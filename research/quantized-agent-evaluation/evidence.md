# Evidence matrix: evaluating quantization-induced changes in LLM Agent performance

Search cutoff: 2026-08-25  
CCF catalog: seventh edition; official catalog checked 2026-08-25. CCF labels apply only to main-conference papers.

| Claim ID | Exact claim | Evidence | Relation | Confidence/limitation |
|---|---|---|---|---|
| C1 | Static quantization benchmarks are insufficient to establish Agent performance preservation. | QLLM-Eval covers static/dialogue/long-context classes but not closed-loop action; ACBench finds larger loss on AgentBoard applications than on workflow/tool subtasks. | supports | Strong conceptual and direct empirical support, but benchmark coverage is not exhaustive. |
| C2 | Quantization effects differ sharply by Agent evaluation level. | ACBench reports small average 4-bit losses on workflow/tool use but 10%-15% on real-world applications. | supports | Direct ICML evidence; exact effects are configuration- and benchmark-dependent. |
| C3 | Structured action representation is a quantization-sensitive failure surface. | ACBench reports more severe degradation for JSON than string output. | supports | One direct study; requires replication on modern native function-calling models. |
| C4 | Success/accuracy plus per-token latency can overstate quantization efficiency. | TokenInflation finds accuracy retention alongside longer reasoning and end-to-end cost; tau-bench motivates repeated-trial reliability. | supports/context | Direct but recent preprint for token inflation; agent-level cost needs broader confirmation. |
| C5 | Quantization location/phase matters, not only nominal bit width. | QLLM-Eval separates weights/activations/KV cache; Mix-Quant separates prefill from decoding and reports different sensitivity. | supports | Strong design implication; Mix-Quant is a recent hardware-specific preprint. |
| C6 | Final success alone cannot identify where quantization damages a trajectory. | T-Eval decomposes tool use; AgentBoard provides progress-rate analysis; recent agent-evaluation survey calls for fine-grained scalable evaluation. | contextual support | Evaluation-method evidence is strong, but few papers apply it specifically to paired quantization analysis. |
| C7 | Agent evaluation must report reliability across repeated rollouts. | tau-bench introduces pass^k and reports large consistency gaps even for strong agents. | contextual support | Not a quantization study, but directly establishes stochastic reliability as an Agent property. |
| C8 | The direct literature remains narrow enough that a step-level, paired, cost-aware evaluation gap is defensible. | ACBench is the only verified formal paper in this search that broadly and directly targets compression-induced Agent capability change; two 2026 preprints add token-cost and phase-aware views. | synthesis/inference | Search is structured but not claimed exhaustive; future publications may change this conclusion. |

## Method coverage matrix

| Work | Paired precision baseline | Tool/action | Multi-turn/closed loop | Step diagnosis | Long context | End-to-end cost | Quantization axes |
|---|---|---|---|---|---|---|---|
| QLLM-Eval (ICML 2024) | yes | no | no | no | yes | system metrics, not episode cost | W/A/KV across broad models |
| ACBench (ICML 2025) | yes | yes | AgentBoard subset | T-Eval capability decomposition, limited trajectory attribution | yes | limited | GPTQ/AWQ/SmoothQuant; pruning comparator |
| Token Inflation (2026 preprint) | yes | includes tool use | partly | reasoning length/repetition | not central | yes, token/serving penalty | INT3/INT4 and QAT mitigation |
| Mix-Quant (2026 preprint) | yes | agent benchmarks | agent workload | phase sensitivity, not failure taxonomy | yes | prefill speed; end-to-end distinction needed | NVFP4 prefill, BF16 decode |
| T-Eval / AgentBoard / tau-bench | no quantization comparison | yes | varies; AgentBoard/tau-bench yes | strong complementary metrics | varies | tau-bench reliability; not quantization cost | none |

## Unresolved evidence needs

- Independent replications of ACBench on newer models, native tool-calling templates and multiple serving backends.
- Paired trajectory logs identifying the first divergent action between full-precision and quantized runs.
- Weight, activation, KV-cache, prefill and decode quantization compared under common memory/latency budgets.
- Confidence intervals and repeated-rollout reliability for quantization deltas.
- Cost per successful episode, including longer reasoning, retries, invalid calls and simulator cost.
