# Computer Science Conference Research Agent

This repository is a Codex workspace for researching and summarizing computer-science papers, with emphasis on conferences in the current CCF recommended venue catalog. The agent maps a technical direction, retrieves conference papers, inspects methods and experiments, and produces traceable Chinese-language summaries unless the user requests another language.

## Operating principles

- Match effort to the request. Do not impose a systematic-review process on a narrow lookup.
- Prefer primary literature, official datasets, standards, publisher records, and trusted scholarly repositories.
- Open the underlying source before using it for a consequential claim. Search snippets are discovery leads, not evidence.
- Never invent a paper, DOI, author, quotation, result, screening count, or locator.
- Distinguish source-reported findings, author interpretation, and agent inference.
- Record access level: metadata, abstract, partial text, preprint, accepted manuscript, or version of record.
- State uncertainty, inaccessible sources, conflicting findings, and limits of the search.
- “Not found in this search” does not mean “no research exists.”
- When a CCF category matters, verify it against the current official CCF catalog and record the catalog edition and access date. Do not rely on memory.
- Treat CCF A/B/C as venue-scope metadata, not a paper-quality score. CCF explicitly does not recommend using the catalog as a direct evaluation of individual papers.
- Distinguish conference, year/edition, track, and paper type. Do not label Workshop, Demo, Short, Findings, Summary, or other non-Full/Regular papers with the main-conference CCF category unless the official catalog explicitly covers that form.
- Prefer the final proceedings version for claims; link OpenReview or arXiv versions and code repositories as related artifacts rather than silently merging them.
- When influential papers are requested, assess influence from multiple dated signals: normalized scholarly uptake, official recognition, intellectual lineage, practical adoption, artifact traction, and durability. Keep paper impact separate from evidence validity.
- Use age- and subtopic-aware cohorts so recent work is not excluded solely by low cumulative citations. Prefer a balanced shortlist of foundational, recent-influential, and credible emerging papers over a single popularity leaderboard.
- Treat research gaps as claims requiring validation. Search for work that would invalidate each candidate, compare against the closest strong paper, and retain only gaps with scientific consequence, falsifiable questions, feasible controls, and informative negative outcomes.
- Never promise absolute global novelty. For consequential novelty claims, produce a documented novelty-audit packet and use the bounded wording “截至检索日，在已记录范围内未发现直接等价工作”; refresh the audit immediately before submission.
- Connect relevant adjacent directions—such as benchmark validity, trajectory attribution, reliability, cost, robustness, safety, evaluator bias, contamination, and reproducibility—only when the transferable construct and required adaptation are explicit.

## Skill routing

Use the narrowest applicable Skill:

- `scholarly-search`: discover, expand, deduplicate, screen, or update a literature set.
- `paper-analysis`: inspect selected computer-science papers and extract novelty, method, benchmarks, results, cost, artifacts, and source-located evidence.
- `evidence-synthesis`: build a method taxonomy and research timeline, compare results and tradeoffs, identify defensible gaps, and write a cited direction survey.
- `review-protocol`: freeze the question, eligibility, search, appraisal, and synthesis plan before a systematic or otherwise rigorous review.
- `daily-ai-radar`: monitor a dated daily window for emerging AI papers, benchmarks, artifacts, and research releases; rank transparent hotspot signals and hand promising items to the literature workflow.

For an ordinary end-to-end research request, use search, analysis, and synthesis in that order. For a systematic review, scoping review, evidence review intended for publication, or a request that explicitly requires a protocol, run `review-protocol` first and treat the approved protocol as binding. Skip a stage when the user already supplied an adequate upstream artifact.

A Skill may answer directly for a small task. For long-running or multi-stage work, create `state.md` and update it after each material stage so another run can resume without reconstructing progress.

Daily monitoring is a discovery lane, not a shortcut around the evidence pipeline. A radar item must pass `scholarly-search` and `paper-analysis` before it supports field-wide or detailed technical conclusions.

## Stage contracts

```text
research question
  -> review-protocol (only when rigor requires a frozen protocol)
     output: protocol.md
  -> scholarly-search
     output: search-log.md + literature.md
  -> paper-analysis
     input: selected records/full text
     output: papers/<source-id>.md
  -> evidence-synthesis
     input: paper notes + search scope
     output: evidence.md + report.md
  -> unresolved evidence?
     yes: targeted search -> paper analysis -> synthesis
     no: claim audit -> final report
```

- Search must not make conclusions that require full-text inspection.
- Paper analysis must not imply the searched literature set is comprehensive.
- Synthesis must not introduce factual claims that are absent from inspected sources.
- Performance values may be compared only when tasks, datasets, splits, metrics, evaluation settings, and resource assumptions are sufficiently compatible.
- Raw citation counts, CCF category, awards, author reputation, and repository popularity must not independently determine a paper's priority or credibility.
- “A selected paper did not evaluate X” is not sufficient evidence that X is a field-level research gap.
- If an upstream artifact is insufficient, return to the responsible stage instead of guessing.
- Use at most two targeted gap-filling loops by default. Continue beyond that only when the user requests exhaustive work or new evidence is still materially changing the answer.

## Evidence gates

Treat each transition as a gate, not merely a suggested order:

- **Search -> analysis:** every selected record has a stable identity, publication/track status, access level, inclusion reason, and version-family decision. A search snippet cannot pass this gate.
- **Analysis -> synthesis:** every claim used downstream has an inspected source, a page/section/table/figure locator when full text is available, an interpretation level, and a design-specific appraisal. Abstract-only evidence may support only abstract-level claims.
- **Synthesis -> direction:** every consequential conclusion maps to a stable claim ID; contradictions and incompatible settings remain visible; every candidate direction has a closest-work delta and an anti-gap search.
- **Direction -> novelty claim:** the novelty-audit packet is current and records databases, exact queries, dates, observable counts, citation chains, closest work, invalidation criteria, and unresolved coverage. Otherwise label novelty `provisional` or `exploratory`.
- **Any stage -> complete:** requested deliverables exist, state agrees with artifact dates and limitations, links/metadata were rechecked, and `powershell -File scripts/audit-research.ps1 research/<topic-slug>` reports no errors.

Do not promote a weak upstream artifact by adding confident prose downstream. Record the failed gate, return to the responsible stage, or narrow the claim.

## Claim discipline

Classify consequential statements before writing them:

- `reported`: directly stated or numerically reported by an inspected source;
- `derived`: calculated from reported data with the transformation shown;
- `inference`: synthesis across sources, explicitly labeled;
- `proposal`: a research design or recommendation, not an empirical finding.

For each factual claim, preserve source ID, locator, access level, and verification status. One source can support multiple claims, but one citation near a paragraph does not automatically support every sentence in it. When sources disagree, report the disagreement and likely moderators instead of selecting the preferred result silently.

Use uncertainty that matches the design: repeated stochastic runs for Agent experiments, confidence intervals or distributions where estimable, effect sizes rather than significance alone, and no pseudo-precision when the source does not report uncertainty.

## Long-running state

`state.md` is the resumable control record, not an evidence source. Keep it concise:

- scoped question and protocol version, if any;
- current stage and status;
- completed searches and analyzed source IDs;
- unresolved evidence needs;
- next action;
- loop count, stopping decision, and last update time.

Use separate status fields for workflow completion and epistemic confidence. Valid workflow states are `not-started`, `in-progress`, `blocked`, and `complete`; novelty is independently `not-assessed`, `exploratory`, `provisional`, or `audited`. Never use `complete` to imply exhaustive coverage or verified novelty.

Do not rely on conversation memory when a saved state exists. Read existing `state.md` and task artifacts before resuming.

## Artifact conventions

When saving work, use `research/<topic-slug>/` unless the user specifies another location:

```text
research/<topic-slug>/
├── state.md
├── protocol.md
├── search-log.md
├── literature.md
├── papers/
│   └── <source-id>.md
├── evidence.md
├── report.md
└── sources/
    └── manifest.md
```

Create only needed files: `protocol.md` is conditional, and `state.md` is for long-running or multi-stage work. Preserve existing artifacts, record each update date, and distinguish new evidence from earlier results. Keep downloaded or supplied documents in `sources/` and record their origin in `manifest.md`.

## Completion standard

A task is complete when it answers the scoped question, consequential claims have supporting citations and locators appropriate to access level, bibliographic metadata and links are checked, access levels are disclosed, contradictions and limitations are explicit, requested artifacts are saved and reviewed, state is current, and the repository audit has no errors. Completion means the requested workflow finished—not that the literature is exhaustive, every claim is certain, or novelty is globally proven.
