# PROTOCOL ZERO — 架构与现有技术复用研究（2026-11-23）

## 0. 结论

PROTOCOL ZERO 的长期目标有技术可行性，但“输入几分钟任意原始波形，即自动得到完整协议语义”不是一个单一算法问题，也不是目前项目已经具备的能力。

建议将系统定位为：面向授权采集数据的多层通信逆向工作台。从可解码的通信观测中建立多个可竞争、可验证的协议假设；在具备外部上下文或安全实验条件时，逐步推断字段语义和状态机；最终输出带证据、适用范围和不确定性标记的协议模型及解析器。

本轮结论：
1. 不应重写 Netzob、NetPlier、AALpy、boofuzz 等已有能力。
2. 不应先上字节级 Transformer。现阶段更需要数据接入、消息分组、字段候选、假设管理、独立验证和证据追踪。
3. 字段语义必须引入外部上下文：操作标签、HMI/传感器、车辆信号、设备状态或受控实验记录。纯字节相关性不能自动证明“温度”“摇杆”等物理含义。
4. 主线应先聚焦 PCAP/已解码字节流，CAN 作为独立输入适配器；UART 和 SDR 必须分别解决物理层/链路层解码，不应假装它们已经是应用层字节流。
5. 当前 V0.22 主线与 V0.2.9 研究分支已明显分叉，不能直接合并。

---

## 1. 首先拆清输入层级

“原始抓包波形”至少可能指四种不同的数据：

| 输入 | 已经知道什么 | 尚未解决什么 |
|---|---|---|
| SDR IQ 样本 | 采样后的复数信号 | 载波/符号同步、调制识别、解调、线路编码、帧同步、FEC 等 |
| UART 逻辑电平/波形 | 可能有电压采样或数字边沿 | 波特率、极性、数据位、奇偶校验、停止位、字节恢复 |
| CAN 报文记录 | 仲裁 ID、DLC、数据帧边界通常已由采集器解码 | ID/报文族分类、payload 字段、信号缩放、物理语义、周期/状态关系 |
| PCAP 网络记录 | 链路/IP/传输层头部，视采集格式而定 | TCP 重组、会话划分、应用层消息边界、字段与语义 |

因此应将采集适配器与协议推断核心解耦。每条观测至少保留：原始文件哈希、采集来源、时间戳与采样条件；输入层类型、接口/通道、方向（如可得）；包/帧/流/会话边界来源；丢包、重复、冲突、解码置信度；人工标签及其来源。

**范围决策：V0.3 首个端到端垂直切片只接收 PCAP 中可重组的 TCP 应用字节流，以及用户提供的已分帧原始字节记录。** 暂不承诺直接处理 IQ 波形。CAN、UART、SDR 作为不同适配器分阶段加入。

---

## 2. 现有工具复用矩阵

| 工具/研究 | 已公开能力 | 复用判断 | 关键限制/许可证 |
|---|---|---|---|
| Netzob | 报文格式/字段关系、协议语法/状态机、主动与被动推断、流量生成、模糊测试；支持 PCAP/raw import，导出 Scapy/Wireshark | **首选比较基线；优先做数据/模型适配器，不重写其通用模型能力** | GPL-3.0；官方推断文档的 inference 章节仍标注“should be completed”；主仓库当前可核验 master 提交时间为 2023-01-08，需先做安装与运行验收 |
| NetPlier | 二进制协议消息轨迹上的多序列比对与概率推断 | **字段结构发现的对照基线** | GPL-3.0；依赖 Netzob 与 MAFFT；CLI 的 protocol type 参数和 ground-truth 评估流程需要检查，不能将它直接视为任意未知协议端到端工具；当前 master 最新可核验提交为 2021-06-10 |
| AALpy | 主动/被动自动机学习：DFA、Mealy、Moore、非确定性/随机模型及 pushdown 形式；包括 L*、KV、RPNI、EDSM、k-tails 等 | **推荐作为状态机学习后端**，前提是 PROTOCOL ZERO 先把消息抽象成输入/输出符号，并实现 SUL/查询接口 | MIT；Python >=3.10；主动学习需要系统接口和等价查询/测试预言机，不是直接喂原始 PCAP 就能得到状态机；仓库近期仍有提交（2026-11-19） |
| AFLNet | 用记录的客户端/服务器交互作为种子，按响应码和状态反馈进行协议实现灰盒模糊测试 | **后期用于协议实现测试，不是字段发现器** | Apache-2.0；主要针对可交互的服务端实现 |
| StateAFL | 插桩服务端，采集每轮处理的长期内存快照，以模糊哈希推断运行状态并引导 fuzzing | **仅适合有源码/可插桩的服务端实现作为旁路证据** | Apache-2.0；需要用项目提供的编译器插桩目标，不能直接套用在外部 PLC/无线设备上 |
| boofuzz | 请求/块/原语定义、变异、故障监测、重置、记录；支持 TCP/UDP、raw socket、串口连接 | **用于已获得候选模型后的授权实验和健壮性测试** | GPL-2.0；其协议定义由用户提供，不负责自动逆向 |
| Wireshark Lua API | 自定义 Proto、ProtoField、dissector table、Decode As 等 | **解析器导出目标**，不要自行重造抓包 GUI | 需按 Wireshark Lua API 和分发许可要求审查生成代码；生成 dissector 只证明模型能被工具执行，不证明模型语义正确 |

### 2.1 关键来源

- Netzob 官方文档：https://netzob.github.io/netzob/
- Netzob 推断指南：https://netzob.readthedocs.io/en/latest/user_guide/inference/
- Netzob GitHub：https://github.com/netzob/netzob
- NetPlier GitHub：https://github.com/yapengye/netplier
- AALpy 官方文档：https://des-lab.github.io/AALpy/
- AALpy GitHub：https://github.com/DES-Lab/AALpy
- AFLNet GitHub：https://github.com/aflnet/aflnet
- StateAFL GitHub：https://github.com/stateafl/stateafl
- boofuzz 文档：https://boofuzz.readthedocs.io/en/stable/
- Wireshark Lua API：https://www.wireshark.org/docs/wsdg_html_chunked/lua_module_Proto.html

---

## 3. 最相关的研究路线：物理语义联合推断

### 3.1 REInPro — 控制字段驱动的工业协议逆向

论文：Qin et al., “Reverse Engineering Industrial Protocols Driven by Control Fields,” IEEE INFOCOM 2024.

公开摘要显示，该方法通过概率网络流量模型识别控制字段、聚类关联流量，再通过协议字段特征差异推断语义。论文报告覆盖 8 种工业协议、6 台 PLC、5 家 OEM，并给出格式/语义正确性与完整性指标。

价值：PROTOCOL ZERO 应把“控制字段候选”和“报文族聚类”作为独立研究层，而不是只在所有报文中寻找固定偏移。

限制：公开摘要中的指标不是跨论文可直接比较的统一基准；尚未确认有可直接复用的 REInPro 实现代码。

论文：https://doi.org/10.1109/INFOCOM52122.2024.10621405
数据集：https://github.com/hi-zer/Industrial-protocols-dataset

### 3.2 SePanner — 基于交互流量的 PLC 变量语义提取

ACSAC 2023 的 SePanner 使用多状态对比定位语义字段，再用单状态比较和过滤规则去除干扰字段。

2026 年同一研究方向的期刊论文摘要报告：在 S7COMM 上验证了 100% 的变量语义准确率，并在 7 种专有工业协议中提取 63 个控制变量及其 134 种状态。该结果是论文报告值，不等同于对任意未知协议的泛化保证。

价值：
- 设计成组的状态/操作对比数据；
- 区分目标变量变化与报文顺序、冗余字段等干扰；
- 把语义标签绑定到字段及其状态，而不是只给字段起名字。

来源：
- ACSAC 2023：https://doi.org/10.1145/3627106.3627179
- 2026 TDSC：https://doi.org/10.1109/TDSC.2026.3667398

### 3.3 Physeinfer — HMI 视觉状态与报文时序联合分析

论文：Computers & Security, 2025-12, DOI 10.1016/j.cose.2025.104654.

其公开摘要描述了：
- 摄像头周期性采集 HMI；
- 图像差异提取物理变量变化序列；
- 自适应步长的纵向多序列对齐；
- DTW 对齐物理变量序列与动态报文字段；
- 六个工业场景的评估。

论文报告字段分割 perfection 相比 Netzob、MSERA、Fieldhunter 分别提升约 16%、11%、27%。这说明外部物理上下文可能比单纯增加字节模型复杂度更有价值。

限制：依赖 HMI 可观察性；其单 HMI-PLC 实验条件不能自动外推到多 PLC、网关或级联 HMI 系统。

来源：https://doi.org/10.1016/j.cose.2025.104654

### 3.4 PicaCAN — CAN 信号物理语义

论文：IEEE Transactions on Mobile Computing, 2025-07, DOI 10.1109/TMC.2025.3541102.

该工作利用物理诱导因果关系，从 CAN 流量中提取动力系统信号语义。论文在三辆车上进行了实验，包括燃油车和混合动力车。

价值：为 CAN 适配器规划提供依据，未来可将候选信号与发动机转速、踏板等外部物理量关联。

限制：特定车辆与动力系统场景，不等同于通用工业总线语义引擎。

来源：https://doi.org/10.1109/TMC.2025.3541102

### 3.5 2026 AFLDL — 不要误用深度学习

AFLDL（2026-11-04）将运行时内存快照映射到协议状态，再结合状态机与灰盒 fuzzing。它依赖目标服务插桩、状态学习和标注快照。

结论：它是协议实现状态探索技术，不是原始字节协议格式推断器。可作为后期服务端实现验证研究，不应作为当前核心依赖。

来源：https://doi.org/10.1186/s42400-026-00688-y

---

## 4. PROTOCOL ZERO 应采用的分层架构

建议把当前“一个 pipeline 里做所有事情”改成显式的证据流水线。各阶段输出候选和证据，不直接覆盖前一阶段的假设。

| 层 | 模块 | 输入 | 输出 | 是否已有积累 |
|---|---|---|---|---|
| L0 | Capture Adapters | PCAP、已解码字节、未来 CAN/UART/IQ | 统一观测记录 | 仅有限 PCAP/TCP 支持 |
| L1 | Stream/Session Reconstruction | 带时间戳的包/帧 | 有方向的流、会话、缺失/重复标记 | 有 classic PCAP IPv4/TCP 原型 |
| L2 | Message Family Discovery | 会话与字节流 | 消息族候选、边界候选 | 有限长度/同步字推断 |
| L3 | Format Hypothesis Engine | 消息族 | 字段边界、类型、长度、校验候选 | 有 CRC/长度/字段原型 |
| L4 | Relation & Constraint Engine | 多条消息、字段候选 | 计数器、长度依赖、跨字段关系、CRC 约束 | 有部分实现 |
| L5 | Semantic Evidence Fusion | 字段变化 + 外部标签/HMI/传感器/实验记录 | 语义映射候选及证据 | **核心缺口** |
| L6 | Grammar/State Learning | 已抽象的消息类型与方向 | DFA/Mealy/扩展状态模型 | 有限历史模型；应评估 AALpy |
| L7 | Active Discrimination Planner | 竞争假设、允许的安全实验 | 下一条最有区分力的观测建议 | 尚无完整实现 |
| L8 | Verification & Export | 模型、留出流量、证据 | 解析器、Wireshark/Scapy 输出、验证报告 | 有部分描述格式原型 |

### 关键设计原则

1. **Hypothesis-first**：每个字段/边界/校验/状态都保留多个候选。
2. **Evidence provenance**：标明证据来自哪份抓包、哪次操作、哪种工具或哪条外部信号。
3. **No semantic overclaim**：相关性只能生成候选；没有外部标签或受控干预时，不把字段命名为温度、转速、摇杆。
4. **Abstention**：数据不足、候选冲突或模型族外时返回“不确定/需要更多证据”。
5. **Independent holdout**：不能把同一设备、同一会话或同一操作序列随机拆分后宣称泛化。
6. **Safety boundary**：默认被动离线分析；主动查询只允许用户授权的隔离实验台或模拟器。不得默认向生产 PLC/车辆控制总线发送写操作、复位、下载或控制命令。

---

## 5. 现有仓库审查：代码积累与集成风险

审查对象：tortletortle/protocol-zero。

### 5.1 main 主线现状

main README 标记 V0.22。主线代码仍以仓库根目录的多个脚本为主：
- capture.py：classic PCAP Ethernet/IPv4/TCP payload extraction，不是通用抓包适配器。
- stream_reassembly.py：有限 TCP 重组；注释明确没有 connection epoch detection。
- stream_framing.py：依赖完整且起点对齐的字节流，搜索受限长度规则。
- length_rules.py：对外部已分帧的变长记录推断长度关系。
- relations.py：精确字节仿射/XOR 关系和计数器候选，不等同于语义推断。
- message_types.py：前 16 个字节位置的单字节消息类型候选。
- session_model.py：有界历史模型；输入要求外部确定方向、完整报文和字段偏移。

README 自身也记录：V0.22 尚未直接集成原始流、双向 PCAP 会话化、真实数据或第三方基准验证。

### 5.2 research/v029-calibration-drift 分支

该分支有模块化的 protocol_zero/ 包，包含 framing、CRC、fields、evidence、reliability、drift 等模块，但它与 main 已经分叉。

2026-11-23 检查到：
- main HEAD：c97034c093d79b1be5cc63391e014ec9f9d770e0
- research/v029 HEAD：792b32c3bc32ba09003bdda3ff5241c7ffea1bf9
- GitHub compare：status=diverged，研究分支 ahead 25、behind 64。

**结论：不能直接把 V0.2.9 分支合并到 main。** 先做 API/模型/测试映射，再以小范围 cherry-pick 或重新实现方式迁移需要保留的模块。本研究文档单独从 main 建立 research/architecture-reuse-2026 分支，未改写 main。

### 5.3 当前不能宣称的能力

- 未发现 SDR IQ 解调链路。
- 未发现 UART 采集/波特率自动识别链路。
- 未发现 CAN 采集适配器和信号语义推断链路。
- 未发现端到端多流/多方向 PCAP 会话化。
- 未发现完整集成的状态机学习与主动查询接口。
- 未发现物理语义外部标签/HMI/传感器融合模块。
- 未完成真实未知协议盲测。

---

## 6. 数据集与基准可用性

### 6.1 REInPro 工业协议数据集

仓库：https://github.com/hi-zer/Industrial-protocols-dataset

本次通过 Git tree 检查到：
- 146 个文件；
- 总文件大小约 25,096,672 bytes；
- 90 个 .pcap，45 个 .pcapng；
- 顶层目录实际出现 9 个：CIP PCCC、Delta、Hollysys、Mitsubish、Modbus、Omron_FINS、S7comm、S7comm_plus、dnp3。

仓库 README 和论文摘要称 8 种协议，但当前目录树有 9 个顶层目录。这一差异必须先核对，不能直接将目录数当作协议数。

部分文件名包含操作标签，例如 read/write register、run/stop、upload/download、clear memory 等。这些标签可用于设计弱监督/配对实验，但必须核验抓包内部内容，不能仅凭文件名当作精确 ground truth。

仓库根目录没有发现 LICENSE/COPYING 文件。**公开可访问不等于允许重新分发或打包进项目**；取得许可/确认数据条款之前，不应把原始数据复制进本仓库或随软件发布。

### 6.2 其他数据

- NetPlier 仓库含 DHCP、DNP3、ICMP、Modbus、NTP、SMB、SMB2、TFTP、ZeroAccess 等样本和评估脚本，但它依赖已知 protocol type 的评估流程，不应被视为未知协议盲测真值。
- 需要另外建立自有合成语法基准，覆盖未知帧头、变长字段、大小端、CRC、多个消息族、计数器、乱序、丢包、重复、加密/压缩和模型族外样本。
- CAN 需要独立的公开数据集和物理信号标签，不能把 PLC PCAP 数据集代替 CAN 评估。

### 6.3 数据划分原则

严禁只按 packet 随机拆分。至少建立：
- 同一设备/同一会话内的训练验证隔离；
- leave-one-device-out；
- leave-one-vendor-out；
- leave-one-protocol-family-out；
- 不同操作状态/环境的时间外留出；
- 纯随机字节流、结构化但不支持的协议族、加密/压缩流负对照。

---

## 7. 推荐的开发顺序

### P0 — 仓库与接口收敛
- main 和 V0.2.9 研究分支建立逐模块映射表。
- 确定统一的数据模型：Capture、Flow、Session、Message、FieldHypothesis、RelationHypothesis、SemanticEvidence、StateModel。
- 每个候选携带来源、算法版本、参数、训练/验证数据 ID 和留出结果。

### P1 — 一个真实数据垂直切片
- 输入：授权工业 PCAP。
- 完成：流重组 → 消息族聚类 → 帧边界/字段候选 → 长度/校验关系 → 证据报告。
- 先不追求语义命名，不做主动写操作。
- 与 Netzob/NetPlier 对照同一份数据、同一训练/留出切分。

### P2 — 语义推断
- 使用带操作标签的成组流量，研究 REInPro/SePanner 思路。
- 若存在 HMI/传感器日志，研究 Physeinfer 式时间序列对齐。
- 对 CAN 另立适配器，评估 PicaCAN 类物理因果方法。
- 将“字段是什么”与“字段代表什么物理变量”分开输出。

### P3 — 状态机与主动学习
- 把消息抽象成方向+消息类型+字段谓词符号。
- 先用 AALpy 被动学习评估已有 trace。
- 再在隔离模拟器/实验台实现 SUL adapter、等价测试和区分性查询。
- 主动实验规划必须提供预期信息增益、风险等级、所需授权和停止条件。

### P4 — 解析器与验证
- 输出统一协议模型 JSON。
- 生成 Wireshark Lua/Scapy parser。
- 对独立留出数据进行 parse/re-encode round-trip、边界一致性、字段值一致性测试。
- 所有不确定字段保留 unknown/alternative，不强行生成语义名称。

---

## 8. 关键指标

| 维度 | 指标 |
|---|---|
| 数据接入 | 可解析记录比例、丢包/重组识别率、方向判定准确率 |
| 消息分组 | ARI/NMI、消息族 precision/recall |
| 分帧 | boundary precision/recall/F1、exact-frame accuracy |
| 字段分割 | byte/bit boundary F1、字段宽度准确率 |
| 字段类型 | counter/length/enum/constant/checksum/numeric 类型准确率 |
| 校验 | CRC 参数精确匹配率、未支持模型拒绝率 |
| 语义 | 有独立标签时的 semantic precision/recall；无标签时不报告语义准确率 |
| 状态机 | state/transition precision/recall、conformance test coverage |
| 可靠性 | FAR、FRR、abstention coverage、selective risk |
| 主动学习 | 达到目标模型所需查询数、信息增益、实验风险 |
| 工程输出 | Wireshark/Scapy parser 执行成功率、round-trip conformance |

---

## 9. 最终研发判断

最有价值的自主研发点不是重新造一个 Netzob 或 AALpy，而是把现有能力组织成一个可信的闭环：

**多源观测 → 候选生成 → 证据关联 → 竞争假设 → 区分性实验 → 留出验证 → 可执行模型。**

建议项目差异化方向：
1. 跨数据源的统一证据模型（PCAP/CAN/UART/未来 SDR）；
2. 字段结构与物理语义分离的双层推断；
3. 信息增益驱动的主动区分实验；
4. 对模型族外数据和不可辨识问题有原则地拒绝；
5. 从候选模型自动生成解析器，并在独立数据上验证。

**短期不建议研发 Transformer。** 当积累了足够多、来源明确、具有字段/语义标注的多协议数据之后，再评估序列模型能否提升消息族分类、候选字段排序或弱监督语义推断；它应是候选生成器，不应成为唯一判决器。
