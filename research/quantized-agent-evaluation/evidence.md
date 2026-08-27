# Evidence matrix：量化导致的 LLM Agent 性能变化

检索截止：2026-08-26

CCF 目录：第七版，2026-08-25 核验；仅对目录覆盖的正式主会使用类别标签。

证据范围：4 篇核心论文全文/实验页面笔记，加 Agent 评测、可靠性与 benchmark 有效性相邻文献。此次不是注册的系统综述。

## 声明账本

| Claim ID | 精确声明 | 类型 | 来源 | 定位 | 访问级别 | 关系 | 证据评价 | 核验 |
|---|---|---|---|---|---|---|---|---|
| C1 | 静态量化任务上的能力保持不足以证明闭环 Agent 能力保持。 | inference | QLLM-Eval；ACBench | 两文摘要；ACBench 实验笔记 | 正式论文全文/记录 | 支持 | 两类评测覆盖互补；结论限于“不能外推” | checked |
| C2 | ACBench 报告：4-bit 量化在其工作流/工具类任务上的平均损失约 1%–3%，在其真实应用任务上约 10%–15%。 | reported | ACBench | Abstract | 正式 ICML 论文全文 | 支持 | 当前最直接证据；不能泛化为所有模型和 Agent | checked |
| C3 | 量化影响具有表示形式、模型架构和任务层级异质性。 | reported + inference | ACBench | Abstract；实验笔记，具体表格待定位 | 正式 ICML 论文全文 | 支持 | 单个直接研究，适合提出机制问题，不足以建立普遍规律 | partial |
| C4 | 仅报告成功率和单 token 速度可能高估低比特推理的实际收益。 | inference | Quantization Inflates Reasoning | Abstract | 2026 arXiv 全文 | 支持 | token inflation 是直接结果；完整 episode 成本是扩展推论 | checked |
| C5 | “4-bit”不是充分实验描述；权重、激活、KV cache、prefill 与 decode 的精度位置需要分别记录。 | inference | QLLM-Eval；Mix-Quant | 两文摘要 | ICML 正式论文 + 预印本全文 | 支持 | 方法论意义强；硬件特定结果尚缺独立复现 | checked |
| C6 | 最终成功率无法定位量化造成的首次行为分歧、传播和恢复。 | inference | ACBench；T-Eval；AgentBoard | ACBench 笔记；相邻论文正式记录/摘要 | 直接 + 相邻证据 | contextual | 覆盖矩阵导出的未解决推断，不是单篇作者结论 | checked |
| C7 | 量化差异需要在重复 rollout 下报告；但“重复运行”本身不是新贡献。 | inference | τ-bench；ReliabilityBench | 正式记录/摘要；预印本摘要 | 相邻证据 | 支持并限制 | 可迁移的是可靠性设计；新意只能来自量化条件及交互 | checked |
| C8 | benchmark 的 task/outcome validity 可能改变观测到的量化效应。 | inference | Agentic Benchmark Checklist | 论文记录/摘要，具体诊断待定位 | 相邻方法证据 | contextual | 在量化 Agent 上仍是待检验假设 | partial |
| C9 | 截至检索日，在已记录范围内未发现将全精度/量化配对 rollout、语义首次分歧、错误传播及验证器校准合并研究的直接等价工作。 | inference | search-log；C1–C8 | 2026-08-26 anti-gap search | 结构化但非穷尽检索 | 支持 | 新颖性为 provisional；缺少完整结果计数和引文链 | checked |
| C10 | 安全、成本、量化位置和通用鲁棒性不宜同时作为独立主创新。 | proposal | C4、C5、C7；相邻安全研究 | 本综合 | 综合推论 | 限制范围 | 它们更适合作为评价轴或专项审计后的备选问题 | checked |

## 核心证据质量

| 来源 | 直接性 | 设计与有效性 | 不确定性/外部有效性 | Artifact | 本报告用途 |
|---|---|---|---|---|---|
| ACBench, ICML 2025 | 最高：直接比较压缩后的 Agent 能力 | 覆盖多层任务，但聚合分数不给出统一机制 | 配置、架构和任务依赖；独立复现有限 | 代码公开 | 直接现象与最近工作基线 |
| QLLM-Eval, ICML 2024 | 中：量化评测基础，不含闭环环境 | 模型/量化轴覆盖广 | 不能观察动作累积、恢复或环境状态 | 代码公开 | 定义量化干预轴和静态基线 |
| Token Inflation, 2026 | 中高：含 agentic tool use 和隐藏成本 | 直接比较低比特与全精度 token 行为 | 预印本；token 长度不等于完整 Agent 成本 | 全文已访问 | 支撑成本维度 |
| Mix-Quant, 2026 | 中高：面向 Agent 工作负载的阶段精度 | 同时测任务质量和 prefill 性能 | 预印本、硬件特定；prefill 加速不等于端到端加速 | 全文已访问 | 支撑量化位置/阶段控制 |
| T-Eval / AgentBoard / τ-bench | 方法相邻 | 提供阶段、进度、最终状态和一致性工具 | 未把量化作为受控干预 | 多数公开 | 迁移评测设计，不作直接效应证据 |

## 可比性约束

现有论文的模型、量化实现、任务、解码和硬件并不统一，因此不能拼接成排行榜。ACBench 的 1%–3% 与 10%–15%只描述其论文内部结果（C2）；Mix-Quant 的峰值 prefill 加速和 Token Inflation 的 token 变化也不能直接换算成统一的端到端 Agent 加速（C4–C5）。

## 未解决证据需求

- 为 ACBench 的结构化输出、架构异质性和限制补齐表格/章节级 locator。
- 精读并定位 Agentic Benchmark Checklist、ReliabilityBench 等相邻论文中需要迁移的方法。
- 完成多数据库可复现结果计数，以及最近工作的前向/后向引文链。
- 在投稿前刷新新颖性检索；在此之前 C9 不得升级为“首创”。
