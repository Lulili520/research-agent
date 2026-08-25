# Quantization Inflates Reasoning

## Identity and access

- Citation: Xinyu Lian et al. *Quantization Inflates Reasoning: Token Inflation as a Hidden Cost of Low-Bit Reasoning Models.* arXiv:2606.25519v2, 2026.
- Stable record/full text: https://arxiv.org/abs/2606.25519
- Publication status: preprint as of 2026-08-25; no CCF category.
- Access level: full experimental arXiv HTML.

## Contribution

The paper identifies reasoning-token inflation: INT4/INT3 models may retain final-answer accuracy but produce longer and more repetitive reasoning. It proposes CoT Token Inflation Ratio (CTIR) and argues that per-token speed plus accuracy omits an important end-to-end cost.

## Agent relevance

The experiments include agentic tool-use alongside mathematics, code generation, and scientific QA. The central implication is that a quantized model can be faster per decoding step yet slower or more expensive per completed task because it emits more steps/tokens. This directly challenges evaluation based only on success rate and tokens-per-second.

## Appraisal

Strengths: isolates a previously hidden efficiency channel; compares low-bit models to full-precision references; examines trace repetition and end-to-end serving consequences.

Limitations: recent preprint; its main construct is reasoning-token count, not a complete taxonomy of Agent actions, environment states, retries, or recovery. Token inflation may also interact with prompting and inference controls, which the paper reports as inconsistent mitigations.

## Impact profile

- Cohort: emerging/high-potential.
- Evidence: directly relevant new metric and multi-domain evidence including tool use.
- Uncertainty: no mature citation or independent-adoption evidence yet.

