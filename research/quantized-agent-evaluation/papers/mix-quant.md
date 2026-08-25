# Mix-Quant

## Identity and access

- Citation: Haiquan Lu et al. *Mix-Quant: Quantized Prefilling, Precise Decoding for Agentic LLMs.* arXiv:2605.20315v1, 2026.
- Stable record/full text: https://arxiv.org/abs/2605.20315
- Publication status: preprint as of 2026-08-25; no CCF category.
- Access level: full experimental arXiv HTML.

## Contribution

Mix-Quant separates inference phases: NVFP4 weight-and-activation quantization is applied during prefill, while decoding stays BF16. The motivation is specific to long-input, multi-turn Agent workloads in which prefill dominates computation but decoding is more accuracy-sensitive.

## Main findings and relevance

- Full-process FP4 produces notable performance degradation in the reported agent workflows.
- Prefill-only NVFP4 largely preserves task performance and provides up to 3x prefill speedup in the reported setup.
- Evaluation of quantized agents therefore must state *where* precision is reduced, not merely label a model “4-bit.” Prefill, decoding, weights, activations and KV cache can have different behavioral consequences.

## Appraisal

Strengths: connects Agent workload shape to a phase-aware system intervention; measures both task quality and speed.

Limitations: recent preprint; hardware-specific NVFP4 design limits immediate generalization; reported peak prefill speedup is not identical to end-to-end Agent speedup; mixed precision is not directly comparable with uniform INT4 checkpoints without a shared resource budget.

## Impact profile

- Cohort: emerging/high-potential.
- Evidence: technically direct and introduces a distinct evaluation/control axis.
- Uncertainty: publication, independent reproduction and durable adoption are not yet established.

