---
name: evidence-synthesis
description: Synthesize analyzed computer-science conference papers into a method taxonomy, research timeline, benchmark comparison, tradeoff analysis, and traceable direction summary. Use for CCF-topic surveys, related-work maps, technical comparisons, trend reports, or research-gap analysis; do not use when papers still need discovery or full-text extraction.
---

# Evidence Synthesis

Answer the research question from inspected evidence without adding unsupported facts.

## Readiness check

Confirm that the available source set and paper notes identify access level, relevant findings, and locators. If coverage is inadequate, return to `scholarly-search`. If key papers lack evidence extraction, return to `paper-analysis`. Do not repair missing upstream evidence by guessing.

## Workflow

1. Restate the technical direction and create a claim ledger. Give each consequential claim a stable `claim_id` and map it to supporting, contradicting, or contextual evidence.
2. Build a problem decomposition, method taxonomy, and chronological lineage. Group papers by technical idea and dependency, not by CCF category, popularity, or paper order.
3. Compare results only when tasks, dataset/benchmark versions, splits, preprocessing, metrics, evaluation settings, and resource assumptions are sufficiently compatible. Otherwise provide a qualitative comparison and explain the incompatibility.
4. Weight evidence using design appropriateness, execution quality, directness, precision, consistency, risk of bias, and missing-results risk. Citation count is not evidence strength. Preserve the rationale rather than outputting an unexplained score.
5. Distinguish established techniques, contested findings, incremental extensions, and preliminary directions. Match wording strength to evidence strength and access level.
6. Analyze accuracy/quality, efficiency, scalability, robustness, generalization, interpretability, privacy/security, engineering complexity, and artifact availability only where relevant. For research gaps, read [references/research-gap-validation.md](references/research-gap-validation.md). When constructing or ranking research directions, also read [references/research-direction-construction.md](references/research-direction-construction.md). Run an explicit anti-gap search and retain only directions with scientific consequence, an irreducible closest-work delta, and a feasible falsifiable study.
7. Audit every consequential sentence against the claim ledger: confirm the cited source supports the exact claim, the locator was checked, the relevant text was accessed, the statement is classified as `reported`, `derived`, `inference`, or `proposal`, the version is clear, and bibliographic metadata agrees with an authoritative record.
8. For impact-focused reports, explain why each representative paper is influential using dated external signals, while keeping impact, technical contribution, and evidence confidence as separate axes. Ensure the narrative includes established, recent, and emerging work when credible candidates exist.
9. Remove decorative citations that merely mention the topic.
10. Before completion, apply the synthesis and direction gates in the repository `AGENTS.md`, update `state.md`, and run the repository research audit when artifacts are saved.

## Output contract

Lead with the direction overview. Include the problem map, method taxonomy, representative CCF papers, chronological development, comparable benchmark evidence, tradeoffs, open problems, and a concise reading list. For gap-focused reports, include detailed gap cards, closest-work deltas, anti-gap search, scientific value, concrete research directions, risks, and calibrated confidence. For direction-generation tasks, return one focused primary direction and at most two meaningful alternatives unless the user requests a broad portfolio. For impact-focused reports, add an impact map and justify representative-paper selection. Put citations beside claims and disclose search cutoff, impact-metric observation date, CCF catalog edition, venue/track scope, source access, and limitations.

When saving work, adapt [assets/synthesis-output.md](assets/synthesis-output.md) into `evidence.md` and `report.md`. Keep claim IDs in both artifacts so report statements remain traceable.

## Boundaries

- Do not imply systematic-review or PRISMA compliance unless that process was actually completed.
- Do not convert a narrow or convenience sample into a claim about the whole field.
- Do not make recommendations stronger than the inspected evidence permits.
- Do not assign evidence strength when critical appraisal is absent; report the missing appraisal instead.
- Do not equate a higher CCF venue category with a stronger contribution or more reliable result.
- Do not construct a leaderboard from incompatible experimental settings.
- Do not promote “not evaluated in this paper” into a research gap without testing whether it is solved elsewhere and whether resolving it changes a scientific inference.
- Stop when each scoped conclusion is traceable, contradictions are addressed, and further evidence would not materially change the requested synthesis; otherwise report the missing upstream work.
