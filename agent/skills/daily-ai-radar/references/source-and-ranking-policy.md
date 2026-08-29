# Source and ranking policy

## Source lanes

Use complementary lanes because no single index is both instantaneous and authoritative:

1. **Fresh scholarly feeds:** arXiv categories such as `cs.AI`, `cs.CL`, `cs.LG`, `cs.CV`, `cs.RO`, and `stat.ML`; OpenReview recent submissions only when status is explicitly labeled.
2. **Bibliographic graphs:** OpenAlex for date/topic/search filters, citation neighborhoods, related works, and normalized identities; Semantic Scholar for academic-graph search and seed-based recommendations.
3. **Authoritative publication records:** ACL Anthology, PMLR, CVF Open Access, ACM DL, IEEE Xplore, USENIX, AAAI/IJCAI, NeurIPS/ICLR/OpenReview, DBLP, or the applicable official proceedings.
4. **Artifacts:** official project, code, model, dataset, and benchmark repositories. Stars/downloads are dated attention signals, not evidence of validity.
5. **Primary institutional releases:** official research-lab or standards pages for new models, datasets, evaluations, or policies. Keep these distinct from peer-reviewed evidence.

Respect API terms, rate limits, and access restrictions. Record failures and do not infer zero activity from a failed source.

## Hotness profile

Record dimensions separately:

- **Research mapping:** match to tracked topics and user research questions after field-wide hotspot selection; this must not determine admission or rank in the daily hotspot list.
- **Freshness:** first public appearance and material update time, not merely index ingestion time.
- **Independent attention:** appearance across independent scholarly/artifact sources; syndicated copies count once.
- **Uptake velocity:** age-normalized early citations, references, recommendations, downloads, forks, or follow-on discussion when verifiable.
- **Artifact strength:** code/data/model availability, license, documentation, and reproducibility evidence.
- **Publication confidence:** proceedings > accepted record > active submission > preprint for status confidence, not necessarily scientific quality.
- **Evidence quality:** construct validity, fair comparisons, uncertainty, external validity, and disclosed limitations to the extent actually inspected.
- **Novelty signal:** credible difference from closest recent work; this remains exploratory until anti-gap search and full-text analysis.

Do not use a universal weighted sum by default. Report why an item is selected and where the signals disagree. A highly discussed preprint can be hot but weakly validated; a rigorous paper can be important without trending socially.

Daily hotspot selection is field-first: identify what gained verifiable attention across AI during the previous calendar day, cluster retained items into emerging directions, and only then map those clusters and items to the user's tracked research themes.

## Corrections

If identity, venue, result, or status changes, preserve the previous entry and publish a dated correction. Never silently rewrite historical radar output.
