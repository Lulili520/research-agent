# Literature set: quantized LLM agent evaluation

Status: core set verified  
Search cutoff: 2026-08-25

| ID | Paper | Year/venue | Relation | Publication status | Decision | Reason |
|---|---|---|---|---|---|---|
| ACBench | [Can Compressed LLMs Truly Act?](https://proceedings.mlr.press/v267/dong25k.html) | 2025 / ICML main / CCF-A | Direct | Proceedings + full text + code | include, core | Directly evaluates quantization and pruning on agentic abilities |
| QLLMEval | Evaluating Quantized Large Language Models | 2024 / ICML | Adjacent | Proceedings | include | Broad quantization evaluation and methodology baseline |
| MixQuant | [Mix-Quant: Quantized Prefilling, Precise Decoding for Agentic LLMs](https://arxiv.org/abs/2605.20315) | 2026 / arXiv | Direct/system | Preprint | include, emerging | Agent-workload-specific phase-aware quantization |
| TokenInflation | [Quantization Inflates Reasoning](https://arxiv.org/abs/2606.25519) | 2026 / arXiv | Direct/metric | Preprint | include, emerging | Adds hidden test-time cost and agentic tool-use evidence |
| ThinkSLM | ThinkSLM: Towards Reasoning in Small Language Models | 2025 / EMNLP | Adjacent | Proceedings | include selectively | Quantization and reasoning robustness context |
| AgentQuest | AgentQuest: A Modular Benchmark Framework to Measure Progress and Improve LLM Agents | 2024 / NAACL Demo | Evaluation context | Proceedings | include selectively | Trajectory/progress-oriented agent metrics |
| TEval | [T-Eval](https://aclanthology.org/2024.acl-long.515/) | 2024 / ACL main / CCF-A | Evaluation context | Proceedings + code | include, core context | Decomposes tool utilization step by step |
| AgentBoard | [AgentBoard](https://proceedings.neurips.cc/paper_files/paper/2024/hash/877b40688e330a0e2a3fc24084208dfa-Abstract-Datasets_and_Benchmarks_Track.html) | 2024 / NeurIPS Datasets and Benchmarks Track | Evaluation context | Proceedings + code | include, core context | Multi-turn environments and progress-rate analysis |
| TauBench | [tau-bench](https://openreview.net/forum?id=roNSXZpUDN) | 2025 / ICLR main / CCF-A | Evaluation context | Proceedings + code | include, core context | Final-state verification and repeated-trial pass^k |
| AgentEvalSurvey | [A Survey on Evaluation of LLM-based Agents](https://aclanthology.org/2026.findings-acl.1330/) | 2026 / ACL Findings | Survey context | Proceedings | include selectively | Current taxonomy and gaps; not labeled as ACL main CCF-A |
| ABC | [Establishing Best Practices for Building Rigorous Agentic Benchmarks](https://openreview.net/forum?id=LIfAFmR4sX) | 2026 / OpenReview | Benchmark validity | Preprint/submission status to verify | include, important direction | Separates task validity, outcome validity and reporting; challenges benchmark scores as ground truth |
| ReliabilityBench | [ReliabilityBench](https://arxiv.org/abs/2601.06112) | 2026 / arXiv | Reliability context | Preprint | include selectively | Repeated execution, perturbation and controlled tool/API failures already exist for general agents |
| MIRAGE | [Beyond Blind Following](https://aclanthology.org/2026.eacl-long.310/) | 2026 / EACL main | Robustness context | Proceedings | include, important direction | Tests imperfect, outdated and mismatched guidance in dynamic environments |
| AgentSafetyBench | [Agent-SafetyBench](https://arxiv.org/abs/2412.14470) | 2024 / arXiv | Safety context | Preprint/formal status to verify | include selectively | Defines agent-specific safety risks and failure modes |
| AgentAuditor | [AgentAuditor](https://proceedings.neurips.cc/paper_files/paper/2025/hash/3dc85735f6e2fcf093e67b134fa00d21-Abstract-Conference.html) | 2025 / NeurIPS main / CCF-A | Evaluator quality | Proceedings + code | include selectively | Stepwise safety evaluator and evaluator benchmark |
| TheAgentCompany | [TheAgentCompany](https://proceedings.neurips.cc/paper_files/paper/2025/hash/0d744742f6fac4d1134c019b7cef3c8a-Abstract-Datasets_and_Benchmarks_Track.html) | 2025 / NeurIPS D&B | Deployment realism | Proceedings + environment | include selectively | Consequential, long-horizon digital-work tasks |
| AgentIF | [AgentIF](https://proceedings.neurips.cc/paper_files/paper/2025/hash/51bb3a8a33610a25aae074bfc51b1b1f-Abstract-Datasets_and_Benchmarks_Track.html) | 2025 / NeurIPS D&B | Constraint following | Proceedings + code/data | include selectively | Realistic long instructions and complex agent constraints |

Impact interpretation: ICML/ICLR/ACL venue status supports visibility but is not a paper-quality score. The direct intersection is young, so ACBench is labeled a central recent paper, while the two 2026 preprints are emerging rather than established high-impact work.
