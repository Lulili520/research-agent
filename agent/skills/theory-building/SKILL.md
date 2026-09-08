---
name: theory-building
description: 将已通过新颖性审计的计算机科学 Proposal 转化为机制模型、竞争解释、区分性预测、反证条件和实验映射；用于正式实验设计前的理论阶段，不用于用公式包装直觉或替代实验证据。
---

# 理论与机制构建

理论的作用是压缩解释空间并产生可能失败的预测，不是证明方案必然有效。先确认 `researchctl.py audit-proposal` 通过，再开展本阶段；该通过只表示实验前科学合同成立，不表示任何经验假设已被支持。

## 构建

1. 读取 Proposal 的形式命题和证明义务，并阅读[形式证明标准](references/formal-proof-standard.md)。正式顶会理论型模式必须完成至少一个与核心贡献直接相关的非平凡定理/命题；若范围文件明确选择经验/系统模式，才允许仅使用因果/机制图、资源模型或系统不变量，并必须明确不声称数学证明。
2. 阅读[理论质量与竞争解释](references/theory-quality.md)，定义构念、可观测量、适用域和关键假设；明确从操纵到中介过程再到结果的机制链。
3. 至少提出一个能解释同一现象的竞争机制。为主机制和竞争机制生成不同的方向、交互、边界或中介预测；如果所有可能结果都能解释，理论不合格。
4. 阅读[预测—实验映射](references/prediction-mapping.md)，为每个预测分配稳定 `P<n>`，关联 `H<n>` 和 `C<n>`，写明观测量、主机制预期、竞争机制预期、适用域、反证条件和所需实验操纵。
5. 使用[理论产物模板](assets/theory.md)生成 `theory/theory.md`，并维护 `theory/claims.jsonl`、`theory/predictions.jsonl` 和 `theory/audit.md`。关键推导引用已有证据定位；无法由现有证据支持的部分标为待检验假设。理论随后必须进入 `experiment-design` 的[理论—实验多轮推演](../experiment-design/references/iterative-theory-experiment.md)，由实验的可识别性和资源约束反向检查理论是否可检验。
   理论型模式还必须生成 `theory/formalization.md`、`theory/proofs.md`、`theory/proof-audit.md` 和 `theory/counterexamples.jsonl`。证明审计与理论作者隔离；数值测试、模型检查或有限枚举只能作为反例搜索或补充验证，不能冒充一般性证明。
6. 理论正文完成后分别交给隔离的 `proof-skeptic` 与 `theory-skeptic`。前者检查定义、量词、假设、引理依赖、推导有效性、边界与反例；后者检查构念可观测性、循环论证、竞争解释、预测区分性、隐藏自由度和资源内可检验性。二者不得继承 Builder“应该通过”的结论，也不得由理论生成者自签 `pass`。
7. 理论审计通过后更新 `outputs/02-验证后Proposal.md`，明确写入 `Proposal decision: pass`、`Novelty status: audited`、`Empirical status: not-run` 以及理论设计审计结论；任一门禁未通过时保留 `revise|reject|pending`，不得使用“理论已证明”或“实验验证成功”措辞。面向用户的完整理论推导、竞争解释和实验论证统一写入 `outputs/03-理论分析与实验探究.md`。

## 审计与回退

运行 `researchctl.py audit-theory research/<topic>`。审计只能验证结构和可追溯性；还需以怀疑性视角检查循环论证、不可观测构念、混淆变量、隐藏自由度以及与最近近邻理论是否实质相同。

- 没有竞争解释或区分性预测：留在本阶段。
- 机制依赖 Proposal 未声明的新贡献：返回 Proposal 审计。
- 代理变量不能有效测量构念：修订构念或标记 `blocked`。
- 预测无法映射为现实资源内的实验：缩小声明或返回方向选择。

只有 `theory/audit.md` 为 `Theory gate: pass` 且机器审计通过，才能进入 `experiment-protocol`。
