---
name: iterative-research
description: 从用户给定的计算机科学 topic 出发，持续完成顶级 CCF 会议标准的相关工作调研、创新审计、理论建模、实验、Artifact 与论文交付；用于明确要求自主开展或完成研究的长期任务，不用于只要文献综述或方向建议的请求。
---

# 迭代科研

将研究视为可回退的证据状态机，而不是以正结果为目标的线性流水线。默认使用简体中文记录决策、失败和结论；官方标题、标识符、代码符号与指标保留原文。

## 启动

1. 先确认用户要求停在哪一阶段及已有授权。已有项目先按 [Research runtime contract](references/runtime-contract.md) 执行 `verify-log` 和 `status`，从当前阶段恢复；不得重新初始化或重做已合格材料。新项目先 `init`，再进入范围阶段。
2. 在 `problem-framing` 调用 `research-framing`，保存当前课题的范围并通过 `audit-scope`。不影响方向的缺省项可保守假设并记录；只有缺失信息实质影响研究选择或超出现有授权时询问。`control/state.md` 是人类摘要，不代替机器状态。
3. 根据研究类型选择证据标准。算法/模型、工程系统、benchmark、实证研究、人类参与研究、理论研究和系统综述不得套用同一实验模板。
4. 正式启动顶会目标研究时阅读[统一顶会完整研究标准](references/top-tier-research-standard.md)和[外部质量依据](references/external-quality-sources.md)。所有课题使用同一质量门禁，不按会议拆分科研标准；具体投稿会议仅在研究完成后影响提交合规检查。

## 每轮执行

阶段描述研究处于哪里，每轮执行决定如何取得下一项证据。以下循环由宿主 Agent 执行，不表示 runtime 已提供自动调度服务：

1. **恢复目标与事实**：读取当前阶段、用户要求的交付终点、已有授权、未解决问题及最近产物。检查运行中的外部任务后再决定重试；状态登记不能证明进程仍在运行。
2. **选择下一动作**：优先处理会改变中心判断或阻塞下游的证据缺口，同时保留必要研究分支。为动作写明待回答问题、所需输入、预计产物和验收依据；能直接执行时不把工作停在计划。
3. **调用并观察**：调用相应 Skill、检索工具或已授权执行器，读取实际返回及原始产物。正文无法取得、工具失败和科学反证分别处理，不能相互替代。
4. **验收并更新**：按当前问题核验来源、推导或运行结果，更新主张及依赖它的材料；关键决策与阶段变更通过控制平面登记。没有新证据的改写不算研究进展。
5. **决定继续、回退或交付**：证据足够才通过阶段门禁；有新矛盾就返回最早受影响阶段；仍有可执行的必要任务就继续。仅在达到用户终点、当前范围确实无法继续或需要新增授权时交接，并说明剩余不确定性。

检索/读取的暂时失败可在合理次数内重试或换来源；同一输入反复失败且没有新线索时更换路径，不无限重试。外部任务可能已启动时先核对任务身份和产物，避免重复提交。出现科学失败则调整解释或设计，不能把重试当成追求正结果的手段。

中断交接在已有 `control/state.md` 中保存：当前问题、最后完成动作及产物、未完成动作/外部任务标识、阻塞原因、下一动作和授权边界。它用于恢复上下文，不覆盖机器状态、事件链或运行登记；长期项目使用 [持久任务队列](references/runtime-contract.md#持久证据任务) 保存具体任务、依赖和产物版本；队列不复制研究阶段。恢复时先检查 `list` 的 `ready/usable`；`running` 不证明外部进程仍存活，须对账后才能 `reconcile`。来源或上游任务变化时复核下游，不继续引用失效结果。普通查找无需建队列。

## 阶段与交接

```text
topic
  -> problem-framing
  -> literature-mapping
  -> direction-audit
  -> theory-building
  -> experiment-protocol
  -> [当前协议已获用户执行授权]
  -> pilot
  -> main-experiment
  -> robustness-analysis
  -> evidence-audit
  -> artifact-building
  -> artifact-validation
  -> report-writing
  -> report-review
  -> complete
```

- `literature-mapping` 先调用 `research-proposal`；它复用 `review-protocol`（按需）、`scholarly-search`、`paper-analysis` 和 `evidence-synthesis`，形成覆盖充分且饱和的已核验语料与核心全文精读（默认预算分别为 50–100 与 20–30 篇）和 Proposal，不得把简短调研报告当作完成。
- `direction-audit` 对 Proposal 做实验前科学审计。除语料覆盖、检索饱和、最近近邻差异和 `Q-K-M-D-C` 外，还必须形成研究问题树、贡献层级、深度链、确认性核心、必要边界、最小外部效度和扩张停止规则，并完成当前 Proposal 的五轮全流程复核（具体记录契约见 `research-proposal`，此处不另建一套轮次）。只有深度、广度、机制、可区分预测、反证条件和纸面识别路径共同通过 `researchctl.py audit-proposal` 后，才进入 `theory-building`。尚未执行实验是正常状态，不得作为拒绝原因。
- Proposal 通过后调用 `theory-building`，并阅读[理论—实验契约](references/theory-to-experiment.md)。形式化证明不是所有研究的硬要求，但必须有明确机制、竞争解释、区分性预测、反证条件和实验映射；`researchctl.py audit-theory` 未通过时不得进入实验协议。
- 理论通过后调用 `experiment-design`，把全部核心预测映射为可反证的设计与预先分析计划；通过 `audit-protocol` 后冻结协议。冻结完成只表示“准备执行”，不会自动启动试点、GPU 或外部任务。
- 用户要求继续执行时，进入试点和主实验前阅读[实验迭代规则](references/experimental-iteration.md)。正式协议冻结后，探索性分析与确认性实验必须分开。进入 Pilot 前用 `authorize-execution` 登记当前协议版本的用户指令证据；所需资源权限还必须与冻结设计中的 `required_permissions` 一致。登记只落实已有授权，不得凭 Skill 自行授予执行权限。
- `artifact-building` 和 `report-writing` 负责生产，`artifact-validation` 和 `report-review` 负责验收，不能由“文件已经存在”冒充正在执行的生产阶段。
- `report-writing` 与 `report-review` 使用 `paper-development`：先冻结被证据支持的声明，再迭代论文论证、图表、复现说明和模拟审稿。实验数量多不等于论文完整；每项实验必须服务于主张、竞争解释或外部效度。
- 申请 `complete` 前先运行 `python agent/runtime/research/audit.py iterative research/<topic-slug>`；控制平面还会执行不可绕过的完成门禁。结构审计通过不等于科学结论已通过同行评议。
- 所有阶段转换、关键决策、协议冻结、实验和 run 都通过控制平面登记；不得只修改 Markdown 假装状态已经推进。
- 实证进度由已登记并可核验的运行终局和产物推导；进入 Pilot 或主实验本身不改变实证状态。主实验需要当前协议的 `experiments/pilot-gate.json`，其中引用的 Pilot run 必须执行成功且产物通过哈希核验。
- 控制平面分别记录 Proposal 决策、新颖性、实证进度和执行就绪度。`Proposal decision: pass` 只代表实验前论证成立；`Empirical status: not-run`、`Execution readiness: designed` 可以与其同时成立。

## 回退与停止

- 新工作推翻新颖性：返回最早受影响的范围、文献或 `direction-audit` 阶段，保留原方向及排除原因。
- 理论无法产生区别于竞争解释的预测：返回问题或方向阶段。
- 试点发现指标无效、任务饱和、方差不可控或实现不可核验：修订协议并重新试点，不进入主实验。
- 主实验反驳假设：分析反例和边界；负结果具有信息价值时形成结论，不得通过未记录的指标、样本或超参数改动追逐正结果。
- 证据冲突：提出能区分解释的定向实验；若资源不足，标记 `blocked` 或限定结论。
- 当核心问题得到支持、反驳或被证明在当前资源下不可判定，且剩余实验不再实质改变结论时停止。不得把投稿接收或指标提升作为唯一完成条件。

外部付费算力、受限数据、人类参与研究、向外部系统提交作业或公开发布不因本 Skill 自动获得授权。
