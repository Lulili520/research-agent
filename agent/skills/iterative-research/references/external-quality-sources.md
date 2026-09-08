# 外部质量依据

使用时须联网重新核验目标会议当届规则；以下来源只提供流程设计依据。

- NeurIPS Paper Checklist：要求论文主张与理论/实验支持范围一致；若包含理论结果，应陈述完整假设并提供完整证明；实验需说明复现、统计不确定性和计算资源。https://neurips.cc/public/guides/PaperChecklist
- NeurIPS 2026 Reviewer Guidelines：评估主张是否由理论或实验支持、是否提供新数据/结论/理论或实验方法；理论论文不因缺少实验自动受罚。https://neurips.cc/Conferences/2026/ReviewerGuidelines
- ICLR 2026 Reviewer Guide：核心问题是论文是否为社区带来足够价值和新知识，并检查问题、文献定位与重要性。https://iclr.cc/Conferences/2026/ReviewerGuide
- ICML 2026 Reviewer Instructions：原创性与重要性必须相对已有工作论证；技术正确不等于贡献重要，二者需分开评价。https://icml.cc/Conferences/2026/ReviewerInstructions
- The AI Scientist：展示 idea→code→experiment→paper→simulated review 的闭环，但自动审稿分数不能替代真实科学验证。https://arxiv.org/abs/2408.06292
- Towards end-to-end automation of AI research：后续同行评议版本说明自动系统可以产出可评审工作，但与最佳人类科研仍有差距，支持保留独立证据门禁和人工授权边界。https://doi.org/10.1038/s41586-026-10265-5
- From Automation to Autonomy：把科学发现分为问题定义、假设、实验、分析、结论与迭代，支持可回退状态机而非一次生成论文。https://aclanthology.org/2025.emnlp-main.895/
- ResearchAgent：以论文图谱和实体关系为 Idea 提供文献依据，并使用协作 reviewer 迭代问题、方法与实验设计；本项目只吸收证据驱动候选和角色隔离，不把 reviewer 自评当门禁。https://github.com/JinheonBaek/ResearchAgent
- AI-Researcher：采用相关论文检索、Idea 生成、去重、Proposal 展开、排序和筛选，并逐一比较相似论文；其执行后排序可能变化，支持把 Proposal 判断与实验结果状态分离。https://github.com/NoviScl/AI-Researcher
- The AI Scientist 源码：通过多轮 reflection 和 Interestingness/Feasibility/Novelty 字段生成候选，但受代码模板和自评分限制；适合候选生成，不适合作为最终科学审计。https://github.com/SakanaAI/AI-Scientist
- Agent Laboratory：展示文献、实验和报告的端到端组织及人工反馈价值；其执行环节属于 Proposal 之后，不应被折叠进实验前通过标准。https://github.com/SamuelSchmidgall/AgentLaboratory

流程只吸收这些来源支持的原则，不复制其系统设计，也不把会议 checklist、GitHub star、自动评分或模拟审稿分数当成录用预测器。
