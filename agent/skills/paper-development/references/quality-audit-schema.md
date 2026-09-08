# 统一质量审计结构

`paper/quality-audit.json` 顶层包含：

- `dimensions`：恰好包含 `importance`、`novelty`、`depth`、`theory`、`correctness`、`experimental_sufficiency`、`robustness`、`reproducibility`、`ethics`、`clarity`。
- 每一维包含 `status: pass|not-applicable`、非空 `rationale` 和非空 `evidence` 定位列表。`not-applicable` 必须解释为何不适用，不能用来逃避失败。
- `fatal_issues`：完成时必须为空列表；未关闭问题不得删除，应先回退研究阶段。
- `review_independence`：包含非空 `reviewer_role`、`reviewer_model`、`context_isolation`，以及布尔值 `independent_evidence_check`。

结构通过只说明审计声明齐全、证据可定位，不说明理由真实或判断正确。审稿者必须从冻结的声明、原始结果和 Artifact 重新核对，而不是照抄作者自评。同一模型仅更换角色提示时，要在 `context_isolation` 如实说明其有限独立性。
