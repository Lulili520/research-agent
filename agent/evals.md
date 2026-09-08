# Agent 行为验收

本文件只保留无法由 `test_researchctl.py` 和审计脚本替代的语义检查。

## 路由

- 查询、调研、完整科研分别选择满足请求的最窄流程，不自动扩大任务范围。
- 只有用户明确要求执行实验时，才从冻结协议进入 Pilot。

## 证据

- 摘要不能支撑全文级方法与结果结论；论文身份、版本、venue、track 和 paper type 可复核。
- 跨论文数值比较具有兼容的数据、划分、指标、协议和资源条件。
- 研究空白包含最近工作比较、反向检索、截止日期和未覆盖范围；“未发现”不写成“无人研究”。

## 科研闭环

- Proposal 被当作实验前科学合同，并用 `Q-K-M-D-C` 说明问题、知识主张、机制、决定性检验和科学后果。
- 候选在知识主张或决定性检验上实质不同；只换模型、数据集、名称或参数的近重复候选被合并，不用候选数量制造虚假探索。
- Proposal 有最近邻差异、竞争解释、可证伪假设、结果—贡献矩阵和停止条件；候选评分不能补偿功能等价、不可证伪或不可识别等致命问题。
- Proposal 只有一个中心问题，并用 2–5 个必要子问题补足现象、特异效应、机制、边界或决策后果；互不相干的 topic 不被包装成广度。
- 深度审计从现象/测量推进到效应识别、机制/rival 和边界/原则；经验系统方案只有相关性表格或故事性机制时不能通过。
- 广度审计区分确认性核心、必要边界、最小外部效度、可选扩展和明确排除项；新增模型、数据集或变量必须关联 claim、rival、threat 或外部效度，并有停止扩张规则。
- 当前 Proposal ID 完成五轮 `full-proposal-cycle`，每轮均重新检查深度、广度、新颖性、机制、识别和完整论文证据包；旧 Proposal 轮次、重复搜索和措辞润色不计数。
- `Proposal decision`、`Novelty status`、`Empirical status` 与 `Execution readiness` 相互独立；`Empirical status: not-run` 不导致 Proposal 失败。
- threat register 将问题分为 `proposal-fatal`、`empirical-dependency` 和 `paper-stage`，只允许未解决的后两类随通过方案向下游交接。
- GitHub artifact 只用于实现、许可和资源可行性核验，不以 star、README 或代码存在证明新颖性与正确性。
- 理论预测能够区分竞争解释，并逐项映射到可失败实验。
- 协议在主结果出现前冻结；Pilot 不通过时不得进入主实验。
- 失败 run 和协议偏离被保留；结论允许 supported、refuted、mixed 或 inconclusive。

## 交付

- 默认使用简体中文，并区分 `reported`、`derived`、`inference` 和 `proposal`。
- 用户交付物只放在 `outputs/`；内部状态、证据、运行记录与来源放在 `.research/`。
