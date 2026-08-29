# Research-direction construction

Read this reference when the user asks the agent to generate, refine, rank, or validate research directions.

## Principle

Do not generate directions from an isolated paper limitation. Construct them from a traceable chain:

`research objective -> evidence landscape -> unresolved inference -> candidate hypothesis -> adversarial novelty search -> feasible experiment -> ranked direction`

The agent proposes candidates; it does not certify truth or global novelty. Human scientific judgment remains a required gate before substantial experimentation or submission.

## Evidence-grounded workflow

1. **Freeze the objective.** Define the target system, intervention, outcome, setting, intended venue/community, resource envelope, and what kind of contribution is acceptable: measurement, mechanism, method, benchmark, or system.
2. **Build the evidence neighborhood.** Start from several direct anchor papers, then expand through backward/forward citations, authors/projects, adjacent constructs, and current proceedings/preprints. Record both supporting and gap-destroying evidence.
3. **Construct a problem map.** Extract established findings, contradictions, validity threats, failure modes, deployment consequences, and transferable concepts from adjacent fields.
4. **Generate structured candidates.** Each candidate must contain problem, hypothesis or method, experiment, expected contribution, and closest-work delta. Encourage cross-domain transfer only when the transferable construct and required adaptation are explicit.
5. **Run adversarial review.** Use separate critic lenses for novelty, scientific importance, validity, feasibility, and reproducibility. Critiques must cite evidence or identify a test; unsupported taste is not a rejection reason.
6. **Run iterative anti-gap search.** Turn each candidate's essential contribution into exact-concept and synonym queries. Search until a direct overlap is found or the documented search reaches diminishing returns. Inspect the closest papers rather than trusting titles or snippets.
7. **Evolve, merge, or reject.** Revise candidates in response to criticism; merge complementary measurement and mechanism ideas; reject candidates whose irreducible delta is merely more models, more datasets, or a renamed established metric.
8. **Rank as a portfolio.** Report novelty confidence, importance, tractability, evidence quality, and expected contribution separately. Keep a focused primary direction plus at most two meaningful alternatives.
9. **Specify validation.** State variables, controls, baselines, metrics, uncertainty analysis, confounders, minimum useful result, and what a null result would teach.
10. **Set gates and refresh points.** Require human approval before expensive experiments, and refresh the novelty audit immediately before commitment and submission.

## Lessons from existing research agents

- ResearchAgent grounds ideation in a seed paper, academic graph, and concept store, then iteratively revises problem, method, and experiment with reviewing agents.
- The AI Scientist generates feasible ideas relative to an executable codebase and uses iterative literature queries to reject substantial overlap.
- AI Co-Scientist uses generate-debate-evolve, specialized review roles, and tournament-style comparison instead of accepting the first plausible hypothesis.
- Agent Laboratory separates literature review, experimentation, and writing, and its reported evaluation supports explicit human feedback gates.

Adopt these mechanisms, but do not inherit their automated novelty labels as facts. Retrieval incompleteness, evaluator bias, fabricated citations, and weak construct validity remain possible.

## Direction card

For every retained direction, report:

- one-sentence research claim and contribution type;
- scientific question and falsifiable hypotheses;
- established evidence and unresolved inference;
- closest work, overlap, and irreducible delta;
- anti-gap queries, near misses, cutoff date, and novelty confidence;
- experiment: systems, interventions, controls, tasks, outcomes, repetitions, and analyses;
- contribution under positive and null results;
- validity threats, compute/data cost, artifact plan, and human decision gate.

## Rejection rules

Reject or demote a direction when its novelty rests only on a new model list, a benchmark mash-up, an unvalidated composite score, an arbitrary metric, or a feature absent from one paper but established elsewhere. Never use `first`, `never studied`, or `no prior work` without a publication-level novelty audit; even then use dated and scoped language.
