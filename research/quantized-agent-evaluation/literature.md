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
| AgentBoard | [AgentBoard](https://openreview.net/forum?id=09Y7J22N9c) | 2024 / ICLR main / CCF-A | Evaluation context | Proceedings + code | include, core context | Multi-turn environments and progress-rate analysis |
| TauBench | [tau-bench](https://openreview.net/forum?id=roNSXZpUDN) | 2025 / ICLR main / CCF-A | Evaluation context | Proceedings + code | include, core context | Final-state verification and repeated-trial pass^k |
| AgentEvalSurvey | [A Survey on Evaluation of LLM-based Agents](https://aclanthology.org/2026.findings-acl.1330/) | 2026 / ACL Findings | Survey context | Proceedings | include selectively | Current taxonomy and gaps; not labeled as ACL main CCF-A |

Impact interpretation: ICML/ICLR/ACL venue status supports visibility but is not a paper-quality score. The direct intersection is young, so ACBench is labeled a central recent paper, while the two 2026 preprints are emerging rather than established high-impact work.
