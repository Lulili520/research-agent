# Design-specific appraisal routing

Use only the lanes relevant to the source. Prefer an established domain tool named in an approved protocol; the prompts below are minimum reasoning dimensions, not substitute branded checklists.

## Randomized experiments

Check allocation/randomization, deviations from assignment, missing outcomes, outcome measurement, selective reporting, power/precision, and applicability.

## Observational and causal studies

Check selection, confounding, exposure and outcome measurement, missingness, model specification, robustness/sensitivity analysis, temporal ordering, and transportability.

## Machine-learning papers

Check dataset provenance and representativeness, leakage or contamination, split design, baseline fairness, metric validity, tuning and test separation, ablations, uncertainty/statistical testing, external validation, compute disclosure, and reproducibility artifacts.

## Systems, networking, databases, and software-engineering papers

Check workload representativeness, experimental environment, scale, baseline parity, tuning, warm-up and repeated runs, variance, resource accounting, failure behavior, sensitivity, open-source artifacts, and whether the evaluation supports deployment claims.

## Security and privacy papers

Check threat model, attacker knowledge and capabilities, security definition, adaptive attacks, baseline strength, dataset realism, false-positive/false-negative tradeoffs, composability, disclosure constraints, and whether empirical evidence matches the claimed guarantee.

## Theory and algorithms papers

Check problem definition, assumptions, theorem scope, proof completeness at the accessed level, complexity model, lower-bound or optimality claims, edge cases, and whether empirical illustrations are being mistaken for proof.

## HCI and empirical software studies

Check sampling, study protocol, construct validity, instrumentation, power or saturation, multiple testing, qualitative coding, participant context, ecological validity, ethics, and generalizability.

## Benchmark or dataset papers

Check construct validity, task coverage, annotation process and agreement, contamination, subgroup performance, licensing, versioning, and whether the benchmark supports the claimed real-world inference.

## Qualitative studies

Check sampling rationale, reflexivity, data collection, analytical transparency, triangulation, negative cases, saturation claims, and transferability.

## Reviews and meta-analyses

Check protocol timing, search coverage, screening and study linkage, extraction verification, design-specific risk-of-bias assessment, heterogeneity, missing-results bias, synthesis appropriateness, and certainty assessment.

## Judgment format

For each relevant domain record:

- judgment: low concern / some concern / high concern / unclear;
- source-located rationale;
- likely direction and importance of impact;
- whether missing information prevents a conclusion.

Give an overall confidence label only after documenting domain judgments. Do not average domain labels mechanically.
