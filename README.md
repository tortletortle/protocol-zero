# PROTOCOL ZERO

> 状态：Private 开发仓 · 批次 1 · 资源优先级：30%

## 当前完成度

- 记录进度：V0.18，TCP 流重组与联合分帧（受控故障注入）
- **未经验收功能不得标记为已完成。**

## 目标 / 架构 / 运行方式

目标：从授权采集或模拟的二进制通信记录推断帧结构、校验及字段数学关系，不将统计关联等同于真实语义。

- 分帧与校验：`joint.py`、`calibration.py`、`crc_adapter.py`
- 字段与歧义：`fields.py`、`ambiguity.py`、`dependency.py`
- 关系推断：`relations.py`、`robust.py`、`adaptive.py`、`temporal.py`、`cadence.py`

运行（Python 3，无第三方依赖的 V0.15 实验）：

```bash
python -m unittest discover -v
python evaluate_v15.py
```

V0.15 本地 21 项单元测试通过；800 个实验单元（每种条件 100 个种子，跨块大小配对复用）。负对照中，块大小 1/4/8/16 的逐行置换误报为 5/19/33/42%，分块置换均为 5%；30% 概率整块替换输出的正对照均检出 100/100。原 200 种子实验超时，最终采用 100 种子。详见 `results_v15.json`。

限制：已知正确分帧与块长度、块间可交换且训练验证独立；未验证真实通信数据、未完成端到端集成或第三方工具对照。不将模拟结果外推到真实工业协议。

## 工程约定

1. 一个独立项目对应一个 GitHub 仓库。
2. 开发阶段默认 Private。
3. 保留本地 Git 完整提交历史和版本标签。
4. 每个版本保留测试报告、实验数据和变更记录（建议放 docs/）。
5. README 保持目标、架构、运行方式、当前完成度四段信息。

## 迁移说明

本仓库已迁入研发源码；如有未迁入的完整历史，仍需保留。若你本地另有完整 Git 历史，请用：

```bash
cd <你的本地项目目录>
git remote add origin https://github.com/tortletortle/protocol-zero.git
git push -u origin --all
git push origin --tags
```

不要用空骨架覆盖已有历史。

## V0.16

运行 `python -m unittest discover -q`（27项通过）及 `python evaluate_v16.py`。520组配对模拟实验：固定块320/320长度识别，160/160正对照正确候选检出，0/160负对照误报。200组压力测试中，弱马尔可夫3/40、16周期随机重复1/40出现错误检出。自相关仅扫描1–8阶，阈值为启发式；自动块长度并不证明块间可交换性，只输出探索性证据。种子跨条件复用。尚无真实采集、端到端集成或第三方基准验证。详见 `results_v16.json`。

## V0.17

`python -m unittest discover -q`：32项通过。`python evaluate_v17.py`：250组受控实验（12000条记录），150/150 正确长度候选检出，100/100 负对照无检测，100/150 正对照有多个候选。旧字段模块不支持16位长度标签，不构成公平外部基准。长报文和小端样本并非均为合规 Modbus ADU。

`capture.py` 支持 classic PCAP Ethernet/IPv4/TCP 单段载荷提取，不支持 TCP 流重组、去重、pcapng；`length_rules.py` 需要已分帧记录。第三方测试 PCAP 284字节，Git blob SHA 一致，3条载荷与 MBAP 长度规则吻合，样本不足以盲推断。来源及哈希见 `capture_smoke_v17.json`。外部较大抓包受 DNS 和连接器限制，尚未获取；不能宣称真实工业捕获验证或第三方逆向工具对照完成。

## V0.18

`python -m unittest discover -q`：42项通过。`python evaluate_v18.py`：280组配对训练/验证实验，每条件40个种子；160/160完整流对完全重组并包含正确长度规则及边界，但均存在多候选；80/80缺失或冲突流对被拒绝；40组独立随机字节流负对照中1组误检（seed 19031，规则 offset=7,width=1,bias=7）。旧逐包提取仅在40组对齐样本中完整恢复，120组非对齐样本均不完整。详见 `results_v18.json`。

新增 `stream_reassembly.py` 与 `stream_framing.py`。仅支持 classic PCAP Ethernet/IPv4/TCP，按方向四元组聚合（假设单连接），重组跨度上限1MiB，无SYN时起点未经验证，不能可靠检测尾部丢失或四元组复用。分帧假设完整且起点对齐，搜索偏移0–7、宽度1/2/4、偏差−16至16；最大帧4096字节。生成的类Modbus样本并非真实工业抓包或完全符合规范；种子跨条件配对复用。未完成校验与字段推断端到端集成、真实抓包和第三方基准对照。
