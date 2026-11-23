# V0.22 ↔ V0.2.9 模块映射与整合决策

日期：2026-11-23  
基准分支：main（V0.22）  
研究分支：research/v029-calibration-drift（V0.2.9）  
本文件所在分支：research/architecture-reuse-2026

## 1. 审查基线

本次核对到的 Git refs：

- main HEAD：c97034c093d79b1be5cc63391e014ec9f9d770e0
- research/v029-calibration-drift HEAD：792b32c3bc32ba09003bdda3ff5241c7ffea1bf9
- GitHub compare：diverged；V0.2.9 分支 ahead 25、behind 64。

两个分支已经各自演化，不能通过一次普通 merge 假定接口兼容。本分支是从 main 建立的独立研究分支。

## 2. 模块映射

| 能力域 | V0.22 代码 | V0.2.9 代码 | 决策 | 理由与迁移风险 |
|---|---|---|---|---|
| PCAP 采集解析 | capture.py | 无对应通用 PCAP 适配器 | 保留 V0.22，后续扩展 | V0.22 只支持 classic PCAP Ethernet/IPv4/TCP；不支持 pcapng、IPv6、IP 分片、TCP 重组本身 |
| TCP 流重组 | stream_reassembly.py | 无对应模块 | 保留 V0.22，补强后作为统一输入层 | 目前按方向四元组分组，未识别 connection epoch；SYN 起点、序列号回绕、四元组复用和时间排序均需专项验证 |
| 会话/方向模型 | session_model.py | 无同等状态机模型 | 保留 V0.22 | 输入仍依赖外部给定的方向与顺序；尚未由 PCAP 自动形成双向应用会话 |
| 帧边界 | stream_framing.py、length_rules.py、pipeline.py | framing.py、equivalence.py | 双引擎并存，通过统一候选接口输出 | V0.22 偏长度字段/边界等价；V0.2.9 偏两字节同步字、有限布局与 CRC-8 证据。两者搜索空间不同，不可把某一方的拒绝解释为协议不存在 |
| CRC/校验 | evaluate_v08.py、pipeline.py 中 SUM8/XOR8 与既有模型 | checksums.py、crc_discovery.py、joint_crc.py、robust_crc.py | 重点复用 V0.2.9，封装成独立校验候选生成器 | V0.2.9 支持的 CRC 搜索仍有界：CRC-8、限定多项式/反射族和有限布局。不得宣传为任意 CRC/校验发现 |
| 联合帧与 CRC 推断 | pipeline.py 中候选边界与校验筛选 | joint_crc.py | 作为 V0.2.9 专用策略保留 | joint_crc.py 直接导入 framing.py 的私有函数 _sync_candidates、_positions、_Candidate、_select，需先提取公共内部接口，避免跨模块私有耦合 |
| 鲁棒 CRC 共识 | 无直接同等模块 | robust_crc.py | 作为可选插件保留 | robust_crc.py 顶层导入 NumPy，而 NumPy 仅列在 robust optional extra；必须将导入延迟到插件入口或明确依赖检查，否则基础安装时导入失败 |
| 字段类型 | fields.py、evaluate_fields.py | fields.py | 保留两种证据产生器，统一为 FieldHypothesis | 两套均以有限偏移/布局为主；V0.2.9 的 counter/enum/constant 仍是结构候选，不是物理语义 |
| 跨字段关系 | relations.py、robust.py、dependency.py、ambiguity.py | 无直接同等模块 | 保留 V0.22 | affine/XOR/counter/carry 关系不能自动推导因果；需要带样本范围、留出表现和可辨识条件 |
| 时序/块依赖 | temporal.py、cadence.py、adaptive.py | 无直接同等模块 | 保留为独立统计策略 | 置换检验要求交换性或合理块划分；显著性不能证明字段语义或因果 |
| 观测等价与区分 | pipeline.py 中 boundary groups | equivalence.py | 以 V0.2.9 的显式模型集为主，兼容 V0.22 groups | V0.2.9 保留近优模型、共识边界、完整帧冲突计数和长度-only acquisition plan；plan 是条件式实验建议，不是设备控制器 |
| 证据来源与溯源 | 分散在结果 JSON / README | evidence.py | 采用 V0.2.9，扩展为统一 Evidence/Source 模型 | independence_group 是声明标签，不是统计独立证明；不能因组名不同就直接相乘证据 |
| 可靠性校准 | 有限 | reliability.py | 采用 V0.2.9 的校准框架 | 要求独立标注校准集、正负样本、环境 ID；依赖审查也只在样本与环境范围内有效 |
| 完整性审计 | 校验通过等证据 | integrity.py | 采用 V0.2.9 的保守解释 | CRC/模型共识不是无损传输证明、身份认证或防重放保证 |
| 漂移监控 | 无 | drift.py | 独立后处理插件，不进入核心解码路径 | 只监控外部标注反馈；V0.2.9 报告明确指出自相关错误会触发 CUSUM/Page-Hinkley 假警，2-of-3 不是独立投票 |
| 修复候选 | 无 | repair.py | 隔离为实验插件，默认关闭 | 仅适用于头/尾完整、单编辑等强假设；修复结果永远不能自动升级为可信原始帧 |
| CLI/协议模型 | pz_cli.py、protocol_spec.py | cli.py、__main__.py、model.py | 先定义 v1 schema，再写兼容 adapter | V0.22 schema version 1 是 groups/rules/checksums/constants；V0.2.9 是 dataclass FrameModel/FrameRecord，二者不可直接互换 |

## 3. 重点代码事实与风险

### 3.1 V0.22 入口范围

pipeline.analyze_pcaps() 先调用 stream_reassembly.streams()，再要求每个 PCAP 恰好存在一个非空且状态为 ok、观察到 SYN 的方向流。否则返回 unsupported_stream。

因此它目前不是完整的双向 PCAP 会话分析器，也不是多连接 pcapng 解析器。stream_reassembly.py 自身注释明确没有 connection epoch detection。

### 3.2 V0.29 帧推断范围

framing.py 的 rank_hypotheses() 搜索有界模型族：
- 2-byte sync；
- length offset 2..5；
- 1/2-byte length；
- 2-byte length 时尝试大小端；
- length 与 payload 之间最多 0..2 个额外字节；
- 单字节 trailer；
- checksums.CHECKSUMS 中注册的校验算法；
- 最大 payload 默认 512 bytes。

它能处理该模型族内的未知 stream offset、噪声重同步和校验候选，但不覆盖无同步字、bit-level framing、多字节 trailer、任意 TLV、压缩/加密等一般协议族。

### 3.3 V0.29 的等价模型不是概率

equivalence.fit_models() 的 score window 是启发式阈值；consensus() 只统计模型共同给出的帧边界；refine() 依赖独立分帧的完整干净帧，达到冲突阈值才剔除模型。

plan_lengths() 只根据用户提供的总帧长度候选寻找模型可区分条件；它不发设备命令，且无响应不构成反证。

### 3.4 证据校准与漂移限制

- evidence.py 将来源类型、覆盖范围、边界序列、结构规则和帧候选显式建模。
- reliability.py 使用标注数据估计来源的 TP/FP/TN/FN，并用校准集/评估集 ID 与环境 ID 防止明显的数据泄漏。
- 来源 independence group 仍由调用方声明；统计相关审计不能证明真正独立。
- drift.py 需要 (ground_truth, source_verdict) 标签，分别监控 FN/FP。无标签流量不能用来证明准确率下降，也不自动更新校准。
- V0.2.9 报告中的 100 seeds 是合成探索实验，不是现场工业误报率保证。

### 3.5 修复插件的边界

repair.py 假设单帧间隔、头和校验尾部完整、最多一个 payload 插入/删除或 bit flip、无 gap padding。其输出被标记为修复假设，不得替代原始采集证据。

## 4. 统一架构：策略插件，不做版本二选一

推荐数据流：

1. Capture Adapter：PCAP/raw bytes/CAN/UART/IQ 分层接入。
2. Flow & Session Builder：重组、方向、时间与丢失状态。
3. Message/Frame Candidate Generator：并行运行长度规则、同步字/CRC 等策略。
4. Hypothesis Registry：去重、竞争、保留观察等价模型。
5. Field & Relation Inference：字段类型与数学关系候选。
6. Evidence Registry & Reliability：来源溯源、校准、依赖与漂移。
7. Semantic Evidence Fusion：外部设备状态/HMI/传感器/操作标签关联。
8. State Learning：抽象消息符号后接 AALpy 等后端。
9. Verification & Export：独立留出验证，生成解析器/报告。

任何推断器只能提交候选和证据，不得直接覆盖原始数据或把单个候选升级为语义真值。

## 5. 迁移顺序

### M0 — 冻结边界
- main 保持 V0.22 稳定基线。
- V0.2.9 保持研究分支。
- 不做 merge，不删历史，不覆盖旧结果。

### M1 — 定义统一 schema
- 采用 docs/UNIFIED_DATA_MODEL_V1.md 与 schemas/protocol-zero-evidence-v1.schema.json。
- 所有新 adapter 输出统一 ID、来源、数据范围、候选状态和证据引用。

### M2 — 只迁移纯函数策略
- 先接入 checksum registry 与 CRC-8 bounded strategy。
- 再接入 framing strategy，移除对私有函数的跨模块导入。
- 以固定 golden captures 比较迁移前后逐字节输出。

### M3 — 迁移证据/可靠性
- 将 V0.29 EvidenceSource / BoundarySeries / StructuralRule / FrameCandidate 适配到 schema。
- 将 ReliabilityProfile / PairwiseDependenceAssessment 作为校准工件，不嵌入单帧对象。
- DriftMonitor 只消费有标签的离线评估结果。

### M4 — 对接 V0.22
- 保留 PCAP/TCP/session 作为 capture adapter。
- 将其边界组、字段候选、关系候选映射到统一对象。
- 不直接把 V0.22 protocol_spec v1 作为统一 schema；保留导入/导出兼容层。

### M5 — 统一 CI 与回归
- 单独运行 V0.22 原有测试；
- 单独运行 V0.2.9 tests；
- 再运行跨版本 golden fixture 测试；
- 验证基础安装不要求 NumPy，只有 robust extra 才加载 NumPy；
- 运行 lint/type/compile 检查和 CLI smoke tests；
- 每次集成保存逐样本结果和环境信息。

## 6. 迁移验收门槛

只有以下条件全部满足，才考虑将整合结果合并到 main：

1. 所有旧版 golden fixture 的输出行为有逐项对照，变化有明确解释。
2. 两边测试在同一受控环境全部运行，失败和跳过项透明报告。
3. 新旧协议描述均可读写，且 round-trip 不丢候选/证据。
4. 未校准的 ranking score 不被序列化为 probability。
5. 任何来源独立性仅在经过审计的范围内陈述。
6. 修复帧不会被默认当成原始可信帧。
7. 不支持协议族能够 abstain，而不是猜一个看似完整的解析。
8. 无任何未经授权的设备 I/O 或主动控制。

## 7. 本轮结论

V0.22 是数据接入、TCP 重组、关系推断与有界会话模型的主要积累；V0.2.9 是受限帧/CRC 联合推断、有限观测等价、证据溯源、校准和漂移监控的主要积累。

二者应通过统一 schema 形成插件化协作，而不是整仓覆盖或简单合并。当前尚未迁移运行时代码，本文件是基于 Git 源码审查的整合设计。
