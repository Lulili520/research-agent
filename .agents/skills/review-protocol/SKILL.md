---
name: review-protocol
description: Define and freeze a reproducible protocol for a rigorous computer-science or CCF conference-paper survey. Use when venue categories, editions, tracks, paper types, technical scope, appraisal, and synthesis decisions must be fixed before screening; do not use for quick paper discovery or ordinary direction summaries.
---

# Review Protocol

Create a decision-complete protocol before detailed searching or screening. Do not retroactively change it to fit discovered results.

## Workflow

1. Define the research question and intended decision. Use PICO, PECO, SPIDER, or another domain-appropriate framework only when it improves clarity.
2. Specify the unit of interest: paper, version family, method, benchmark, system, or another entity. Explain how arXiv, OpenReview, proceedings, and journal extensions will be linked.
3. Freeze inclusion and exclusion criteria for topic, CCF domain/category, venue editions, track and paper type, method/task, dataset/benchmark, dates, language, publication status, and access where relevant.
4. Define information sources, draft search concepts, grey-literature or registry coverage, citation chaining, deduplication, and search-update policy.
5. Define screening stages, exclusion-reason vocabulary, conflict resolution, and which counts will be recorded. Do not promise independent dual review unless separate reviewers or genuinely independent passes are available.
6. Select study-design-appropriate extraction and critical-appraisal methods.
7. Predefine grouping, synthesis, heterogeneity handling, evidence-strength method, and conditions under which meta-analysis or other quantitative synthesis is appropriate.
8. Define amendments, stopping rules, deliverables, and review limitations.

## Output contract

Adapt [assets/protocol.md](assets/protocol.md) and save it as `protocol.md` when files are requested or downstream stages need persistent state. Mark the protocol status and version. Later amendments must preserve the original decision, date, reason, and expected impact.

## Boundaries

- A protocol improves consistency; it does not by itself make a review systematic or PRISMA-compliant.
- CCF category is a venue filter, not an individual-paper quality criterion.
- Do not invent registration, peer review, independent reviewers, or measured counts.
- If the question is too ambiguous to define defensible eligibility criteria, stop for user direction.
