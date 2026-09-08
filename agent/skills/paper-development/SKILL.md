---
name: paper-development
description: 将已完成证据审计的计算机科学研究迭代构建为 ICML、ICLR、NeurIPS、ACL、EMNLP 等顶级 CCF 会议标准的论文、Artifact 说明和投稿审计；不用于实验未完成时包装论文或保证录用。
---

# 顶会论文构建

本 Skill 只消费通过控制平面登记的理论、协议、run、结果、证据和 Artifact。先阅读 `../iterative-research/references/top-tier-research-standard.md`；投稿前联网核验目标会议当届官方规则。

## 入口门禁

1. 运行 `researchctl.py verify-log`，确认所有主张可回溯到终局 run 和原始产物。
2. 核验 `experiments/results.md` 的 Outcome、`analysis.md`、evidence ledger 与 Artifact 验证。缺失时返回最早受影响阶段，不能用叙述补齐证据。
3. 冻结 `paper/claims.jsonl`：每项声明标记 `supported|refuted|mixed|inconclusive`、证据定位、适用域和禁止外推范围。

## 多轮构建

阅读[论文多轮迭代](references/iterative-paper-development.md)和[统一质量审计结构](references/quality-audit-schema.md)，维护 `paper/iterations.jsonl`。论文不是实验报告拼接；围绕一条主论证选择必要内容，删除不服务主张的实验。

内部产物保存在 `.research/paper/`：

- `manuscript.md` 或 `manuscript.tex`：当前唯一正文；
- `claims.jsonl`：正文声明—证据映射；
- `figures/`：由冻结产物生成的图表；
- `iterations.jsonl`：每轮论证与修改；
- `unified-quality-audit.md`：统一顶会标准下的重要性、新颖性、理论、正确性、实验、稳健性、复现、伦理与表达审计；
- `quality-audit.json`：十个质量维度的结构化状态、理由和证据定位，以及审稿隔离元数据；控制平面只校验结构和证据是否可定位，不替代科学判断；
- `review.md`：隔离模拟审稿；
- `reproducibility.md`：Artifact、环境、预算和复现结果。

用户输出 `outputs/04-论文与投稿审计.md`，只概括最终贡献、论文入口、证据边界、统一质量审计、复现状态和审稿结论；正文与内部审计材料不混排。确定投稿会议后另行联网核验当届提交规则，该步骤不改变科学结论。

## 边界

- 不新增未预注册的确认性假设；结果后发现只能标为探索性。
- 不因任何投稿选择改写不支持的主张，不隐藏负结果、失败 run 或协议偏离。
- 不以语言润色关闭科学问题；模拟审稿指出证据缺口时返回理论、实验或 Artifact 阶段。
- 模拟审稿最高结论为 `agent-review-cleared`，仅表示自动化内部审查没有未关闭的致命问题；不得输出 `submission-ready`，最终投稿判断仍需独立外部审阅。
- 未经用户授权不提交论文、不公开仓库、不上传数据或使用外部付费服务。
