---
name: iterative-research
description: 从用户给定的计算机科学 topic 出发，持续完成相关工作调研、创新方向审计、理论建模、实验协议、执行分析与论文级交付；用于明确要求开展或完成研究的长期任务，不用于只要文献综述或方向建议的请求。
---

# 迭代科研

将研究视为可回退的证据状态机，而不是以正结果为目标的线性流水线。默认使用简体中文记录决策、失败和结论；官方标题、标识符、代码符号与指标保留原文。

## 启动

1. 先调用 `research-framing` 将用户 topic 转成有边界的问题空间并通过 `audit-scope`。缺少的约束若不改变研究方向，可先采用保守假设并记录；会改变数据、算力、研究对象或外部授权时再请求用户决定。
2. 阅读[Research runtime contract](references/runtime-contract.md)，用 `researchctl.py init` 初始化机器状态；参考[状态摘要模板](assets/state.md)维护 `control/state.md`，但机器事实源是 `control/state.json`。不得覆盖已有项目，每次运行先验证事件链并从当前阶段恢复。
3. 根据研究类型选择证据标准。算法/模型、工程系统、benchmark、实证研究、人类参与研究、理论研究和系统综述不得套用同一实验模板。

## 状态机

```text
topic
  -> problem-framing
  -> literature-mapping
  -> proposal-development / direction-audit
  -> theory-building
  -> experiment-protocol
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

- `literature-mapping` 先调用 `research-proposal`；它复用 `review-protocol`（按需）、`scholarly-search`、`paper-analysis` 和 `evidence-synthesis`，形成 50–100 篇已核验语料、20–30 篇核心全文精读和 Proposal，不得把简短调研报告当作完成。
- `direction-audit` 对 Proposal 做反向新颖性审计。只有语料覆盖、检索饱和、最近近邻差异、机制、可区分预测和反证条件通过 `researchctl.py audit-proposal` 后，才进入 `theory-building`。
- Proposal 通过后调用 `theory-building`，并阅读[理论—实验契约](references/theory-to-experiment.md)。形式化证明不是所有研究的硬要求，但必须有明确机制、竞争解释、区分性预测、反证条件和实验映射；`researchctl.py audit-theory` 未通过时不得进入实验协议。
- 理论通过后调用 `experiment-design`，把全部核心预测映射为可反证的设计与预先分析计划；通过 `audit-protocol` 后冻结协议。冻结完成只表示“准备执行”，不会自动启动试点、GPU 或外部任务。
- 用户要求继续执行时，进入试点和主实验前阅读[实验迭代规则](references/experimental-iteration.md)。正式协议冻结后，探索性分析与确认性实验必须分开。
- `artifact-building` 和 `report-writing` 负责生产，`artifact-validation` 和 `report-review` 负责验收，不能由“文件已经存在”冒充正在执行的生产阶段。
- 申请 `complete` 前先运行 `powershell -File agent/audit-iterative-research.ps1 research/<topic-slug>`；控制平面还会执行不可绕过的完成门禁。结构审计通过不等于科学结论已通过同行评议。
- 所有阶段转换、关键决策、协议冻结、实验和 run 都通过控制平面登记；不得只修改 Markdown 假装状态已经推进。

## 回退与停止

- 新工作推翻新颖性：返回 `direction-audit`，保留原方向及排除原因。
- 理论无法产生区别于竞争解释的预测：返回问题或方向阶段。
- 试点发现指标无效、任务饱和、方差不可控或实现不可核验：修订协议并重新试点，不进入主实验。
- 主实验反驳假设：分析反例和边界；负结果具有信息价值时形成结论，不得通过未记录的指标、样本或超参数改动追逐正结果。
- 证据冲突：提出能区分解释的定向实验；若资源不足，标记 `blocked` 或限定结论。
- 当核心问题得到支持、反驳或被证明在当前资源下不可判定，且剩余实验不再实质改变结论时停止。不得把投稿接收或指标提升作为唯一完成条件。

外部付费算力、受限数据、人类参与研究、向外部系统提交作业或公开发布不因本 Skill 自动获得授权。
