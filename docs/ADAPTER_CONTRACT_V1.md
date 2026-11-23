# V1 只读适配器接口与策略插件契约

状态：设计提案；尚未实现运行时 adapter。  
依赖：UNIFIED_DATA_MODEL_V1.md 与 protocol-zero-evidence-v1.schema.json。

## 1. 为什么需要 Adapter 层

V0.22 与 V0.2.9 的对象不只是命名不同，语义也不同：
- 一个 V0.22 group 可以包含多条边界规则；
- 一个 V0.29 FrameModel 是一个具体的受限布局模型；
- V0.29 FrameRecord.checksum_ok 是算法对当前候选模型的检查结果，不是外部 ground truth；
- V0.29 FieldHypothesis.confidence 没有在对象内声明校准过程；
- V0.22 pipeline group 未必有可比较的数值分数。

因此 adapter 只能忠实映射已有信息，不能补造概率、字段语义、来源独立性或唯一模型。

## 2. 策略插件公共接口

概念接口：

    class FrameInferenceStrategy(Protocol):
        strategy_id: str
        capabilities: StrategyCapabilities

        def propose(self, context: AnalysisContext) -> StrategyResult:
            ...

StrategyCapabilities 至少包含：
- accepted_capture_formats；
- accepted_input_layers；
- requires_external_message_boundaries；
- supports_unaligned_stream；
- supports_multiple_flows；
- supports_missing_bytes；
- supported_sync_widths；
- supported_length_widths；
- supported_checksum_families；
- active_io_allowed（默认 false）；
- known_limitations。

StrategyResult 至少包含：
- strategy_id / strategy_version；
- hypotheses；
- evidence；
- diagnostics；
- rejected_inputs；
- execution_config；
- exact input capture/flow/session IDs。

策略只产生候选。是否 active/accepted 由统一 Hypothesis Registry 根据独立验证与策略规则决定。

## 3. V0.22 → V1 适配

### 3.1 protocol_spec v1 groups

旧结构主要包括：
- source_status；
- groups[]；
- selected；
- rules[]；
- checksums[]；
- observed_constants[]；
- length_fields[]。

映射规则：
1. 每个 group 建立一个 equivalence group ID。
2. group 中每一条 rule 生成一个 FrameHypothesis；不能把整个 group 压成一条规则。
3. parameters 保存原始 rule、checksum candidates、observed constants、length rules 和边界签名。
4. selected=true 只映射为 active/candidate 状态，不能映射为 accepted_under_scope。
5. 若旧结果没有排序分数，score.status=unscored、value=null、scale=none。不得用 group 顺序或 selected 标志伪造概率。
6. observed_constants 仅作为观测常量约束，不转成 enum/semantic label。
7. boundary signature 必须保留训练/验证 stream ID 和字节范围；只保留 frame lengths 会丢失绝对位置证据。

### 3.2 stream_reassembly → Flow

保留：
- capture ID；
- 方向四元组；
- reassembly status；
- missing bytes/gap/conflict；
- duplicates；
- SYN observed；
- connection epoch 状态。

当前实现按方向四元组聚合，但未解决 epoch/四元组复用。Adapter 必须将 connection_epoch_status 标为 unknown/ambiguous，不能静默合并多次连接。

### 3.3 fields.py / message_types.py

- fields.py 的 constant、length、counter、unknown、checksum_candidate 输出映射为 FieldHypothesis。
- message_types.py 的 offset + predictive gain 映射为 field_kind=message_type 或 enum 候选。
- gain_bits 是 held-out predictive ranking statistic，不是概率；映射到 ranking_only score，scale=bits_per_event。
- 不能因为一个字节具有预测增益就认定它是 opcode；需要与消息族/方向/状态证据共同验证。

### 3.4 relations.py / dependency.py / temporal.py

- affine、XOR、counter、carry 关系映射为 RelationHypothesis。
- 默认 claim_level=statistical_association 或 deterministic_constraint，具体取决于是否对完整留出集逐样本精确成立。
- permutation p-value 及 block assumptions 放入 evidence/validation，不作为 semantic truth。
- 每条关系都保留 operands、参数、训练/验证样本范围、反例数和适用条件。

## 4. V0.2.9 → V1 适配

### 4.1 FrameModel → FrameHypothesis

参数逐项保留：
- sync；
- length_offset / length_width / length_endian；
- payload_offset；
- trailer_size；
- checksum；
- max_payload。

strategy 标识为 bounded-sync-length-checksum，capability 声明必须包含它的搜索限制。一个 FrameModel 只是一种候选布局模型，不是通用协议规范。

### 4.2 FrameRecord → Message + Evidence

- stream_id 必须通过显式映射关联到 V1 flow/session；不可直接把整数 stream_id 当成全局 ID。
- start/end 作为流内半开字节区间；
- data 原样引用 Capture byte range 或派生 blob；
- checksum_ok 产生 capture_derived checksum_observation。
- 因为 framing search 本身可能已经使用同一 checksum model 选边界，所以该证据与模型存在循环依赖；source independence_group 必须继承原始 capture 的来源组，不能算独立 CRC 投票。
- FrameRecord.score 是内部 interval scheduling 分数，不是校准概率；映射为 ranking_only，并保存 scoring method/version。

### 4.3 FieldHypothesis → FieldHypothesis

- start/end 均以字节为单位，转换成 bit offset。
- 非负 start/end 相对 frame_start。
- 负 start/end 表示相对 frame_end；例如 start=-1,end=0 映射为 frame_end[-8,0)。
- start=payload_offset、end=-trailer_size 表示动态 payload 区间；需同时保存 length_expression。
- confidence 仅映射为 ranking_only/normalized_score，除非存在独立 CalibrationProfile。
- alternatives 原样保留，不将其扁平化为唯一字段类型。

### 4.4 Evidence / Reliability / Drift

- EvidenceSource → V1 source；independence_group 原样保留，independence_status 初始为 declared。
- BoundarySeries → boundary_observation evidence；必须保留 covered_start/covered_end、complete 和 boundary positions。注意旧 BoundarySeries 的 covered_end 是 inclusive coverage；不能直接当作 Message 的 half-open end。
- StructuralRule → deterministic constraint candidate，并保留 source_id 与 expectation form。
- ReliabilityProfile → CalibrationProfile；保留 TP/FP/TN/FN、min_per_class、calibration dataset 和 environment。
- PairwiseDependenceAssessment → DependenceAudit；保留正/负类相关系数、区间、样本量、阈值和方法。
- drift.monitor_source → DriftAssessment；必须保留 calibration/evaluation dataset 不同、环境匹配条件、FN/FP 分开统计和 detector outputs。
- DriftAssessment 必须保持 calibration_updated=false、integrity_verified=false。

### 4.5 Repair

repair.py 的候选输出映射为 RepairHypothesis：
- 引用 original_message_id；
- 记录 reconstructed_sha256；
- 保存 edit operation 和 assumptions；
- 状态只能表示在假设条件下的候选/接受；
- trusted_as_original 永远为 false；
- 不覆盖 Capture、Flow 或 Message 的原始字节。

## 5. 统一 Hypothesis Registry 规则

1. 相同字节边界不一定意味着相同字段语义；按模型参数和观测行为分别去重。
2. 不同模型在当前观测上产生相同边界时，保留 observational equivalence group。
3. 候选之间存在冲突时，保留 alternative，不以分数微小差距强制唯一选择。
4. accepted_under_scope 必须绑定验证数据集、设备/环境范围和适用条件。
5. 分数不同量纲不能直接排序：bits/event、log-likelihood、heuristic score、normalized score 必须分开比较。
6. calibrated_probability 必须引用 CalibrationProfile；否则 schema validator 应拒绝。
7. 所有输出都必须保留支持证据、反证和未覆盖范围。

## 6. 第一批只读 Adapter 的验收测试

### V0.22 adapter
- 规则数量和偏移/宽度/端序/偏差逐项保留；
- group equivalence ID 不丢失；
- selected 不会转成概率或事实；
- constants 不会变成语义标签；
- relations 的 operand IDs 可以追溯到字段候选。

### V0.2.9 adapter
- FrameModel 所有参数逐项 round-trip；
- FrameRecord 半开边界和原始 bytes hash 一致；
- checksum_ok 保留为算法观察，不变成 ground truth；
- FieldHypothesis 负 offset 正确映射 frame_end；
- CalibrationProfile 的正负样本数和 dataset/environment 正确；
- repair hypothesis 永远不被当作原始帧。

### 跨版本
- 读取旧结果 → V1 → 读取 V1 后候选/证据不丢失；
- 旧版无法表达的 provenance/alternatives 在有损导出时显式报告；
- 所有 ID 全局唯一，所有引用可解析；
- 旧版测试结果和原始 JSON 不被改写。

## 7. 实施顺序

1. 先实现只读 V0.22 adapter。
2. 再实现只读 V0.2.9 adapter。
3. 用 synthetic fixture 和各分支原有实验输出做 golden tests。
4. 运行两个分支完整测试套件和跨版本 schema tests。
5. 通过后才把策略插件接入统一 pipeline。
