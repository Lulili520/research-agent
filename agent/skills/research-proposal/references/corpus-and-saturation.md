# 语料与饱和规则

## 三层语料

- 候选池：查询或引文扩展发现的记录，可以超过 100 篇；只用于筛选。
- 纳入语料：默认预算 50–100 篇，每篇具有稳定身份、版本关系、访问级别、纳入理由和与 topic 的关系，用于领域地图。
- 核心近邻：默认预算 20–30 篇全文精读，包含最接近 Proposal 的工作、最新强基线、潜在先例、关键矛盾证据和主要实验协议，用于关键方法与新颖性结论。

以下路径均相对项目 `.research/`。

`review/literature/corpus.jsonl` 每行至少包含：`source_id`、`title`、`year`、`stable_url`、`identity_verified`、`screening_status`、`access_level`、`role`、`relevance_reason`。纳入记录的 `screening_status` 为 `included`；核心近邻的 `role` 为 `core` 且 `access_level` 为 `full-text`。

## 覆盖矩阵

用 `review/literature/coverage.md` 显式检查：问题定义、方法家族、关键数据与 benchmark、理论或机制、评测协议、效率与资源、失败案例、最近强工作和相邻方向。某一格没有文献时，区分真实缺口、术语遗漏和来源不可访问。

## 饱和判据

范围饱和依据关键近邻、必要分支、竞争术语和反向证据的实际处理，而非固定稳定轮数。每项补检记录查询、来源、日期、实际返回、认识变化及未解决项；没有观察到的数量不填造。当前版本没有尚可取证且可能改变中心主张的关键缺口，经独立复核后才写`Saturation: reached`；否则保持`not-reached`。`coverage.md`记录范围、截止日期、取舍理由和直接近邻处理，绑定到当前验收。实质变化重新打开受影响要求，不累计或清零“稳定计数”。阶段性范围成立不证明绝对无人做过；实验前和论文审查前仍按时效刷新近邻。详见[验收要求](acceptance-criteria.md)。

`access_level: full-text` 只说明全文可访问，不证明已深入分析。卡片须按 `paper-analysis` 记录实际深度和未解决问题。当前 runtime 对核心语料仅检查身份、全文标记与非空卡片等结构，不能据此自签精读完成。未饱和时如实记录 `Coverage status: not-saturated`，不为格式检查改为 saturated。
