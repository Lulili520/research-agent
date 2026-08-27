---
name: daily-ai-radar
description: Discover, verify, rank, and summarize current AI research developments into a dated daily radar. Use for today's AI research hotspots, daily paper monitoring, emerging-topic alerts, or recurring research briefs; do not use for exhaustive literature reviews or full-paper conclusions.
---

# Daily AI Research Radar

Produce a reproducible daily snapshot of emerging AI research without treating popularity as scientific validity.

## Workflow

1. Resolve the time window and timezone. Default to a 24-hour primary window in `Asia/Shanghai` plus a 72-hour lookback used only to catch delayed indexing. Distinguish `new`, `late-indexed`, and materially `updated` items. If no items pass the lead gate, publish a quiet-day report rather than recycling old items.
2. Read [references/source-and-ranking-policy.md](references/source-and-ranking-policy.md). Search at least one primary scholarly feed, one bibliographic graph, and authoritative proceedings/project records where applicable. Search official laboratory or organization pages only for releases that materially affect research.
3. Separate `paper`, `benchmark/dataset`, `model/system`, `artifact`, and `research-policy` items. Product marketing, funding news, rumors, social posts, and ordinary company news are excluded unless the user requests an industry radar.
4. Deduplicate by DOI/arXiv/OpenReview/DBLP ID, then normalized title and authors. Link preprint, submission, proceedings, project, code, and dataset versions instead of counting them as separate trends.
5. Verify every shortlisted item's title, authors/organization, first-public date, update date, publication status, venue/track/type, stable URL, and access level. Search snippets and social posts are discovery leads only.
6. Build transparent feature profiles for topical relevance, freshness, independent attention, scholarly uptake velocity, artifact availability, venue/status confidence, and evidence quality. Do not collapse these into an unexplained score or call an item important from raw citations alone.
7. Inspect the abstract or primary announcement for every retained item. Label claims as source-reported or radar inference. Do not summarize methods, results, or limitations beyond the accessed content.
8. Compare against `radar/index.json`. Mark items `new`, `late-indexed`, `updated`, `continuing`, or `corrected`; explain what changed. Do not repeat an unchanged item merely to fill a quota.
9. Apply the deterministic eligibility gate in `config/ai-radar.json`. Identity and abstract access are mandatory; lead promotion additionally requires sufficient relevance, independent sources, or an explicit early-uptake signal. Keep dimensions visible instead of presenting the gate as a scientific-quality score.
10. Save Markdown and JSON briefs under `radar/YYYY/`, update `radar/index.json` and `radar/queue.md`, then run `powershell -File scripts/audit-radar.ps1 radar`. A radar run is complete only when the audit reports no errors.

## Handoff

- Send a promising paper to `scholarly-search` for citation chaining and venue verification.
- Send selected full text to `paper-analysis` before making detailed technical or experimental claims.
- Use `evidence-synthesis` only after adequate paper notes exist.

The radar discovers and prioritizes; it does not establish field-wide conclusions, paper quality, causal findings, or research novelty.

## Stop conditions

Stop when the time window and tracked topics have adequate multi-source coverage, retained identities are verified, duplicates are linked, and further queries mostly repeat known items. Report rate limits, inaccessible sources, delayed indexing, and sources not checked.

For unattended collection, use `node scripts/collect-ai-radar.mjs`; GitHub Actions runs it daily at 08:30 Asia/Shanghai. The deterministic collector creates discovery artifacts, not full-paper scientific summaries.
