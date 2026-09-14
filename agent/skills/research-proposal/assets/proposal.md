# 〔具体研究问题〕：研究方案

> Proposal ID／版本／证据截止日期。明确正式方案或待修订草案；编辑日期与取证日期分开。

## 1. 当前方案介绍

开头直接用普通语言介绍方案本身：研究对象、具体问题、拟做的处理或方法、比较方式，以及最终希望获得什么知识。首次出现的术语就地解释；必要时使用有出处的短例子或明确标注的构造例子。读完这一节应能复述“准备做什么、为什么、怎样判断”。

若用户要求结论先行，先概括拟提出的方案和拟回答的问题，不用“保留问题／继续修订”等审查处置代替方案介绍。区分已选定设计与仍在竞争的收紧方向；待检验假设和条件性预期不能写成已发生的实验结果。

介绍结束后用短段交代主要局限及尚未实验等状态；详细四轴状态、版本历史和技术门禁集中在第8节或内部记录。不可隐去会推翻方案的缺口，但不要让状态字段占据读者理解方案之前的位置。

## 2. 问题依据与科学价值

解释对象、条件、有来源的现象及现有解释，附关键来源定位；说明回答后改变什么认识或决策。真实案例与构造例子区分，不用单个例子证明普遍性。

## 3. 当前研究主张与适用范围

用可读叙述呈现Q（问题）、K（待检验知识主张）、M（机制或理论依据）、D（决定性检验）、C（科学后果），随后给出必要子问题。

交代分析单位、可观察终点、确认性核心、必要边界、最低外部效度、不负责事项、扩张触发与停止条件。形式研究按需给出命题、假设、证明义务与反例，不把完整内部表单复制进正文。

关键示意图说明信息流与证据链，紧接对应叙述；设计图不能冒充已运行系统。

## 4. 已有工作与拟新增贡献

集中比较最强近邻、已覆盖内容、拟增加的原子知识主张及其科学后果。未发现先例不等于创新已成立；已撤回主张只保留影响当前判断的摘要，详细历史移入附录或内部记录。

## 5. 材料与判定依据

说明构念如何操作化，材料版本、信息条件、选择方式、合法比较及可靠终点。理论、系统、测量研究选用相应证明对象或验证材料，不强制训练数据。

区分已经具备、尚待核验和无法取得的条件。记录机制假设、最强竞争解释及判定失效条件。

## 6. 决定性检验设计

| 待区分主张或解释 | 处理／对照及固定项 | 区分性预测 | 材料与判定位置 | 无法判定的条件 |
|---|---|---|---|---|

解释基线、预算、误差或统计处理、必要广度与反证规则。按研究类型采用实验、证明或系统验证；没有实际结果时全部标为设计。所有解释都预测同样涨点的比较不构成决定性检验。

## 7. 可能结果及允许得出的结论

此处是条件性结果解释，不是已发生的结果。

| 预先定义的结果模式 | 允许的知识结论 | 禁止的外推 |
|---|---|---|
| 支持／正向 | | |
| 反驳／零效应 | | |
| 混合／依赖条件 | | |
| 无法判定 | | |

## 8. 验收缺口、可行性与下一动作

| 状态轴 | 当前判断 | 依据或限制 |
|---|---|---|
| Proposal decision | pass / revise / reject | |
| Novelty status | exploratory / provisional / audited | |
| Empirical status | not-run / pilot / tested | |
| Execution readiness | designed / deployable / blocked | |

文稿判断与机器门禁不一致时明确区分。

区分proposal-fatal、empirical-dependency和paper-stage问题；列出最可能改变判断的下一证据动作与恢复／停止条件。实际效应未知不因not-run本身否决设计。

简要交代资源估算、已具备资源、授权边界及适用的伦理约束。集中放置技术审查状态：Theory mode、Paper sufficiency、Depth gate、Breadth gate、当前七项证据验收及独立审查位置（proposal/acceptance.json等）。不以结构完整代替通过，不要求固定轮数。

## 附录与内部索引（按需要）

详细候选竞争、声明—证据映射、版本变化、独立意见闭合、完整论文论证包和深度广度审查链接到内部记录。附录不得藏匿会改变开头结论的关键反证。已有章节能够清楚表达时不再复制表单或另设同义章节。

### 内部运行时字段（不复制到用户报告）

内部`proposal/proposal.md`在可读正文后保存下列字段，按当前真实证据填写具体内容或对应正文位置；缺口如实写明。保留运行时字段名称，不能以表格替代要求行首字段的机器契约，也不能用位置索引冒充科学验收。用户报告不必与内部文件逐字相同，但科学主张、状态和证据必须一致。

```text
Topic:
Proposal ID:
Search cutoff:
Proposal decision:
Novelty status:
Empirical status:
Execution readiness:
Paper sufficiency:
Depth gate:
Breadth gate:
Knowledge question (Q):
Knowledge claim (K):
Mechanism (M):
Decisive test (D):
Scientific consequence (C):
Constructs:
Assumptions:
Mechanism:
Competing explanations:
Predictions:
Falsifiers:
Central thesis:
Research-question tree:
Contribution stack:
Confirmatory core:
Boundary program:
External-validity minimum:
Expansion stop rule:
Positive outcome:
Null outcome:
Mixed outcome:
Inconclusive outcome:
```

formal另保留`Formal statement:`、`Proof obligations:`、`Proof sketch:`、`Counterexample search:`、`Empirical corollaries:`。未到该阶段不生成虚假证明或通过状态。
