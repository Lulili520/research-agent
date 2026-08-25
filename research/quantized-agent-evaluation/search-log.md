# Search log: quantized LLM agent evaluation

Search/update date: 2026-08-25

Scope: Research that evaluates how post-training quantization or low-precision inference changes LLM agent capabilities, plus adjacent work needed to judge evaluation coverage. Agent capabilities include workflow/planning, tool or function calling, long-context state, multi-turn interaction, environmental action, coding agents, and end-to-end task completion.

Assumptions:

- “量化模型” means a quantized LLM used as the policy/reasoning model inside an agent, not an agent that performs quantization.
- Compression studies including pruning are retained only when they report separable quantization results.
- Primary research is prioritized; community benchmarks are contextual evidence, not substitutes for peer-reviewed claims.
- CCF category will be verified only for formally published venues and will not be used as a paper-quality score.

## Eligibility

Include direct empirical studies of quantized models on agentic tasks; comprehensive quantized-LLM evaluations containing agent prerequisites; agent-evaluation papers that define relevant metrics or failure analysis; and recent phase-aware/system work specifically motivated by agent workloads.

Exclude papers where “quantization agent” means an LLM automating deployment, papers applying QLoRA only as a training convenience without comparing agent behavior, and ordinary quantization benchmarks with no relevance to agent evaluation except as clearly labeled background.

## Queries executed

| Platform | Exact query | Date | Notes |
|---|---|---|---|
| Web/arXiv | `site:arxiv.org quantized LLM agent evaluation tool use quantization` | 2026-08-25 | Direct intersection discovery |
| Web/OpenReview | `site:openreview.net LLM quantization agent benchmark tool calling` | 2026-08-25 | Submission and full-text discovery |
| Web/ACL Anthology | `site:aclanthology.org quantization LLM reasoning evaluation agent` | 2026-08-25 | Adjacent evaluation research |
| Web/PMLR | `site:proceedings.mlr.press LLM quantization reasoning benchmark` | 2026-08-25 | Formal quantization evaluation papers |
| Web | `"Can Compressed LLMs Truly Act" conference ACBench` | 2026-08-25 | Seed verification |
| Web | `"Agent Compression Benchmark" ACBench paper` | 2026-08-25 | Seed expansion |
| Web | `"quantized" "agentic capabilities" LLM benchmark` | 2026-08-25 | Direct intersection expansion |
| Web | `"quantization" "tool use" LLM agents benchmark` | 2026-08-25 | Tool-use specific expansion |

## Initial candidates

- Dong et al. (2025), *Can Compressed LLMs Truly Act?* / ACBench - direct seed.
- Li et al. (ICML 2024), *Evaluating Quantized Large Language Models* - foundational adjacent evaluation.
- Lu et al. (2026), *Mix-Quant* - emerging phase-aware agentic quantization.
- Lian et al. (2026), *Quantization Inflates Reasoning* - emerging hidden-cost evaluation including agentic tool use.
- Srivastava et al. (EMNLP 2025), *ThinkSLM* - adjacent reasoning robustness study.
- AgentQuest and recent surveys of LLM-agent evaluation - evaluation-method context.

## Limitations

- Dynamic citation metrics have not yet been collected.
- Publication status and venue metadata remain to be verified for preprints.
- The direct intersection is young; “high impact” will require age-aware evidence rather than raw citation ranking.
