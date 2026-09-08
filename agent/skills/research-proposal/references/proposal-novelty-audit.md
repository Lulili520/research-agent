# Proposal 新颖性审计

先把 Proposal 分解成可检索的原子声明：研究问题、核心机制、方法组合、训练或推理设置、评测协议和证据贡献。对每项构造直接名称、同义词、旧术语、相邻领域术语和功能等价描述。

至少执行：精确组合检索、拆分组件检索、任务×机制检索、最近年份检索、核心近邻的前后向引文、相关作者后续工作、benchmark 与 artifact 检索。将最接近的工作写入 `literature/nearest-neighbors.md`，逐项记录 `inherited`、`new`、`scientific consequence` 以及它是否推翻 Proposal。

GitHub 检索用于发现论文配套代码、未被论文题名暴露的同类系统、数据与基线实现、许可证、维护状态和已知工程失败。仓库 README、star、fork、issue 数量或代码存在本身不能证明科学新颖性；关键知识声明仍须回到论文、正式文档或可复核原始产物。

`proposal-audit.md` 必须包含检索截止日期、数据库、查询族、核心全文近邻、潜在先例、尚未解决的威胁和新颖性状态。审计关注“已有工作是否实质实现同一知识贡献”，不能只比较标题和模块名称。

相关性与等价性必须分开：共享 topic、任务、数据集、理论来源、模块或实验框架均可接受。对部分重叠的最近邻，分别写明 `inherited`、`new` 与 `scientific consequence`；只有新增部分不能改变任何可证伪判断，或核心主张与决定性证据均已存在时，才判定等价并拒绝。

方案生成和反方审计必须产物隔离。Proposal Builder 生成候选后，由 `adversarial-novelty-reviewer` 只接收 scope、原子贡献声明、检索材料和论文证据，不接收“希望通过”的结论。它必须独立执行至少一组反向检索，并在 `novelty-review.md` 记录 Reviewer role、Reviewer model、Reviewer context isolation、Independent search、Reviewer stance、Equivalent-work criterion、Adversarial findings、Claim withdrawals、Unresolved threats、Independence statement 和 Decision。同一模型只改角色提示不是强独立性，必须如实记录。发现等价工作或最后一轮改变 Proposal 时，Decision 不能为 `pass`；进入实验前及论文审稿前还须刷新检索，新颖性结论始终带范围与截止日期。

两次刷新分别写入 `proposal/novelty-refresh-pre-experiment.md` 与 `proposal/novelty-refresh-pre-paper.md`，至少记录 Search date、Databases、Query families、New nearest neighbors、Claim impact 和 `Refresh decision: pass|return-to-proposal`。出现改变核心声明的近邻时必须回退 Proposal；若合理收缩后仍保留不同知识贡献，可以重新接受碰撞审计，不能只靠措辞变化静默前进。

新颖性状态：

- `exploratory`：只有初步搜索，不得进入确认性实验。
- `provisional`：已完成多源检索与近邻全文比较，但仍有重要来源或冲突待处理。
- `audited`：覆盖和饱和门禁通过，未发现实质等价工作；仍只能表述为“在所列范围和截止日期内未发现”。
