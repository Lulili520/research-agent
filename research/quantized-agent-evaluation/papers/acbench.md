# ACBench

## Identity and access

- Citation: Peijie Dong et al. *Can Compressed LLMs Truly Act? An Empirical Evaluation of Agentic Capabilities in LLM Compression.* ICML 2025, PMLR 267:14169-14202.
- Stable record: https://proceedings.mlr.press/v267/dong25k.html
- Full text: https://arxiv.org/abs/2505.19433
- Code: https://github.com/pprp/ACBench
- Track/type: ICML main conference paper.
- CCF: Artificial Intelligence, A under the seventh catalog (catalog checked 2026-08-25).
- Access level: full experimental HTML plus official proceedings metadata.

## Problem and contribution

The paper argues that perplexity and static NLP tasks do not characterize whether a compressed LLM can act. It introduces ACBench, covering 12 tasks organized around action execution, workflow generation, long-context understanding, and real-world applications. It compares GPTQ, AWQ, SmoothQuant and several pruning methods over 15 models and adds representation/output-gap analyses (ERank, top-k ranking correlation, and energy).

## Experimental coverage

- Action execution: T-Eval decomposes planning, reasoning, retrieval, understanding, instruction following, and review.
- Workflow generation: WorfBench function-call, embodied, problem-solving, and open-grounded tasks.
- Long context: LongBench, LongGenBench, and Needle-in-the-Haystack.
- Real-world AgentBoard tasks: ScienceWorld, Jericho, PDDL, tool query, and tool operation.
- Quantization: AWQ, GPTQ, SmoothQuant; mostly 4/8-bit configurations, with model-family-specific availability.

## Main findings

- The abstract reports roughly 1%-3% degradation for 4-bit quantization on workflow generation and tool use, versus 10%-15% on real-world applications.
- Structured JSON generation degrades more severely than string output.
- Quantization generally preserves tool-use capability better than pruning, but effects vary substantially by model architecture.
- Workflow-generation scores often remain within a 5% degradation margin, while closed-loop AgentBoard tasks show materially larger losses.
- Long-context average scores can look stable while needle retrieval reveals failures; compressed models in the reported setup show a boundary around 32K within 40K-context tests.

## Appraisal

Strengths: first direct, broad benchmark; formal ICML publication; code release; evaluates both decomposed capabilities and interactive applications; reports model- and method-dependent heterogeneity.

Limitations reported by the paper: no QAT; only methods compatible with vLLM; default configurations without group-size exploration. Additional limitation for the present research question: much of the analysis aggregates benchmark scores and does not provide a causal, step-level account of how quantization errors accumulate through complete trajectories. The benchmark mixture also prevents a single numerical degradation estimate from generalizing to all Agent workloads.

## Impact profile

- Cohort: recent influential/direct seed.
- Evidence: ICML main publication, public benchmark/code, and direct reuse of established T-Eval, WorfBench and AgentBoard evaluation components.
- Uncertainty: too recent for durable citation-based influence to be established; “central direct work” is better supported than “field-defining high-impact work.”

