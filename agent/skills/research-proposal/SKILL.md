---
name: research-proposal
description: 从用户给定的计算机科学 topic 出发，完成大规模相关工作调研、新颖性反向检索和可证伪研究 Proposal；用于正式启动研究或要求高可信创新方案，不用于简短选题建议。
---

# 研究 Proposal

目标不是用论文数量装饰想法，而是建立足以推翻错误创新判断的证据地图，再形成有理论依据、可证伪且资源可行的实验前科学合同。Proposal 通过不表示理论已被证明、实验已成功或论文会被录用。默认输出简体中文，论文官方标题和标识符保留原文。

## 调研

1. 先冻结 topic 的问题边界、相邻概念、时间与文献范围、研究类型、资源限制以及可能推翻创新性的等价工作定义。
   顶会目标研究同时读取[统一研究质量标准](../iterative-research/references/top-tier-research-standard.md)，使用统一顶会质量标准；不得按目标会议挑选更宽松的科学门禁。
2. 阅读[语料与饱和规则](references/corpus-and-saturation.md)，调用 `scholarly-search` 建立候选池和去重后的纳入语料。50–100 篇身份已核验论文是默认检索预算，不是硬性质量指标；真正门禁是问题边界内的覆盖、直接近邻完整性与检索饱和。偏离默认数量须记录理由，不得为了达标纳入明显无关记录。
3. 语料必须覆盖奠基工作、方法谱系、最近两个完整发表周期的前沿工作、直接竞争者、相邻问题、负面或矛盾证据以及 benchmark/评测工作。通过关键词、同义词、前后向引文、作者后续工作和最近相关工作迭代检索。
4. 对所有纳入论文建立结构化最小卡片；通常选择 20–30 篇最接近 Proposal 的核心论文，使用 `paper-analysis` 完成全文精读。实际数量由直接竞争者、最新强基线、潜在先例、关键矛盾证据和主要实验协议的覆盖决定；关键事实和新颖性判断不得仅依赖摘要。
5. 按[语料与饱和规则](references/corpus-and-saturation.md)记录定向补检与停止依据。广域查询不计稳定轮，关键证据未核验不能因新增数量少而宣布饱和。

## Proposal 构建与审计

1. 先完整读取[Proposal 实验前科学门禁](references/proposal-gate-contract.md)，再用 `evidence-synthesis` 形成问题谱系、方法分类、失败模式、证据冲突和候选方向；不要先写 Proposal 再寻找支持性论文。
   论文证据用于知识判断；GitHub 仓库、issue、release、环境文件和复现脚本用于核验实现路径、许可和工程约束，不得用 star、README 自述或代码存在替代科学新颖性证据。
2. 正式 Proposal 必须先阅读[Proposal 深度—广度审计](references/proposal-depth-breadth-audit.md)，建立一个中心问题、2–5 个必要子问题、贡献层级、深度链、确认性核心、必要边界和最小外部效度。把各扩展轴标为 `must-have|conditional|optional|out-of-scope`；不得用变量数量制造广度，也不得把单一实验误写成完整论文。
3. 随后阅读并执行[多轮 Proposal 推演流程](references/iterative-proposal-development.md)。六类否定性检查必须覆盖，顶会目标还须完成当前 Proposal ID 下连续五轮 `full-proposal-cycle`；每轮都重审完整 Q/K/M/D/C、深度、广度、新颖性、识别与论文证据包，只是主要攻击面不同。措辞润色、重复检索和旧 Proposal 的轮次不能计入。
4. 阅读[Proposal 新颖性审计](references/proposal-novelty-audit.md)，为每个候选寻找最可能推翻它的工作；逐项比较问题、机制、训练/推理设置、数据、指标、资源假设和贡献。
5. Proposal Builder 与 `adversarial-novelty-reviewer` 分离：前者不得替后者填写结论。反方审计器生成 `.research/proposal/novelty.md`，明确等价工作判据、最强反例、撤回声明、未解决威胁、独立性说明和决策。
6. 每个保留候选先写成 `Q-K-M-D-C`：精确问题、拟建立的知识主张、机制、决定性检验和科学后果。Proposal 必须包含问题与重要性、研究问题树、最近近邻差异、贡献栈、构念、假设、竞争解释、可区分预测、可反证条件、识别蓝图、确认性核心、必要边界、最小外部效度、结果—贡献矩阵、风险、资源和授权边界。每个关键主张应能回溯到 claim register、深度—广度审计和至少一轮专门压力测试。
   此外必须给出计划中的“完整论文论证包”：一句话知识主张、理论/机制支柱、最小决定性实验、强基线、必要外部效度、不同结果的知识价值以及 Artifact 路径。这里审查的是论证路径是否完整，不要求实验、操纵检查、稳健性或 Artifact 已经完成。
7. 新颖性分开评估问题、机制、方法实例、实验协议和证据贡献。只有关键差异具有科学后果时才能保留，不能把模块拼接、换数据集或尚未比较的涨点称为创新。
   新想法可以与已有研究共享问题、理论基础、数据、组件或评测工具；“相关”不是拒绝理由。只有核心知识主张和决定性证据与最近邻功能等价时才拒绝；部分重叠时须明确继承项、新增项及新增项会改变的科学判断。
8. 输出前按[Proposal 模板](assets/proposal.md)和[深度—广度模板](assets/depth-breadth.md)完成内部 `proposal/proposal.md`、`proposal/depth-breadth.md` 和 `proposal/audit.md`，再生成或更新面向用户的 `outputs/01-文献调研总结.md`。该报告必须包含三层：对实际纳入集合的领域级综合分析；对实际深入精读的核心论文逐篇撰写“研究动机—方法介绍—总结归纳”；详细解释仍存在的问题、证据不足原因、最近邻边界和可验证方式。不得用摘要改写、批量一句话列表或论文卡链接代替精读正文。可同步生成 `outputs/02-验证后Proposal.md` 草案，但必须展示四轴状态以及研究问题树、论证深度、必要广度和完整论文证据包。最后连续两轮稳定性检索、五轮全流程、必需推演轮和反方审计未通过时，新颖性不能标为 `audited`；尚未运行实验时必须标为 `Empirical status: not-run`，不能因此把科学上成立的 Proposal 降级。
9. Proposal 审计使用 `Paper sufficiency: insufficient|promising|proposal-ready`，并独立记录 `Depth gate: pass|revise` 与 `Breadth gate: pass|revise`。它检查计划中的核心主张能否组织成完整论文，而不是预测录用或要求结果已经出现。只有 Proposal、新颖性、深度、广度和论文充分性全部通过才进入理论阶段；否则返回最早受影响的候选、调研、机制或识别轮。
10. 阅读[新颖性—深度—理论闭环](references/novelty-depth-theory-loop.md)。所有 Proposal 都要给出可反证机制和竞争解释；仅当 scope 的 `Theory mode` 为 `formal` 时，才必须给出非平凡形式命题、假设、证明义务、证明草图、理论近邻、反例与经验推论。`empirical-system` 模式改用因果机制、系统不变量或资源模型及区分性预测，不得把经验规律包装为证明。

威胁必须在 `proposal/threats.jsonl` 标为 `proposal-fatal|empirical-dependency|paper-stage`。只有未解决的 `proposal-fatal` 阻止 Proposal；实际效应、操纵结果、跨模型稳健性、真实运行量和 Artifact 复现属于后续状态，必须保留但不得提前判定。

数量偏离 50–100 篇纳入或 20–30 篇精读时，在 `.research/review/literature/coverage.md` 解释问题边界、直接近邻覆盖、数量取舍和饱和证据。数量本身既不能使 Proposal 通过，也不能单独使其失败；覆盖缺口、关键近邻未全文核验或未饱和才是失败原因。
