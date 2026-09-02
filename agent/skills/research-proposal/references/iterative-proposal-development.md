# 多轮 Proposal 推演流程

## 目的

Proposal 不是一次生成的文本，而是一个在证据压力下逐步收缩的可证伪主张集合。每一轮只承担一种认知任务，必须产生决策变化或明确说明为何不变化。重复搜索、改写措辞、增加引用数量不算独立迭代。

## 内部产物

保存在课题 `.research/proposal/`，不增加用户输出目录复杂度：

- `candidates.jsonl`：候选方向及淘汰状态。
- `claims.jsonl`：原子贡献声明、证据、最近邻和状态。
- `rivals.jsonl`：竞争机制及其区别性观测。
- `threats.jsonl`：新颖性、识别、测量、可行性和外部效度威胁。
- `iterations.jsonl`：每轮问题、输入、发现、决策和改动。
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

## 五类必需推演轮

### 1. 候选竞争轮 `candidate-comparison`

不要过早选中第一个看似新颖的想法。通常生成至少三个具有不同知识贡献的候选，而不是同一方法的参数变体。逐个回答：

- 它要解释什么现象，而不仅是提升什么分数？
- 最近强工作留下的是缺失实验，还是尚未识别的科学问题？
- 差异若成立，会改变什么理论或系统设计结论？
- 最关键的正结果、负结果分别意味着什么？
- 最小可行证据是否能在资源内取得？

根据科学价值、不可约差异、可证伪性、识别可行性、负结果价值和资源风险选择候选。其余候选标为 rejected 或 reserve，并记录原因。

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

若只能通过挑选处理成功案例、依赖不可复核 judge 或无法匹配关键混杂来成立，应回到机制轮或拒绝方向。

### 5. 独立反方轮 `adversarial-review`

由 `adversarial-novelty-reviewer` 在不继承 Builder“希望保留”的结论下完成。它应优先寻找：功能等价工作、被隐藏的宽泛主张、循环论证、无法识别的中介、弱基线、不可实现资源假设和无价值负结果。

反方轮可以输出 `pass`、`revise` 或 `reject`。`revise` 后必须返回对应轮次重新推演；反方审查不能由 Proposal 作者用措辞修改自行关闭。

## 迭代状态机

```text
证据地图
  -> 候选竞争
  -> 等价工作碰撞
  -> 机制与反证
  -> 识别与可行性
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

- 候选竞争、等价工作碰撞、机制与反证、识别与可行性、独立反方五类轮次都有完整记录；
- 当前原子贡献声明均有证据、最近邻差异和科学后果；
- 每个核心机制至少有一个 rival、区别性预测和明确 falsifier；
- threat register 中没有未处理的致命威胁；
- 独立反方决策为 `pass`；
- 最后连续两轮定向检索均为 `Proposal changed: no`，且 `Saturation: reached`。

达到文献数量或完成五轮不自动代表通过。若核心知识贡献在迭代中被覆盖，应保留审计记录、替换当前用户 Proposal，并回到候选竞争。
