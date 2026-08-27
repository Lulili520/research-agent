---
name: paper-analysis
description: Closely analyze computer-science conference papers with source-located evidence about novelty, method, datasets, baselines, results, efficiency, and artifacts. Use for CCF paper summaries, experiment or ablation review, figure/table interpretation, reproducibility assessment, or structured paper notes; do not use for broad discovery or unsupported field-wide synthesis.
---

# Paper Analysis

Turn accessible paper content into a source-located evidence record. Analyze only what was actually accessed.

## Workflow

1. Resolve identity and publication status. Verify title, authors, canonical venue, edition/year, track, paper type, pages or paper ID, stable identifiers, and whether the document is arXiv, OpenReview, proceedings, or a later journal version.
2. Record access level. If only metadata or an abstract is available, restrict analysis accordingly and say so prominently.
3. Extract the problem formulation, prior limitation addressed, claimed novelty, assumptions, method or system design, algorithmic steps, complexity, datasets/benchmarks, splits, baselines, metrics, evaluation protocol, headline results, ablations, efficiency/compute, limitations, and failure cases when relevant.
4. Read tables, figures, appendices, and supplementary material when they materially affect the requested conclusion. Use the available PDF workflow for PDF inspection.
5. Extract narrow evidence statements with page, section, figure, or table locators. Assign stable evidence IDs and classify each as `reported`, `derived`, or `inference`; show any derivation. Keep source-reported results separate from author interpretation and agent inference.
6. Assess validity and reproducibility using a computer-science lane in [references/design-appraisal.md](references/design-appraisal.md). Check code, model, data, configuration, and environment availability when reported. Do not apply one generic checklist to every subfield.
7. For impact-focused work, verify the shortlisted impact signals against their cited external records and summarize the concrete intellectual or practical uptake. Keep this separate from technical appraisal.
8. Check whether the abstract, results, and conclusion differ in strength or scope; flag overclaiming or unsupported extrapolation.
9. Before handoff, apply the analysis gate in the repository `AGENTS.md`. Claims without adequate access or locators remain unresolved and cannot be promoted downstream.

## Output contract

Return or save a paper note containing verified venue/track/type and version family, problem and novelty, method, datasets/benchmarks, baselines, metrics, comparable results, ablations, resource cost, artifacts, source-located evidence, validity appraisal, limitations, and unresolved questions. Include a separately sourced impact profile when impact is part of the selection question.

When saving a note, adapt [assets/paper-note.md](assets/paper-note.md) to `papers/<source-id>.md`. Omit irrelevant fields rather than inventing values.

## Boundaries

- A paper note is not a field-wide conclusion.
- Acceptance at a CCF venue is not evidence that every claim in the paper is correct.
- Never compare headline numbers without checking dataset version, split, metric definition, evaluation protocol, and resource assumptions.
- Do not treat absence from the accessible text as proof that something was not done.
- Keep quotations short and use precise paraphrase where possible.
- Do not turn an unperformed appraisal into a high/medium/low quality label.
- Stop when the requested claims are located and the paper note captures the evidence needed downstream, or report that the accessible version is insufficient.
