---
name: daily-ai-radar
description: 每日选择最多三篇有价值的 AI 论文，阅读全文后生成让非细分领域读者也能快速理解的中文 Markdown/PDF 晨报；不用于领域综述。
---

# 每日三篇 AI 论文精读

1. 按 `Asia/Shanghai` 生成日期命名。选文不设发表时间下限；扫描既有 `full-text` 日报，排除已经精读的稳定论文身份。版本更新只补充原记录，不作为新论文重复入选。
2. 阅读[来源与质量选择策略](references/source-and-ranking-policy.md)。优先发现历届及近届 ICML、ICLR、NeurIPS 的 Best/Outstanding Paper、Oral 和 Spotlight，再补充其他具有强证据或重要科研启发的论文。先执行重要性与证据门禁，再在同一质量层级内优先选择更新的论文；会议认可和热度都是候选线索，不参与最终质量结论。
3. `node agent/radar.mjs` 只补充新近候选，不能代表完整候选池。随后用 `scholarly-search` 从官方 program、proceedings 和 OpenReview 建立未读候选，用 `paper-analysis` 阅读问题、方法、实验、消融和限制；完成全文评价后才能确定最终三篇。无法获取正文或证据明显不足时替换候选。
4. 写作前阅读[精读表达与版式规范](references/report-presentation.md)。默认读者了解 AI 基础概念，但不了解论文所属细分领域；报告应让读者不打开原文也能理解研究问题、方法数据流、关键设计、实验逻辑和结论边界，不以摘要压缩代替讲解。
5. 每篇严格使用三个一级内容段落：`1 研究动机`、`2 方法介绍`、`3 总结归纳`。背景概念放入研究动机；方法介绍应详细、通俗，并把核心实验作为其内部小节；总结归纳包含核心贡献、证据边界和可复用启发。不得增加并列的第四部分。
6. 篇幅以逐篇精读为主；总结归纳必须从该论文的问题、方法、结果和局限直接推出科研启发、可证伪问题和可执行实验。除非用户明确要求，不读取或映射用户个人研究主题。
7. 报告只保留帮助读者理解方法、判断证据和继续研究的信息。必须基于全文重新组织解释，不能用摘要改写代替精读；元数据保持简洁。正文默认简体中文，必要术语与论文标题保留原文。
8. 全文完成后将 `analysisLevel` 改为 `full-text`，并为每篇 JSON 写入 `fullTextSource`、`fullTextPages`、问题、方法、关键证据、局限和证据定位；缺少任一项不得生成正式 PDF。
9. 下载的正式论文 PDF 直接保存到 `data/radar/<year>/<YYYY-MM-DD>/sources/`；全文抽取文本和渲染检查图片只能在日期目录的隐藏工作子目录中短暂存在。不得使用项目根 `tmp/`。
10. 在日期目录生成 `report.md`、`report.json`，再运行 `python agent/render-radar-latex.py <report.md> <report.pdf>`。LaTeX 构建必须在日期目录的隐藏构建子目录完成并自动清理；正式目录只保留三份 `report.*` 产物和 `sources/` 原始论文 PDF。
11. 逐页渲染检查 PDF 后删除检查图片并运行 `agent/audit-radar.ps1`。缺少 Tectonic 或 LaTeX 编译失败时明确报错，不得静默退回旧版 Markdown PDF。Codex Automation 只有在全文分析、PDF 验证和审计全部通过后才能提交正式报告；`abstract-screening` 草稿不得发布。

对刚发布的论文只能评价当前证据质量与阅读价值；不得据此断言长期影响力、领域地位或新颖性已经成立。
