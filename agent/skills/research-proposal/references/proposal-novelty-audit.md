# Proposal 新颖性审计

先把 Proposal 分解成可检索的原子声明：研究问题、核心机制、方法组合、训练或推理设置、评测协议和证据贡献。对每项构造直接名称、同义词、旧术语、相邻领域术语和功能等价描述。

至少执行：精确组合检索、拆分组件检索、任务×机制检索、最近年份检索、核心近邻的前后向引文、相关作者后续工作、benchmark 与 artifact 检索。将最接近的工作写入 `literature/nearest-neighbors.md`，逐项记录相同点、不同点、差异的科学后果以及它是否推翻 Proposal。

`proposal-audit.md` 必须包含检索截止日期、数据库、查询族、核心全文近邻、潜在先例、尚未解决的威胁和新颖性状态。审计关注“已有工作是否实质实现同一知识贡献”，不能只比较标题和模块名称。

方案生成和反方审计必须产物隔离。Proposal Builder 生成候选后，由 `adversarial-novelty-reviewer` 只接收 scope、原子贡献声明、检索材料和论文证据，不接收“希望通过”的结论。它在 `novelty-review.md` 记录 Reviewer role、Reviewer stance、Equivalent-work criterion、Adversarial findings、Claim withdrawals、Unresolved threats、Independence statement 和 Decision。发现等价工作或最后一轮改变 Proposal 时，Decision 不能为 `pass`。

新颖性状态：

- `exploratory`：只有初步搜索，不得进入确认性实验。
- `provisional`：已完成多源检索与近邻全文比较，但仍有重要来源或冲突待处理。
- `audited`：覆盖和饱和门禁通过，未发现实质等价工作；仍只能表述为“在所列范围和截止日期内未发现”。
