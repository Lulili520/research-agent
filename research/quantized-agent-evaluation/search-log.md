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

## Research-gap anti-search update (2026-08-26)

Purpose: search for work that would invalidate candidate novelty claims.

| Candidate | Exact query | Closest results | Effect on gap |
|---|---|---|---|
| Paired trajectory attribution | `"quantized" LLM agent "trajectory" evaluation paired full precision` | Generic trajectory evaluation; no directly equivalent paired quantization study found | Retain as provisional, not “first” |
| Reliability | `LLM agent quantization repeated rollouts reliability variance evaluation` | ReliabilityBench and broader agent reliability science already cover repeated execution, perturbations and tool faults without quantization as the causal factor | Narrow to quantization-conditioned reliability surface |
| Successful-task cost | `quantized LLM agent cost per successful task end-to-end evaluation` | Token Inflation covers hidden token cost; community work uses cost per successful task | Narrow to peer-reviewed, controlled episode-level Pareto and cost decomposition |
| Safety/robustness | `quantization LLM agent safety robustness tool use evaluation` | Agent-SafetyBench, MIRAGE and AgentAuditor cover agent safety/robustness without controlled quantization comparisons | Retain as provisional translation gap |
| Benchmark validity | agentic benchmark task/outcome validity searches | Agentic Benchmark Checklist finds task/outcome validity failures in major benchmarks | Add validity-aware quantization evaluation; do not assume benchmark scores are ground truth |

Important related directions checked: fine-grained trajectory evaluation, task/outcome validity, consequential long-horizon tasks, instruction constraints, imperfect guidance, safety/security, evaluator bias, contamination, cost and efficiency, and reproducibility.

Novelty status remains provisional because a full multi-database forward/backward citation audit with measured result counts has not yet been completed. The permitted statement is: “截至 2026-08-26，在已记录检索范围内未发现直接等价工作。”

## Research-direction agent search (2026-08-26)

Purpose: identify how published or publicly documented research agents construct and filter scientific directions.

| System | Query / primary source | Direction-construction mechanism | Adopted lesson |
|---|---|---|---|
| ResearchAgent (NAACL 2025) | `ResearchAgent iterative research idea generation scientific literature large language models paper`; ACL Anthology | Seed paper + academic graph + cross-paper concept store; structured problem/method/experiment generation; iterative ReviewingAgents | Expand an evidence neighborhood before ideation and require structured critique/revision |
| The AI Scientist | `The AI Scientist idea generation novelty check arXiv Sakana AI`; official repository and project page | Generate ideas relative to an executable codebase; score feasibility/interestingness; iterative Semantic Scholar novelty queries | Tie ideas to executable resources and search specifically for substantial overlap |
| AI Co-Scientist | `Google AI co-scientist research hypothesis generation paper`; Google Research and Nature record | Generate-debate-evolve; specialized agents; tournament ranking; web/tool grounding | Compare and evolve a candidate portfolio instead of accepting the first plausible gap |
| Agent Laboratory | `Agent Laboratory using LLM agents as research assistants arXiv` | Literature review -> experiment -> report, with user feedback at each stage | Preserve explicit human approval gates; reported human feedback improved output quality |

Primary sources inspected:

- ResearchAgent: https://aclanthology.org/2025.naacl-long.342/
- The AI Scientist project and novelty-check implementation: https://sakana.ai/ai-scientist/ and https://github.com/SakanaAI/AI-Scientist/blob/main/ai_scientist/generate_ideas.py
- AI Co-Scientist: https://research.google/blog/accelerating-scientific-breakthroughs-with-an-ai-co-scientist/ and https://doi.org/10.1038/s41586-026-10644-y
- Agent Laboratory: https://arxiv.org/abs/2501.04227

These systems motivate workflow design but do not make their own novelty decisions reliable ground truth. The local agent therefore adds a closest-work delta, explicit invalidation conditions, recorded anti-gap queries, paper-quality appraisal, and pre-submission novelty refresh.
