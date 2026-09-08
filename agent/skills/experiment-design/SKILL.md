---
name: experiment-design
description: 将已审计的理论预测转化为可冻结、可复现、能反驳核心声明的计算机科学实验协议；用于实验执行前设计，不执行实验或分析结果。
---

# 实验协议设计

本 Skill 的终点是“协议通过审计并冻结，等待执行”，不启动 Pilot、本地进程、远端 GPU 或外部提交。此时 `Execution readiness` 可从 `designed` 变为 `deployable`，而 `Empirical status` 仍为 `not-run`。

1. 先运行 `researchctl.py audit-theory`。从 `theory/predictions.jsonl` 导入全部核心预测，不得只选择容易获得正结果的预测。随后完整执行[理论—实验多轮推演](references/iterative-theory-experiment.md)，维护 `theory/iterations.jsonl`。
2. 阅读[设计与识别规则](references/design-and-identification.md)，确定实验单元、自变量、因变量、控制、混杂因素、基线、数据划分、污染检查和资源条件。每个 `P<n>` 至少映射到一个可失败实验。
3. 阅读[分析计划规则](references/analysis-plan.md)，在看到主实验结果前冻结主要指标、估计量、不确定性、重复/随机种子、多重比较、排除规则、失败 run、缺失值和停止条件。
4. 生成内部 `experiments/protocol.md`、`experiments/design.json`、`experiments/analysis-plan.md` 和 `experiments/protocol-audit.md`。探索性分析必须与确认性分析分区。`design.json` 显式包含 `required_permissions`（无需额外资源权限时为 `[]`）及 `research_materials`（`mode: external|generated|none`）；外部来源逐项记录 `url`、`version` 和 `selection`，生成或无数据模式记录 `rationale`。
5. 协议审计通过后生成用户交付物 `outputs/03-理论分析与实验探究.md`。报告先给出理论构念、机制推导、竞争解释、区分性预测和反证条件，再逐项说明实验如何支持、削弱或推翻理论。数据与研究材料按实际研究类型说明：使用外部数据时给出官方稳定链接、固定版本方式、具体 split/类别/样本数和改造步骤；使用生成材料时给出生成规则、种子与数量；不使用数据时说明理由与替代验证方式。不设固定数据集数量，不要求无关的课题专用章节。实验或验证部分按研究类型给出处理与对照、随机化、重复、运行量、系统/算法/模型配置、基线、指标、统计或形式验证方法及阶段门禁。不适用项必须说明理由与替代验证方式；不得为了填模板强行引入模型、数据集或经验实验。资源部分量化实际需要的 CPU/GPU/RAM/磁盘、人工工时、日历时间、软件环境、部署步骤和费用；无需 GPU 时明确写 0 或不适用。估算、当前机器已具备、人工需要部署和仍需授权的资源必须分开，不能用“若干数据集”“适量 GPU”等占位描述。
6. 协议正文由 `protocol-skeptic` 隔离审查，重点寻找混杂、泄漏、无效代理指标、不公平预算、低功效设计和可选择停止；`protocol-audit.md` 必须显式记录被审查的 `Protocol ID`、`Protocol version`、Reviewer role 与 Independence statement，并与 `protocol.md`、`design.json` 一致，不能由设计者自签通过。
7. 运行 `researchctl.py audit-protocol`。通过后才运行 `freeze-protocol`；冻结会版本化保存正文、结构化设计、分析计划、审计结论、范围、Proposal、理论和预测的完整文件集合，任何冻结文件改动都必须回到协议阶段升版，并说明哪些 run 受影响。已登记的 run 必须先登记终局，不得在执行阶段原地替换协议。只有理论审计、多轮推演和协议审计均通过时，`outputs/03-理论分析与实验探究.md` 才能写对应 `pass`；此前必须标记为 `pending` 或 `draft`。

若无法构造能区分主机制和竞争解释的设计，返回 `theory-building`；若预算不足以支持最低有效设计，缩小声明或暂停，不用低功效实验制造确定性结论。

执行授权不由协议审计授予。用户明确要求执行后，由编排角色按 [runtime contract](../iterative-research/references/runtime-contract.md) 记录 `authorize-execution`，绑定当前协议版本、文件集合哈希及用户指令证据；冻结新版本后需要针对新版本登记授权。已有用户指令明确涵盖该版本时直接登记，不重复索要确认。
