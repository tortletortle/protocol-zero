# PROTOCOL ZERO 统一数据模型 V1

状态：研究分支中的接口提案，尚未接入运行时。  
配套机器校验文件：schemas/protocol-zero-evidence-v1.schema.json

## 1. 设计目标

统一模型不只是统一字段名称，而是统一每一项推断的来源、范围、证据、竞争关系和验证状态。

V0.22 与 V0.2.9 的数据形态不同：
- V0.22 多使用 dict、tuple 和协议描述 JSON；
- V0.2.9 使用 FrameModel、FrameRecord、FieldHypothesis 等 dataclass；
- 两边对 score/confidence、帧边界、CRC 共识和来源的语义并不完全一致。

V1 不允许通过简单字段重命名掩盖语义差异。

## 2. Bundle 顶层结构

一个分析结果由一个 Evidence Bundle 表示，包含：

- run：运行版本、Git commit、参数摘要、数据划分与环境；
- captures：不可变原始采集文件及哈希；
- sources：证据来源与其来源组；
- flows：网络/总线方向流及重组状态；
- sessions：由多个 flow/burst 组织的会话；
- messages：候选或已确认的消息/帧观测；
- evidence：支持、反驳或无法判断某个候选的证据；
- frame_hypotheses：边界、同步字、长度与校验模型；
- field_hypotheses：字段范围、编码与类型候选；
- relation_hypotheses：字段间数学/时序关系；
- semantic_hypotheses：字段与外部设备变量/操作的映射；
- state_models：消息序列的状态/转移模型；
- validation_results：独立数据集上的验证结果。

所有 ID 在 bundle 内唯一。跨 bundle 引用必须同时带 bundle ID，不能只依赖数组下标。

## 3. 统一对象语义

### 3.1 Capture：原始数据永远不可变

Capture 只描述采集文件本身：
- 格式、SHA-256、字节数、采集时间；
- 来源 URI 或受控存储引用；
- 设备、环境、接口和授权范围；
- 不在 Capture 内写入推断出来的字段或帧边界。

原始文件不应被“修复”或重写。任何清洗、解码、重组都产生派生对象，并保留对原始 Capture 的引用。

### 3.2 Flow 与 Session：传输层对象不等于应用层会话

Flow 记录端点、方向、传输协议、重组状态、缺失区间、重复数据、连接 epoch 识别情况。

Session 记录多个 flow/burst 的关联及顺序依据。方向、客户端/服务端角色、会话归属若只是推断，必须标记为 hypothesis，不能伪装成事实。

对 TCP 而言，四元组不能唯一标识整个生命周期；需要 connection epoch，考虑 SYN、FIN、RST、序列号回绕、重用和时间边界。

### 3.3 Message：字节片段和帧候选

Message 是原始字节流中的一个区间或外部采集器给出的帧。
- 使用半开区间 [start, end)；
- 同时保留源 Capture、Flow、Session 和 byte offset；
- 记录 boundary_status：externally_delimited、candidate、ambiguous、truncated、unknown；
- 若多个算法给出不同边界，产生多个 frame_hypotheses，不复制或篡改原始字节。

V0.29 的 FrameRecord 可以映射为 Message 的一个派生解码结果，但其 checksum_ok 不能直接变成独立 ground truth。

### 3.4 Hypothesis：推断对象不是事实

每个 hypothesis 必须有：
- 稳定 ID、类型、适用范围；
- 当前状态：candidate、active、alternative、rejected、abstained、accepted_under_scope；
- 产生算法、算法版本、参数；
- 支持/反驳/未知证据引用；
- 竞争候选 ID；
- 原始排序分数及其分数定义。

禁止把任意 ranking score 叫作 probability。只有在独立标注校准集上完成校准，并记录 calibration_profile_id、校准环境和样本量时，才允许提供 calibrated_probability。

### 3.5 FieldHypothesis：位置、编码和语义分离

位置统一使用 bit offset，避免 byte offset 与 bit offset 混淆：
- start/end 都是半开范围；
- anchor 可以是 frame_start 或 frame_end；
- end-relative 范围可表达末尾 CRC、尾部标志；
- 变长字段需记录 length_expression 或终止条件。

字段结构类型与物理语义分开：
- structure kind：sync、length、checksum、counter、enum、constant、payload、bitfield、numeric、timestamp、unknown；
- encoding candidate：unsigned/signed integer、endianness、float format、scale、offset、bit order；
- semantic mapping：temperature、pressure、motor speed、operator action 等外部标签候选。

“2 字节小端计数器候选”不等于“设备转速”。

### 3.6 RelationHypothesis：相关、约束与因果必须分级

关系至少记录：
- operand hypothesis IDs；
- kind：equality、affine_modular、xor、counter_increment、length_matches、checksum、monotonic、timing、mutual_exclusion 等；
- claim_level：statistical_association、deterministic_constraint、controlled_intervention、spec_confirmed；
- 训练/验证范围、支持样本、反例和适用条件。

被动数据上的高相关性不能直接写成因果关系。只有受控干预或独立规范证据才能支持更强的 claim level。

### 3.7 SemanticEvidence：必须有外部观测源

语义证据可以来自：
- 设备日志；
- HMI/屏幕变量；
- 独立传感器；
- 操作员标注；
- 设备规范；
- 授权隔离实验中的受控操作。

记录时间对齐方法、时钟偏差、滞后区间、观测误差和操作事件。仅有文件名“run/stop”只能算弱标签来源，不能直接成为字段真值。

### 3.8 StateModel：未观测不等于非法

状态机输入符号来自已抽象消息类型、方向和字段谓词。模型需记录：
- model family：DFA、Mealy、Moore、bounded-history 等；
- 状态和转移；
- 学习算法、查询预算、SUL/Oracle；
- 训练与验证会话；
- 未观测转移语义必须默认 unknown_not_proven_illegal。

V0.22 session_model 是 bounded-history baseline，不应描述为通用协议状态机学习器。AALpy 只能在实现抽象输入符号和 SUL/query 接口后接入。

## 4. EvidenceSource 与独立性

V0.29 的 independence_group 是来源归组标签。V1 进一步记录 independence_status：
- declared：调用方声明；
- audited：在指定校准/评估范围内完成依赖审计；
- unknown：未知。

即使状态为 audited，也必须保留审计数据集、环境、方法和时间范围。不得把一个已审计环境的独立性推广到其他设备或环境。

同一原始 Capture 派生出的多个统计量通常共享来源，不能作为多份独立证据相乘。

## 5. ValidationResult 与数据泄漏控制

每次评估必须记录：
- train/validation/test dataset IDs；
- split policy：session_disjoint、device_disjoint、vendor_disjoint、protocol_family_disjoint、time_disjoint 或自定义；
- 标签来源和 ground-truth authority；
- 算法版本、参数、随机种子、运行环境；
- 指标定义、分母、样本数和置信区间；
- abstention、错误接受、错误拒绝和失败样本。

packet 随机切分不能作为唯一泛化证据。同一设备/会话/操作轨迹跨训练与测试会导致泄漏风险。

## 6. V0.22 / V0.2.9 适配关系

| 旧对象 | V1 对象 | 适配说明 |
|---|---|---|
| V0.22 PCAP bytes | Capture | 保留原始哈希、采集格式与授权来源 |
| V0.22 stream_reassembly result | Flow | gap/conflict/duplicates/SYN 等转为明确状态 |
| V0.22 externally ordered bursts | Session | 保留方向来源和顺序可信度 |
| V0.22 split frames | Message | 保留原始流 offset 与边界候选 ID |
| V0.22 protocol_spec v1 groups | FrameHypothesis | 每条 rule 单独保留，groups 作为 equivalence group |
| V0.22 fields.py tuples | FieldHypothesis | 位置映射为 bit range；类型仍为 candidate |
| V0.22 relations.py outputs | RelationHypothesis | 保留算法、训练/验证样本和关系参数 |
| V0.29 FrameModel | FrameHypothesis | sync/length/trailer/checksum 作为 bounded model parameters |
| V0.29 FrameRecord | Message + DecodeEvidence | checksum_ok 是算法观察结果，不是 ground truth |
| V0.29 FieldHypothesis | FieldHypothesis | confidence 转成未校准 score，除非有校准 profile |
| V0.29 EvidenceSource | EvidenceSource | 增加 independence_status 与数据/环境范围 |
| V0.29 BoundarySeries | Evidence | 覆盖范围、complete 与 boundary observations |
| V0.29 StructuralRule | Relation/Constraint hypothesis | 明确规则来源和 claim_level |
| V0.29 ReliabilityProfile | Calibration artifact | 单独存储，不能嵌入单条 frame |
| V0.29 PairwiseDependenceAssessment | DependenceAudit | 保留样本数、环境和置信区间 |
| V0.29 Drift monitor output | DriftAssessment | 只消费有标签反馈，不自动更新 profile |
| V0.29 repair hypotheses | RepairHypothesis | 独立于原始 Message，默认不进入可信解码 |

## 7. 兼容策略

1. 先实现 V0.22/V0.2.9 → V1 的只读导出 adapter。
2. 运行 golden fixtures，比较候选数量、边界、字段和证据，不追求旧 JSON 文本逐字相同。
3. V1 → 旧格式只允许有损导出，并必须列出被丢弃的 provenance/alternatives/validation 字段。
4. 禁止在 adapter 中自动选择唯一模型，或把缺失信息填成默认真值。
5. schema 版本升级使用显式 migration function，禁止静默改写历史实验记录。

## 8. 当前状态

本文件定义 V1 对象契约；配套 JSON Schema 用于结构校验。尚未实现 Python runtime dataclasses、adapter、持久化层或前端 UI。下一步应先实现 schema validator 与两个只读 adapter，再进行跨分支 golden regression。
