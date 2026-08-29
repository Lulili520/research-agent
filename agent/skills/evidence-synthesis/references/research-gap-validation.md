# Research-gap validation

Read this reference whenever the user asks for research gaps, novelty opportunities, thesis directions, or publishable future work. A missing column in a literature table is not automatically a valuable gap.

## Gap status

Assign one status and preserve the rationale:

- **Author-stated limitation**: explicitly reported by one or more inspected papers.
- **Coverage gap**: absent or weak across the inspected coverage matrix.
- **Contradiction gap**: credible studies disagree and the cause is unresolved.
- **Validity gap**: the prevailing task, outcome, metric, judge, or experimental protocol may not measure the intended construct.
- **Translation gap**: a validated method from an adjacent field has not been adequately adapted or tested in the target setting.
- **Emerging opportunity**: motivated by new systems, hardware, risks, or deployment patterns but not mature enough to claim established absence.

Use `candidate gap` until the gap survives the checks below. Avoid priority claims such as `first`, `none`, and `unexplored` unless the search supports them.

Absolute proof that nobody has done a direction is impossible because unpublished, unindexed, newly posted, non-English, or inaccessible work may exist. The strongest permitted conclusion is: `As of <date>, no directly equivalent study was found in the documented search scope.` State this limitation whenever novelty is consequential.

## Validation funnel

### 1. Precise proposition

State the gap as a falsifiable proposition with population/system, intervention or phenomenon, outcome, and setting. Replace vague wording such as “lacks comprehensive evaluation” with the exact missing comparison or inference.

### 2. Saturation and anti-gap search

Search to disprove the candidate, not only to support it:

- exact claim and alternate terminology;
- adjacent subfields and older terminology;
- recent proceedings, preprints, workshops, datasets, and benchmark papers;
- backward and forward citations from the closest direct work;
- combinations of the proposed method and target domain.

Record what would invalidate the gap and which sources came closest. A gap is not validated when access or search coverage is too weak.

For a thesis, grant, or publication-level novelty claim, produce a novelty-audit packet containing:

- databases and proceedings searched, exact dates, full queries, filters, pagination and result counts where observable;
- exact-title, exact-concept and synonym searches;
- closest-work backward and forward citation chains;
- author/project/code searches for the closest methods;
- current major-venue proceedings and recent preprints;
- a closest-work table showing overlap and the irreducible delta;
- explicit invalidation criteria and near-miss papers;
- a scheduled update immediately before submission.

Do not label a gap `validated` if the direct query set is narrow, citation chaining is incomplete, or recent-work coverage is stale. Use `provisional` or `exploratory` instead.

### 3. Importance and consequence

Explain who is harmed by the missing knowledge or what scientific decision remains unreliable. Prefer gaps that affect validity, safety, robustness, efficiency, reproducibility, generalization, or mechanistic understanding. Novelty without consequence is low value.

### 4. Scientific tractability

Require a measurable outcome, meaningful baselines, controllable confounders, feasible data/compute, and a result that remains informative if the main hypothesis is false. Distinguish a research question from an engineering backlog item.

### 5. Increment over strong work

Name the closest papers and state the delta in one sentence. The proposed direction should change the inference that can be made, not merely add more models, datasets, or metrics.

### 6. Evidence and paper quality

Weight the sources supporting the gap by:

- construct, task, and outcome validity;
- dataset provenance, contamination risk, and representativeness;
- baseline fairness and controlled comparisons;
- repeated trials, uncertainty, effect size, and statistical analysis;
- external validity and stress testing;
- artifact availability, documentation, and independent reproduction;
- claim-scope alignment and disclosed limitations.

Venue category, citation count, author reputation, and leaderboard position do not replace this appraisal.

## Valuable adjacent directions

Use only directions relevant to the target question:

- fine-grained trajectory and causal component evaluation;
- task validity and outcome validity of agentic benchmarks;
- stochastic reliability, worst-case and tail behavior;
- cost, latency, energy, and capability Pareto analysis;
- robustness under noise, imperfect guidance, distribution shift, or tool failure;
- safety, security, privacy, and constraint following;
- evaluator reliability, judge bias, deterministic checks, and human agreement;
- contamination resistance, dynamic evaluation, and cross-benchmark generalization;
- reproducibility, artifact quality, and independent replication;
- consequential long-horizon tasks and deployment realism.

Do not force all directions into every report. A cross-field connection must name the transferable construct, explain why it applies, and identify what must be adapted.

## Gap card

For each retained gap report:

- precise gap proposition and status;
- closest existing work and what it already solves;
- direct and contextual evidence, with quality appraisal;
- anti-gap search performed and surviving uncertainty;
- scientific importance and affected decision;
- research questions or hypotheses;
- feasible study direction: variables, baselines, measurements, and analysis;
- expected contribution if positive and if null/negative;
- feasibility, risks, confounders, and ethical/resource constraints;
- confidence: high / medium / exploratory, with reason.

Rank gaps on separate axes—novelty confidence, scientific importance, tractability, and expected contribution—rather than an opaque total score.
