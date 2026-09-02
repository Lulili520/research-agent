# 语料与饱和规则

## 三层语料

- 候选池：查询或引文扩展发现的记录，可以超过 100 篇；只用于筛选。
- 纳入语料：50–100 篇，每篇具有稳定身份、版本关系、访问级别、纳入理由和与 topic 的关系，用于领域地图。
- 核心近邻：20–30 篇全文精读，包含最接近 Proposal 的工作、最新强基线、潜在先例、关键矛盾证据和主要实验协议，用于关键方法与新颖性结论。

`literature/corpus.jsonl` 每行至少包含：`source_id`、`title`、`year`、`stable_url`、`identity_verified`、`screening_status`、`access_level`、`role`、`relevance_reason`。纳入记录的 `screening_status` 为 `included`；核心近邻的 `role` 为 `core` 且 `access_level` 为 `full-text`。

## 覆盖矩阵

用 `literature/coverage.md` 显式检查：问题定义、方法家族、关键数据与 benchmark、理论或机制、评测协议、效率与资源、失败案例、最近强工作和相邻方向。某一格没有文献时，区分真实缺口、术语遗漏和来源不可访问。

## 饱和判据

广域发现不计入稳定性补检。每轮定向补检在 `search-log.md` 使用独立 `Round:` 块，记录查询、数据库、日期、发现数、去重后新增数、纳入数、直接竞争者以及 `Proposal changed: yes|no`。若为 `yes`，说明撤回或修改了什么，并将稳定性计数清零。只有最后连续两轮均为 `Proposal changed: no`，且两轮都覆盖精确组合、功能等价描述和最近工作/引文链，才能写 `Saturation: reached`；否则必须写 `Saturation: not-reached`。候选池可以超过 100 篇，但正式纳入集合必须控制在 50–100 篇；达到上限仍未饱和时，应收紧问题边界或继续筛选候选，不能绕过饱和要求。
