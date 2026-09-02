---
name: evidence-synthesis
description: 将已分析的计算机科学论文综合为方法分类、发展脉络、benchmark 比较、权衡和可追溯研究方向；不用于尚未完成检索或全文提取的材料。
---

# 证据综合

1. 只使用经过核验的检索记录和论文卡片；检查范围、版本、访问级别和声明定位是否足以支持综合。
2. 为关键结论建立 claim ID，标记 `reported`、`derived`、`inference` 或 `proposal`，并关联来源与定位。
3. 按问题定义、方法机制、训练/推理策略、benchmark、资源假设和 artifact 组织方法分类与时间线。
4. 只有实验设置充分兼容时才比较数值；否则比较协议差异和定性权衡，不拼接排行榜。
5. 保留相互矛盾的结果并分析可能原因，不用多数票掩盖差异。
6. 研究空白必须阅读[空白验证规则](references/research-gap-validation.md)；构建研究方向还须阅读[研究方向构建规则](references/research-direction-construction.md)。每个方向都要有最近工作差异、反向检索、科学意义、可证伪问题、可行控制和负结果价值。
7. 新颖性只能按检索覆盖给出 `exploratory`、`provisional` 或 `audited` 状态，不承诺“绝对无人做过”。

形成正式 Proposal 时调用 `research-proposal` 的新颖性审计和模板；先完成证据地图、失败模式与最近近邻比较，再生成方案，禁止围绕预设想法选择性综合。

默认生成中文综合，官方题名和标识符保留原文。保存时参考[综合输出模板](assets/synthesis-output.md)，确保报告中的关键结论可回溯到 evidence ledger。
