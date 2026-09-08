# 多轮 Proposal 推演流程

## 目的

Proposal 不是一次生成的文本，而是一个在证据压力下逐步收缩或扩展的可证伪主张集合。六类专门推演保证每种认知任务被执行；五轮 `full-proposal-cycle` 保证修改后的完整 Proposal 被重新检查，而不是把六项检查各做一次就宣布收敛。重复搜索、改写措辞、增加引用数量不算独立迭代。

## 内部产物

保存在课题 `.research/proposal/`，不增加用户输出目录复杂度：

- `candidates.jsonl`：候选方向及淘汰状态。
- `claims.jsonl`：原子贡献声明、证据、最近邻和状态。
- `rivals.jsonl`：竞争机制及其区别性观测。
- `threats.jsonl`：按 `proposal-fatal|empirical-dependency|paper-stage` 分层的新颖性、识别、测量、可行性和外部效度威胁。
- `iterations.jsonl`：每轮问题、输入、发现、决策和改动。
- `depth-breadth.md`：研究问题树、贡献层级、深度链、确认性核心、必要边界、最小外部效度和扩张停止规则。
- `proposal.md`：当前唯一有效版本；被否定版本不放进 `outputs/`。

用户侧只保留当前 `outputs/02-验证后Proposal.md`，其中必须如实展示审计状态。

## 迭代记录最小字段

`iterations.jsonl` 每行至少包含：

```json
{
  "iteration_id": "I01",
  "proposal_id": "P1",
  "cycle_type": "candidate-comparison",
  "question": "本轮具体要推翻或区分什么？",
  "inputs": ["C12", "paper-x"],
  "finding": "本轮得到的证据结论",
  "decision": "retain|revise|merge|reject|return-to-search",
  "proposal_changed": true,
  "change_summary": "撤回、收缩或新增了什么",
  "unresolved": ["仍未解决的威胁"],
  "next_action": "下一轮为何必要"
}
```

`proposal_changed=true` 时，检索稳定性计数归零。`false` 必须说明本轮使用了什么新证据或新反证角度；没有新压力的“无变化”不计数。

## 五轮完整 Proposal 循环

顶会目标研究至少执行五轮 `cycle_type=full-proposal-cycle`。每轮都要重新审查 Q/K/M/D/C、研究问题树、最近邻、深度链、必要广度、识别、资源和论文证据包，并填写 `round`、`breadth_review`、`depth_review`、`novelty_review`、`mechanism_review`、`identification_review` 与 `paper_review`。五轮的主要攻击面依次为：

1. 问题重要性、候选组合和必要子问题；
2. 功能等价、新颖性边界和范围过窄/过宽；
3. 机制、竞争解释、假设去除和反例；
4. 决定性证据、测量、必要边界、外部效度与资源；
5. 完整论文论证和不继承 Builder 结论的反方整合。

五轮不是把同一段文字循环五次。每轮必须记录新的证据或压力、具体改动和仍未解决的威胁；未改变时也要说明经何种独立攻击仍保持。当前 Proposal ID 必须拥有连续的 1–5 轮，旧版本记录只能用于追踪。

六类专门推演记录与五轮完整循环可以引用相同证据，但承担不同审计语义：前者证明每种认知操作确实做过，后者证明每次实质修改后完整论证仍成立。不得把一条记录复制成两类来凑数。

## 六类必需推演轮

### 1. 候选竞争轮 `candidate-comparison`

不要过早选中第一个看似新颖的想法。通常生成至少三个具有不同知识贡献的候选，而不是同一方法的参数变体。逐个回答：

- 它要解释什么现象，而不仅是提升什么分数？
- 最近强工作留下的是缺失实验，还是尚未识别的科学问题？
- 差异若成立，会改变什么理论或系统设计结论？
- 最关键的正结果、负结果分别意味着什么？
- 最小可行证据是否能在资源内取得？

根据科学价值、不可约差异、可证伪性、识别可行性、负结果价值和资源风险排序候选。评分只能辅助排序；任何功能等价、不可证伪或不可识别的致命问题都能否决高分候选。其余候选标为 rejected 或 reserve，并记录原因。

每个保留候选须先写成 `Q-K-M-D-C`：精确问题、知识主张、机制、决定性检验和科学后果。无法说明负结果会改变什么知识判断的候选不能进入下一轮。

### 2. 等价工作碰撞轮 `novelty-collision`

把候选拆成问题、机制、方法、协议和证据贡献五类原子声明。对每项寻找名称不同但功能等价的工作，并回答：

- 最近邻是否已经回答同一个知识问题？
- 差异只是数据集、模型、规模、指标或模块组合吗？
- 最近邻未做的内容是否有科学后果，还是普通 future work？
- 两项工作若得到相同结果，本 Proposal 还会新增什么知识？

发现覆盖核心知识贡献的工作时，应拒绝或重新立项；不得通过添加第三个数据集、更多模型或新名称维持原主张。

### 3. 机制与反证轮 `mechanism-falsification`

为保留候选绘制最小因果结构或机制链，明确 treatment、mediator、outcome、confounder 和 selection。具体回答：

- 核心构念怎样操作化，何时不成立？
- 至少两个竞争解释能否产生相同表面结果？
- 哪个观测模式能区分主机制和每个竞争解释？
- 哪项结果会直接反证，而不是仅“效果较小”？
- 机制是否依赖不可观察的模型自述？能否用行为或干预交叉验证？

每个主要假设必须关联 prediction、rival pattern、falsifier 和实验映射。无法产生区别性预测的机制不能进入 Proposal。

### 4. 识别与可行性轮 `protocol-feasibility`

先尝试设计能推翻理论的最小实验，再讨论完整 benchmark。具体检查：

- 处理变量是否真正独立，操纵检验是什么？
- clean、sham、omission、negative control 和 positive control 是否足以排除混杂？
- 数据、划分、环境重放、许可证和真值是否可用？
- 主要指标是否直接测量构念，而不是便利代理？
- 样本量由什么方差和最小效应决定？
- 最简单基线是否可能解释全部收益？
- GPU、时间、人工标注和失败重跑是否在预算内？

本轮只审查设计是否原则上可操作、可识别且资源上存在实现路径，不要求操纵检查、效应量或运行成本已经观测。若只能通过挑选处理成功案例、依赖不可复核 judge 或无法匹配关键混杂来成立，应回到机制轮或拒绝方向；若纸面设计成立而实际表现尚未知，则登记为 `empirical-dependency`。

### 5. 完整论文架构轮 `paper-architecture`

把候选当作一篇完整顶会论文而不是单个实验，检查计划中的一句话核心主张、理论/机制支柱、决定性实验、最强基线、消融、外部效度、负结果价值和 Artifact 路径能否形成闭环。明确哪些是未来必需证据，哪些只是可选扩展；此时不要求实验和 Artifact 已经完成。如果论证只能依赖一个无识别力的演示实验，或必须靠堆模型/数据集制造分量，返回候选、机制或可行性轮。

本轮输出 `Paper sufficiency: insufficient|promising|proposal-ready`。它评价计划中的论证是否完整，不预测录用或实验结果。

### 6. 独立反方轮 `adversarial-review`

由 `adversarial-novelty-reviewer` 在不继承 Builder“希望保留”的结论下完成。它应优先寻找：功能等价工作、被隐藏的宽泛主张、循环论证、无法识别的中介、弱基线、不可实现资源假设和无价值负结果。

反方轮可以输出 `pass`、`revise` 或 `reject`。`revise` 后必须返回对应轮次重新推演；反方审查不能由 Proposal 作者用措辞修改自行关闭。审计者只对实验前可知事项下结论，不得因尚无效应量、显著性、跨模型结果或 Artifact 而拒绝 Proposal。

## 迭代状态机

```text
证据地图
  -> 候选竞争
  -> 等价工作碰撞
  -> 机制与反证
  -> 识别与可行性
  -> 完整论文架构
  -> 五轮完整 Proposal 循环
  -> 独立反方
       ├─ reject -> 回到候选竞争或停止
       ├─ revise -> 返回被指出的轮次
       └─ pass -> 新颖性稳定检索
                    ├─ changed -> 返回等价工作碰撞
                    └─ 两轮 no/no -> audited 候选
```

迭代不是单向流水线。任何新论文改变最近邻、任何预测无法区分 rival、任何关键控制不可实施，都必须回退。

## 允许升级的门禁

只有同时满足以下条件，Proposal 才可标为 `audited`：

- 候选竞争、等价工作碰撞、机制与反证、识别与可行性、完整论文架构、独立反方六类轮次都有完整记录；
- 当前 Proposal ID 具有连续五轮有效 `full-proposal-cycle`，且每轮重审深度与必要广度；
- `depth-breadth.md` 的深度链、研究问题树、确认性核心、必要边界、最小外部效度和扩张停止规则完整，`Depth gate` 与 `Breadth gate` 均为 `pass`；
- 当前原子贡献声明均有证据、最近邻差异和科学后果；
- 每个核心机制至少有一个 rival、区别性预测和明确 falsifier；
- threat register 中没有未解决的 `proposal-fatal`；`empirical-dependency` 和 `paper-stage` 已明确交接但允许保持 `open|deferred`；
- 独立反方决策为 `pass`；
- 当前 Proposal 的 `Proposal decision: pass` 与 `Paper sufficiency: proposal-ready`；
- 最后连续两轮定向检索均为 `Proposal changed: no`，且 `Saturation: reached`。

达到文献数量或完成六类轮次不自动代表通过。若核心知识贡献在迭代中被覆盖，应保留审计记录、替换当前用户 Proposal，并回到候选竞争。
