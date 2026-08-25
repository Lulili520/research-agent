---
name: scholarly-search
description: Find, verify, deduplicate, and map computer-science conference papers, especially current CCF-recommended venues. Use for CCF paper searches, topic landscapes, conference/year/track filtering, citation chaining, or candidate bibliographies; do not use for full-paper interpretation or cross-paper conclusions.
---

# Scholarly Search

Build a relevant, reproducible computer-science literature set without overstating what metadata or abstracts establish.

## Workflow

1. Frame the technical direction, subproblems, time range, target CCF domains/categories, conference or journal scope, paper types, and desired breadth. State material assumptions.
2. Create concept groups with synonyms, abbreviations, spelling variants, and useful exclusions. Use multiple queries when one cannot cover the topic.
3. Search complementary sources. Prefer official conference proceedings or submission portals for status and paper type; use DBLP for normalized computer-science metadata; use ACM Digital Library, IEEE Xplore, USENIX, Springer, AAAI/IJCAI proceedings, ACL Anthology, CVF Open Access, PMLR, or field-equivalent proceedings as applicable; use OpenReview for review-era metadata; use arXiv for discovery and accessible manuscripts.
4. Record the database and platform, exact query, searched fields, controlled vocabulary, filters, sort, result cap, pagination status, search date, and observable count when reproducibility matters.
5. Read [references/ccf-venue-rules.md](references/ccf-venue-rules.md) whenever filtering, labeling, or comparing CCF venues. Separate three operations:
   - deduplicate identical records by DOI/stable ID, then normalized title and author/year;
   - link versions or reports such as preprint, conference abstract, accepted manuscript, and version of record;
   - group multiple reports that describe the same underlying study when the study is the protocol's unit of interest.
6. Screen with predeclared criteria when a protocol exists. Record a concrete exclusion reason for full-text candidates when coverage matters, using the protocol vocabulary.
7. Expand strong seed papers through backward references, forward citations, and related-paper links when the requested breadth requires it.
8. When the user prioritizes influential or representative work, read [references/impact-prioritization.md](references/impact-prioritization.md). Build dated, source-attributed impact profiles and select across foundational, recent-influential, and emerging cohorts. Otherwise rank using topical directness, study type, recency, and likely methodological value.
9. Verify title, authors, venue, conference edition/year, track, paper type, pages or paper ID, DOI/DBLP key/OpenReview forum ID where available, version relationship, and stable link from authoritative records.

## Output contract

Return or save the search scope and exact queries, a deduplicated candidate list with CCF catalog metadata, venue/year/track/paper type, record/version relationships, full-text and code availability, screening rationale, a shortlist for analysis, and search limitations with the stopping reason. For impact-focused searches, also report each candidate's impact evidence, sources and observation dates, cohort, uncertainty, and selection rationale.

When saving files, adapt [assets/search-output.md](assets/search-output.md) into `search-log.md` and `literature.md`. Do not fill unknown metadata by guessing.

## Boundaries

- Label conclusions drawn only from titles or abstracts.
- Do not claim comprehensiveness unless the process supports it.
- Do not synthesize causal, clinical, or comparative conclusions; hand selected sources to `paper-analysis` first.
- Do not silently merge records merely because their titles are similar; preserve uncertain version or study-family matches for review.
- Do not infer acceptance track or Full/Regular status from the venue acronym alone.
- Do not rank individual papers by CCF category alone.
- Do not call a paper high-impact from raw citation count or one popularity proxy alone.
- Stop when the scope is met and new searches mostly duplicate known results, or when access limitations prevent useful expansion.
