# Evaluating Quantized Large Language Models

## Identity and access

- Citation: Shiyao Li et al. *Evaluating Quantized Large Language Models.* ICML 2024, PMLR 235:28480-28524.
- Stable record: https://proceedings.mlr.press/v235/li24bb.html
- Code: https://github.com/thu-nics/qllm-eval
- Track/type: ICML main conference paper.
- CCF: Artificial Intelligence, A under the seventh catalog (catalog checked 2026-08-25).
- Access level: official proceedings metadata and accessible paper record/full-text link.

## Contribution and relevance

This is a broad evaluation of weight, activation, and KV-cache PTQ over 11 model families from 125M to 180B. It covers basic NLP, emergent abilities, trustworthiness, dialogue, and long-context tasks. It is not an Agent benchmark, but it establishes the adjacent quantization-evaluation baseline from which ACBench departs.

## Relevance to the research question

- Shows that quantization must be evaluated across model families, precision targets, quantized tensor types, and task classes rather than by perplexity alone.
- Includes dialogue and long-context prerequisites relevant to agents.
- Does not observe environment interaction, trajectory recovery, tool execution, or end-to-end task state; therefore its scores cannot validate Agent performance preservation.

## Appraisal

Strengths: unusually broad model and quantization coverage; formal ICML publication; code artifact; separation of weight, activation and KV-cache effects.

Limitation for this topic: static task evaluation cannot expose compounding action errors, simulator variance, invalid tool arguments, repeated actions, recovery, or cost per successful episode.

## Impact profile

- Cohort: established adjacent foundation.
- Evidence: ICML publication, broad experimental scope, open evaluation code, and conceptual role as the comprehensive pre-Agent quantization evaluation baseline.
- Uncertainty: no citation count is asserted because a consistent dated citation index was not available in this run.

