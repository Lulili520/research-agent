# 如何评测量化导致的 LLM Agent 性能变化？

检索截止：2026-08-26

调研性质：问题导向的结构化文献调研，不是注册、双人筛选或穷尽性的系统综述。

新颖性状态：**provisional**。所有“未发现”均限于 [search-log.md](search-log.md) 记录的范围。

## 核心回答

评测量化模型的 Agent 性能，不能只比较静态准确率、最终成功率或 tokens/s。可靠方案应覆盖四层：

1. **模型层**：基础推理、对话、长上下文和量化对象；
2. **动作层**：工具选择、参数/schema、调用执行和无效动作；
3. **轨迹层**：首次语义分歧、计划/状态变化、错误传播和恢复；
4. **任务与系统层**：最终环境状态、重复 rollout 分布、总 token/延迟/重试和每成功 episode 成本。

直接证据已表明，静态能力保持不能直接外推为闭环 Agent 能力保持（C1）。ACBench 在其设置中报告，4-bit 量化在工作流/工具类任务上的平均损失约 1%–3%，在真实应用任务上约 10%–15%（C2）。但现有研究仍不能联合回答“量化首先改变哪个语义决策、如何传播、Agent 是否恢复、验证器是否正确判分”（C6、C8）。

因此，当前最值得研究的不是再造综合排行榜，而是建立一种**有效性校准的全精度—量化配对轨迹评测方法**（C9–C10）。

## 文献版图

### 一般量化评测

[QLLM-Eval（ICML 2024）](https://proceedings.mlr.press/v235/li24bb.html)系统比较权重、激活和 KV cache 量化，覆盖基础 NLP、涌现能力、可信性、对话和长上下文。它说明量化效果需要跨模型、精度和任务评估，但没有环境动作、工具执行、恢复或完整 episode 状态，因而不能单独证明 Agent 可用（C1、C5）。

### 直接的压缩 Agent 评测

[ACBench（ICML 2025）](https://proceedings.mlr.press/v267/dong25k.html)是本次检索中最直接的正式论文。它将 action execution、workflow generation、long context 和 AgentBoard 应用纳入评测，并显示闭环应用可能比工具/工作流子任务更敏感（C2）。其不足是聚合分数尚不能给出稳定的首次语义分歧、错误传播与恢复机制（C3、C6）。

### 隐藏成本与量化位置

[Quantization Inflates Reasoning（2026 预印本）](https://arxiv.org/abs/2606.25519)报告低比特模型可能在最终准确率保持时产生更多、更重复的推理 token；单 token 更快因此不必然意味着每次任务成本更低（C4）。

[Mix-Quant（2026 预印本）](https://arxiv.org/abs/2605.20315)区分 prefill 与 decode 精度，说明“4-bit 模型”是过粗的实验标签。评测必须明确量化对象和阶段，并区分 prefill 峰值加速与完整 Agent episode 加速（C5）。两篇均为预印本，不能表述为已经得到长期复现。

### 可迁移的 Agent 评测方法

- [T-Eval（ACL 2024）](https://aclanthology.org/2024.acl-long.515/)提供工具能力的阶段化分解；
- [AgentBoard（NeurIPS 2024 Datasets and Benchmarks）](https://proceedings.neurips.cc/paper_files/paper/2024/hash/877b40688e330a0e2a3fc24084208dfa-Abstract-Datasets_and_Benchmarks_Track.html)用 progress rate 补充最终成功率；
- [τ-bench（ICLR 2025）](https://openreview.net/forum?id=roNSXZpUDN)强调最终状态检查和重复运行一致性；
- ReliabilityBench 等近期工作已研究通用 Agent 的随机性、扰动和工具故障。

这些方法说明量化评测应加入过程诊断和重复 rollout，但它们没有直接证明量化效应。“多运行几次”不是新贡献；可研究的是量化与随机性、任务长度或工具故障的交互（C6–C7）。

## 当前证据边界

| 结论 | 证据状态 | 合理表述 |
|---|---|---|
| 静态指标不足以证明 Agent 能力保持 | 较强 | 可作为研究动机（C1） |
| 闭环任务可能有更大损失 | 单篇直接正式证据 | 限定为 ACBench 设置（C2） |
| 表示形式和架构存在异质性 | 直接但待补精确定位 | 作为待验证机制（C3） |
| token 膨胀会削弱效率收益 | 新兴直接证据 | 限定为预印本结果（C4） |
| 量化位置/阶段是必要控制变量 | 正式相邻 + 新兴证据 | 作为实验原则（C5） |
| 配对轨迹归因无直接等价工作 | 初步反缺口检索 | 仅作日期/范围受限的 provisional 判断（C9） |

## 主方向：有效性校准的配对轨迹归因

### 精确研究空白

在同一基础模型、任务初态、Agent scaffold 和受控解码条件下，现有证据尚不能可靠识别：量化首先改变了哪个**语义动作**，该变化是否被环境反馈放大或被 Agent 恢复，以及 benchmark 验证器是否对量化输出产生差异性误判（C6、C8–C9）。

这属于“机制 + 测量有效性”问题，而不是“某篇论文少测一个指标”。它将科学推断从“量化后掉多少分”推进到“为什么掉分，以及观测差异是否真实”。

### 最近工作与不可约差异

| 最近工作 | 已经解决 | 仍需解决 |
|---|---|---|
| ACBench | 证明压缩会影响多层 Agent 能力 | 配对首次语义分歧、传播和恢复 |
| T-Eval / AgentBoard | 阶段能力与过程进度 | 把量化作为受控干预并连接最终环境状态 |
| Agentic Benchmark Checklist | task/outcome validity 审计思想 | 量化/全精度条件下的差异性误判 |
| Token Inflation | 推理长度和隐藏成本 | 完整 action–tool–state 轨迹及成功 episode 成本 |

不可约差异不是增加更多模型或指标，而是把**受控量化干预、语义轨迹对齐、失败传播和验证器校准**放在同一个可证伪设计中。

### 可证伪假设

- H1：控制基础模型、任务和 scaffold 后，首次语义分歧集中于少数动作类型，而非均匀出现。
- H2：首次分歧的位置和类型，比静态指标或总 token 数更能预测最终失败。
- H3：部分表面退化来自验证器的差异性误判；校准后效应量或排序会改变。
- H4：局部分歧并不必然导致失败，错误恢复是连接量化干预与最终结果的中介变量。

### 最小可行实验

1. 选择 2–3 个可本地复现、具有确定性最终状态检查的 Agent benchmark，先审计 task/outcome validity。
2. 固定基础模型、prompt/scaffold、工具版本与硬件，比较 BF16 和至少两个 PTQ 条件；明确记录量化对象和阶段。
3. 对相同任务实例进行多种子 rollout，保存 observation、原始输出、解析动作、工具结果、环境状态、错误和恢复事件。
4. 以环境状态和“语义动作等价类”而非 token 严格相等对齐轨迹；用盲法人工复核校准自动错误分类器。
5. 报告配对效应及置信区间、首次分歧时间、分歧类型、失败传播/恢复概率，以及验证器修复前后的变化。
6. 将 token、prefill/decode 时间、重试和工具调用汇总为“每成功 episode 成本”，但不构造不透明总分。

### 结果价值与风险

- 若存在稳定敏感动作，可为选择性精度保护或量化感知训练提供目标。
- 若分歧不集中，可否定“修复单一模块即可恢复 Agent”的假设。
- 若验证器偏差显著，可纠正 benchmark 推断；若不显著，则提供有效性证据。
- 主要风险是 token 轨迹快速失配、自动 judge 偏差和实验因子爆炸；应用语义/状态对齐、人工校准和功效导向设计控制。

## 两个备选方向

### 量化条件下的可靠性响应面

研究量化方法/位宽与 rollout 随机性、提示扰动、工具故障和任务 horizon 的交互，报告方差、尾部失败、worst-group 或 CVaR。通用 Agent 可靠性已经有人研究，贡献必须来自量化条件及交互效应（C7）。新颖性：**中等、provisional**。

### 成功任务成本与阶段精度配置

在统一硬件和成功约束下，比较权重/KV/prefill/decode 精度对完整成功 episode 的能力—成本 Pareto，并用轨迹失败与重试解释成本来源。若只是画 Pareto 曲线，新意较弱；只有导出可复现规律或自适应精度策略时，才适合作为系统向主贡献（C4–C5）。新颖性：**中等偏低至中等、provisional**。

## 不建议独立立项

- **笼统的安全 + 鲁棒性评测**：相邻工作密集且构念不同；目前只适合作为高后果子集验证。
- **统一多测几种量化位置**：与 QLLM-Eval、Mix-Quant 重叠；除非解释轨迹机制或产生新策略，否则只是实验扩展。
- **新综合总分或排行榜**：容易掩盖成功率、可靠性、成本和有效性之间的权衡。

## 新颖性边界与立项门槛

截至 2026-08-26，在已记录查询中未发现与主方向直接等价的工作（C9）。这不是“无人做过”的保证。正式立项前必须：

1. 完成 DBLP、Semantic Scholar/OpenAlex、arXiv、OpenReview 和目标会议 proceedings 的查询、分页与结果计数；
2. 完成 ACBench 等最近工作的前向/后向引文链、作者/项目/代码检索；
3. 建立至少 10 篇 closest-work 的 overlap/delta 表，并让独立研究者尝试推翻新颖性；
4. 用小规模实验验证轨迹记录、语义对齐和验证器校准的可靠性；
5. 在投入大规模实验和投稿前分别刷新检索。

完成前不能使用“首次”“从未研究”或“填补空白”等绝对表述。

## 阅读顺序

1. [ACBench / ICML 2025](https://proceedings.mlr.press/v267/dong25k.html)：直接基线。
2. [QLLM-Eval / ICML 2024](https://proceedings.mlr.press/v235/li24bb.html)：量化变量基础。
3. [T-Eval](https://aclanthology.org/2024.acl-long.515/)与 [AgentBoard](https://proceedings.neurips.cc/paper_files/paper/2024/hash/877b40688e330a0e2a3fc24084208dfa-Abstract-Datasets_and_Benchmarks_Track.html)：过程分解。
4. [τ-bench / ICLR 2025](https://openreview.net/forum?id=roNSXZpUDN)：最终状态与可靠性。
5. [Token Inflation](https://arxiv.org/abs/2606.25519)与 [Mix-Quant](https://arxiv.org/abs/2605.20315)：新兴成本和阶段精度证据。

## 限制

- 本调研没有执行注册协议、双人筛选或 PRISMA 流程。
- 部分关键细节尚缺页码/表格级 locator，已标记为 `partial`，没有伪造定位。
- 2026 年工作是预印本，正式发表、独立复现与长期影响尚不确定。
- 不同论文的模型、量化实现、任务和硬件不可直接比较，故不制作跨论文数值排行榜。
- CCF 类别仅用于 venue 元数据，不代表单篇论文质量。

完整证据见 [evidence.md](evidence.md)，检索与反缺口记录见 [search-log.md](search-log.md)，实验化方向卡见 [research-directions.md](research-directions.md)。
