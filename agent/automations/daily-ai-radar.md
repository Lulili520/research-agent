# 每日 AI 论文精读 Automation

## 调度配置

- 名称：每日三篇 AI 论文精读
- 工作目录：本仓库根目录
- 计划：每天 07:00
- 时区：Asia/Shanghai
- 运行环境：已登录 ChatGPT 账号的 Codex CLI
- API Key：不需要
- 交付：审计成功后将当天 Markdown、JSON 和 PDF 推送到 GitHub

任务语义保存在本文件。当前 Windows 机器通过 `register-daily-ai-radar.ps1` 注册每天 07:00 的任务计划，并由 `run-daily-ai-radar.ps1` 调用已登录的 Codex CLI；不使用 OpenAI API Key。

## 任务提示词

你正在 `Research-Agent` 仓库中执行每日 AI 论文精读。先完整读取根目录 `AGENTS.md`，然后读取并严格执行 `agent/skills/daily-ai-radar/SKILL.md` 以及其中直接引用的规范。

以运行时的 `Asia/Shanghai` 自然日期作为报告日期。在 `data/radar/` 中检查历史全文精读记录，使用稳定论文身份和规范化标题排除已精读论文；论文换链接、更新版本或再次获关注不得被当作新论文重复收录。

联网检索仍未精读的高价值 AI 论文。优先从 ICML、ICLR、NeurIPS 的官方获奖、Oral、Spotlight、正式 proceedings 与 OpenReview 发现候选，但不得把会议标签或热度直接当作论文质量。先按问题价值、方法实质、证据强度、主张校准、可复现性和科研启发性进行门禁；质量相当时优先较新的论文。最多选择三篇，质量不足时允许少于三篇。

必须访问并阅读最终入选论文的完整正文，核验稳定身份、版本、发表状态和全文来源。搜索摘要、网页片段、新闻稿或自动采集结果只能用于发现候选，不能冒充全文精读。将正式论文 PDF 保存到 `data/radar/<year>/<YYYY-MM-DD>/sources/`。

用简体中文生成 `report.md` 和可审计的 `report.json`。默认读者了解 AI 基础概念但不了解细分领域；第一次出现的关键术语须就地解释。每篇论文只使用以下三个主体部分：

1. 研究动机
2. 方法介绍
3. 总结归纳

方法介绍应使读者不打开原文也能理解任务设定、信息流、核心模块、训练或推理过程、实验设计和关键结果；总结归纳应分别说明贡献、证据边界、局限，以及从该论文自身推出的可复用科研启发和可证伪后续问题。不得读取或强行映射用户个人研究主题。

随后运行：

```powershell
python agent/render-radar-latex.py <report.md的实际路径> <同目录/report.pdf>
powershell -File agent/audit-radar.ps1 <当日日报目录>
```

将 `report.pdf` 逐页渲染并检查中文字体、分页、段落层级、页眉页脚、溢出、重叠、乱码和空白页；清理隐藏构建目录与检查图片。正式日期目录只保留 `report.md`、`report.json`、`report.pdf` 和 `sources/*.pdf`。

只有全文精读、三份报告、来源文件、PDF 视觉检查和审计全部成功才宣告完成。任何来源不可访问、证据不足、编译失败或审计失败都必须如实说明，不得虚构、降级为摘要报告或留下看似完成的残缺产物。

Codex 任务成功退出后，外层运行器调用 `publish-daily-radar.ps1`。`radar` 是不继承 `main` 历史的纯产物分支。发布器再次检查 `analysisLevel=full-text`、论文数量和 PDF 是否存在，在隔离的临时 Git worktree 中只提交当天的 `report.md`、`report.json` 与 `report.pdf`，不提交 Agent 代码、下载的原论文 PDF，也不夹带当前工作区中的其他修改。提交或推送失败会使计划任务返回失败状态并保留本地报告；不得强制推送。
