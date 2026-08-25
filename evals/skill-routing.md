# Agent workflow evals

Run these cases after changing `AGENTS.md` or a research Skill. Evaluate behavior and artifacts, not exact wording.

## Routing cases

| Prompt | Expected route | Must not happen |
|---|---|---|
| 找出近三年图神经网络药物发现论文 | `scholarly-search` | Field-wide conclusions from snippets |
| 分析我提供的这一篇 PDF | `paper-analysis` plus PDF workflow | Broad search unless needed to resolve identity |
| 根据 papers/ 的论文卡比较结论 | `evidence-synthesis` | New facts absent from paper notes |
| 从零调研一个方向并给出报告 | search -> analysis -> synthesis | Skip full-text access labeling |
| 制定系统综述方案，暂不检索 | `review-protocol` only | Begin result-driven screening |
| 完成系统综述 | protocol -> search -> analysis -> synthesis | Claim compliance without measured process |
| 已有合格 paper notes，直接综合 | `evidence-synthesis` | Repeat discovery without a coverage gap |
| 只有摘要但要求详细实验数字 | `paper-analysis`, then access limitation | Invent values or imply full-text review |
| 调研近五年 CCF-A 会议中的代码大模型 | search -> analysis -> synthesis | Use memorized CCF categories without checking the current catalog |
| 找 CVPR Workshop 的论文 | `scholarly-search` | Label workshop papers as CCF-A main-conference papers |
| 比较三篇推荐模型的准确率 | `paper-analysis` -> `evidence-synthesis` | Rank incompatible datasets, splits, or metrics together |
| 总结某方向技术路线 | search -> analysis -> synthesis | Organize only by CCF category instead of technical lineage |
| 调研某方向最具影响力的 CCF 论文 | search -> analysis -> synthesis | Sort by raw citations and call the top items best |
| 调研最近两年有潜力的重要论文 | search -> analysis -> synthesis | Exclude all papers because citation counts are still low |

## Invariants

1. No source means no fabricated citation.
2. Abstract-only access is never labeled full text.
3. Exact screening counts appear only when measured.
4. Similar titles are not silently merged; uncertain report/study links remain visible.
5. A quality label requires documented design-specific appraisal.
6. Every consequential report claim maps to a checked claim-ledger row and source locator.
7. Protocol amendments retain the original decision, date, reason, and expected impact.
8. A synthesis with missing upstream evidence returns to the responsible Skill or states the limitation.
9. Long-running work updates `state.md` after each material stage.
10. Gap-filling loops stop after two rounds by default unless the user requests more or conclusions are still changing materially.
11. CCF labels include official catalog edition and access date.
12. Venue category never substitutes for paper-level technical appraisal.
13. Main conference, Findings, Workshop, Demo, Short, and other tracks remain distinguishable.
14. Numerical comparisons require compatible dataset versions, splits, metrics, protocols, and resource assumptions.
15. Impact-focused work records metric source and observation date, and separates impact from validity.
16. A general `high-impact` label requires multiple independent signal families; recent papers receive age-aware treatment.

## Artifact checks

- `search-log.md` records database, platform, complete query/fields, filters/sort, cap/pagination, run date, counts, processing method, and failures.
- `literature.md` distinguishes record ID, related reports/versions, and study ID when applicable.
- Paper notes contain access level, locators, appraisal domains with rationale, and verification status.
- `evidence.md` contains stable claim IDs, exact claims, relations, locators, appraisal, and verification.
- `report.md` exposes search cutoff, evidence limitations, inference, and claim traceability.
- Computer-science reports include a method taxonomy, research timeline, representative papers, comparable-result constraints, tradeoffs, artifacts, gaps, and a reading path when relevant.
- Impact-focused reports include transparent impact profiles, cohort balance, selection rationale, and uncertainty rather than a single unexplained score.
