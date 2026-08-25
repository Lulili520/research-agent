# 量化模型的 Agent 性能变化：评测方法文献调研

检索截止：2026-08-25  
调研性质：结构化叙述性综述，不宣称系统综述或穷尽覆盖。

## 核心结论

这个问题已经有一项高度直接的正式工作，但研究空间没有被封闭。ICML 2025 的 ACBench 是目前本次检索中最核心的论文：它首次系统比较压缩模型在动作执行、工作流生成、长上下文和真实 Agent 应用中的能力。其重要发现是，4-bit 量化在工作流和工具使用子任务上的平均下降可能只有约 1%-3%，但在真实应用任务上可达到 10%-15%。因此，“静态能力基本保持”不能推出“Agent 闭环能力基本保持”。[ACBench official record](https://proceedings.mlr.press/v267/dong25k.html)

现有证据进一步表明，评测不能只看最终成功率和每 token 延迟。2026 年的 *Quantization Inflates Reasoning* 显示 INT4/INT3 可能在准确率不变时增加推理 token 与重复步骤，从而抵消速度收益；Mix-Quant 则显示量化 prefill 与量化 decoding 的风险不同，说明“4-bit 模型”这一粗标签不足以描述 Agent 的实际精度配置。[Token Inflation](https://arxiv.org/abs/2606.25519)；[Mix-Quant](https://arxiv.org/abs/2605.20315)

综合来看，最明确的文献缺口是：缺少一套对同一模型进行配对、能定位首次轨迹分歧、考虑重复运行可靠性、并以“每个成功任务的端到端成本”衡量收益的量化 Agent 评测方法（C1-C8）。

## 研究版图

### 1. 传统量化评测

ICML 2024 的 QLLM-Eval 广泛评测了权重、激活和 KV Cache 量化，覆盖 11 个模型家族以及基础 NLP、涌现能力、可信性、对话和长上下文任务。它奠定了“不能只测困惑度”的方法论基础，但仍然没有环境动作、工具执行、恢复和完整 episode 状态。[QLLM-Eval](https://proceedings.mlr.press/v235/li24bb.html)

### 2. 直接的压缩 Agent 评测

ACBench 将问题推进到 Agent 层面：

- T-Eval：规划、推理、检索、理解、指令跟随、复核；
- WorfBench：函数调用、具身、问题求解和开放场景的工作流生成；
- LongBench、LongGenBench、Needle-in-the-Haystack：长上下文；
- AgentBoard：ScienceWorld、Jericho、PDDL、工具查询和操作。

论文还发现 JSON 结构化输出比字符串输出更容易因压缩退化，量化通常比剪枝更能保留工具能力，不同模型架构的敏感度差异显著。其局限包括未测试 QAT、只覆盖兼容 vLLM 的方法、使用默认量化配置且未探索 group size；对完整轨迹中误差如何累积的归因也仍然不足。[ACBench full text](https://arxiv.org/abs/2505.19433)

### 3. 隐藏成本和阶段敏感性

*Quantization Inflates Reasoning* 提出 CTIR，用量化模型相对全精度模型的推理 token 增量描述隐藏成本。其意义在于：量化模型即使答对，也可能因为更长、更重复的推理而使单个成功任务更慢、更贵。该工作包含 agentic tool-use，但主要分析推理轨迹长度，并非完整的 Agent 动作错误分类。[paper](https://arxiv.org/abs/2606.25519)

Mix-Quant 把 Agent 的输入密集型工作负载拆成 prefill 与 decode：仅对 prefill 使用 NVFP4、decode 保持 BF16，在其设置下可获得最高 3 倍 prefill 加速并基本保留任务能力。它提醒后续调研和实验必须报告量化位置；峰值 prefill 加速也不能被直接写成端到端 Agent 加速。[paper](https://arxiv.org/abs/2605.20315)

## Agent 评价方法提供的补充

量化研究应吸收而不是重新发明成熟的 Agent 评价思想：

- T-Eval 将工具利用拆成多个阶段，可用于定位量化后哪个能力先退化。[ACL 2024 paper](https://aclanthology.org/2024.acl-long.515/)
- AgentBoard 不仅报告成功率，还报告任务进度，适合发现“没有完成但接近完成”的变化；它是 ICLR 2024 正式论文。[OpenReview](https://openreview.net/forum?id=09Y7J22N9c)
- τ-bench 使用最终数据库状态验证任务，并用 pass^k 衡量多次运行的一致可靠性；论文在 ICLR 2025 发表。量化差异可能小于随机 rollout 方差，因此这个指标尤其关键。[τ-bench](https://openreview.net/forum?id=roNSXZpUDN)
- BFCL 覆盖 AST、可执行调用、拒绝不合适工具以及后续多轮版本，适合作为结构化调用层指标，但不能单独代表完整 Agent。[BFCL](https://gorilla.cs.berkeley.edu/blogs/8_berkeley_function_calling_leaderboard.html)
- 2026 年 Agent 评测综述指出领域正转向更真实、持续更新的评测，并仍缺少成本效率、安全、鲁棒性和细粒度可扩展方法。这与量化 Agent 的缺口高度一致。[ACL Findings survey](https://aclanthology.org/2026.findings-acl.1330/)

## 方法分类

现有文献可以组织为四层：

1. **模型层**：困惑度、静态推理、对话、长上下文；适合筛除明显失效的量化配置，不能证明 Agent 可用。
2. **动作层**：工具选择、参数/schema、调用执行、拒绝无效工具；能定位结构化输出退化。
3. **轨迹层**：计划、进度、状态保持、重复、首次分歧、错误恢复；目前在量化文献中覆盖最弱。
4. **任务与系统层**：最终环境状态、pass^k、总 token、总延迟、能耗和成功任务成本；现有工作通常只覆盖其中一部分。

## 当前可以成立的研究空白

### 缺口一：缺少配对轨迹归因

ACBench 能说明某类任务下降，却较少回答全精度与量化模型从哪一步开始分歧，以及该分歧属于选错工具、参数错误、环境误读、计划偏移还是恢复失败。逐步 T-Eval 与 AgentBoard progress 提供组件，但尚未形成量化专用的配对归因框架。

### 缺口二：缺少可靠性统计

Agent 是随机闭环系统。单次成功率差异可能来自采样、环境或用户模拟器，而非量化。τ-bench 已证明重复运行一致性本身是关键能力，但 ACBench 的主要结论没有形成以配对重复 rollout 和置信区间为中心的方法。

### 缺口三：成本定义仍不完整

每 token 加速不等于每任务加速。Token Inflation 揭示推理 token 可能增加；Agent 还会产生额外工具调用、重试和无效步骤。文献尚未统一报告“完成一个成功 episode 的显存、时间、能耗和调用成本”。

### 缺口四：量化轴没有被统一控制

权重、激活、KV Cache、prefill 和 decoding 的敏感性不同。现有论文分散地研究这些轴，缺少在同一模型、Agent scaffold、任务和资源预算下的统一比较。

### 缺口五：benchmark 外推不足

静态函数调用、工作流生成和真实交互的退化幅度不同。一个量化配置在 BFCL 或 T-Eval 上稳定，不代表在长周期 web、软件工程或数据库状态任务中稳定。现有直接证据集中于有限模型家族和环境。

## 代表论文阅读顺序

1. [ACBench / ICML 2025](https://proceedings.mlr.press/v267/dong25k.html)：与你的问题最直接，先理解它覆盖什么以及没有覆盖什么。
2. [QLLM-Eval / ICML 2024](https://proceedings.mlr.press/v235/li24bb.html)：理解量化评测变量和传统任务版图。
3. [T-Eval / ACL 2024](https://aclanthology.org/2024.acl-long.515/)：学习工具能力的逐步分解。
4. [AgentBoard / ICLR 2024](https://openreview.net/forum?id=09Y7J22N9c)：学习闭环进度分析。
5. [τ-bench / ICLR 2025](https://openreview.net/forum?id=roNSXZpUDN)：学习最终状态验证和重复运行可靠性。
6. [Quantization Inflates Reasoning / 2026 preprint](https://arxiv.org/abs/2606.25519)：理解准确率以外的隐藏成本。
7. [Mix-Quant / 2026 preprint](https://arxiv.org/abs/2605.20315)：理解推理阶段和量化位置的差异。

## 影响力与证据说明

本交叉方向形成时间很短，因此没有把原始引用数作为排序依据。ACBench 和 QLLM-Eval 的优先级来自正式 ICML 主会发表、公开代码和对问题的直接性；T-Eval、AgentBoard、τ-bench 的优先级来自正式会议发表及其指标被后续 Agent 评测采用；两个 2026 年预印本被标为“新兴高潜力”，不称为已经建立长期影响的论文。

按照 CCF 第七版目录，本报告中的 ICML、ICLR、ACL 主会论文属于相应人工智能方向的 A 类会议范围；ACL Findings 与 arXiv 预印本没有沿用主会 CCF 标签。CCF 类别仅用于 venue 元数据，不代表单篇论文质量。[CCF official catalog](https://www.ccf.org.cn/Academic_Evaluation/By_category/)

## 调研限制

- 本次为问题导向的结构化调研，不是注册或双人筛选的系统综述。
- 对 2026 年预印本只能做新兴证据判断，不能宣称长期影响或稳定复现。
- 没有把不同论文的数字拼成排行榜，因为模型、量化方法、任务、解码和硬件条件不兼容。
- 社区量化排行榜和个人测试仅用于发现线索，没有作为核心科研结论依据。
