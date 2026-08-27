# 每日 AI 研究雷达：运行与调度

## 能力边界

`daily-ai-radar` 生成带检索窗口和来源记录的每日快照。它不是毫秒级实时流，也不替代全文精读。对于学术论文，“实时”更合理地定义为按固定时区每日增量检索，因为 arXiv、会议和引文数据库本身存在发布与索引延迟。

## 推荐架构

```text
定时触发
  -> 多源增量发现
  -> 标识符去重/版本关联
  -> 权威记录核验
  -> 多维热点画像
  -> 摘要级证据检查
  -> 与历史日报比较
  -> radar/YYYY/YYYY-MM-DD.md
  -> 高价值论文进入 scholarly-search / paper-analysis
```

## 数据源

- arXiv：最新预印本和版本更新；记录 category、submitted/updated 时间和 arXiv ID。
- OpenAlex：日期/主题检索、引用网络和 related works。注意 publication date 不等于索引更新时间。
- Semantic Scholar：论文图谱、引用和基于种子论文的 recommendations。
- 官方 proceedings/DBLP：核验会议、年份、track、paper type 和正式版本。
- 官方代码/数据/模型页：记录 artifact，不用 stars/downloads 代替科学评价。
- 官方研究机构页面：只收录研究型发布，并与同行评议证据分开。

## 调度选择

### 方案 A：Codex/ChatGPT 自动化

如果当前客户端提供定时自动化，可每天北京时间 08:30 运行：

```text
使用 $daily-ai-radar 检索过去 24 小时的 AI 研究动态，重点关注 LLM Agent、模型量化、长上下文、记忆与推理评测。核验论文身份和状态，去重版本，生成 radar/YYYY/YYYY-MM-DD.md；没有高置信热点时输出 quiet-day 报告。不要提交或推送外部仓库。
```

客户端功能和可用权限可能变化，应以当前官方 OpenAI 文档和界面为准。

### 方案 B：GitHub Actions（当前已实现）

`.github/workflows/daily-ai-radar.yml` 每天 UTC 00:30（北京时间 08:30）运行无密钥采集器，执行离线测试和日报审计，并将变化提交回仓库。它生成基于 metadata/abstract 的发现日报和精读队列，不生成未经全文核验的科研结论。

### 方案 C：Windows 任务计划程序

适合本机常开。任务每天触发 Codex 可调用的受支持入口或数据采集脚本。若机器关机、休眠或网络不可用，本次任务会延迟或失败，因此应保留失败日志和补跑窗口。

## 建议配置

- 时区：`Asia/Shanghai`
- 运行时间：每天 `08:30`
- 默认窗口：过去 24 小时，并回看 72 小时捕获延迟索引
- 重点主题：LLM Agent、quantization/compression、long context、memory、reasoning、agent evaluation
- 日报上限：10 条 lead items；其余进入 watchlist
- 每周汇总：比较 7 天历史，只提升持续增长或有新证据的主题
- 每月校准：抽样核查热点排序与后续正式发表/复现，调整筛选规则

## 可靠性要求

- 使用 DOI、arXiv、OpenReview、DBLP 或 OpenAlex ID 去重。
- 保存首次发现时间和来源，不用文件生成时间代替论文发布时间。
- API 失败时标记 source unavailable，不能输出“今日无论文”。
- 预印本、投稿中论文、正式论文和机构发布必须分开。
- 旧热点没有新证据时不重复占位。
- 报告保存后运行 `powershell -File scripts/audit-radar.ps1 radar`；GitHub Actions 已将它设为提交前硬门禁。

## 本地运行

```text
node tests/test-ai-radar.mjs
node scripts/collect-ai-radar.mjs
powershell -File scripts/audit-radar.ps1 radar
```

配置位于 `config/ai-radar.json`。`radar/index.json` 保存跨日稳定身份和首次/最近发现时间；`radar/queue.json` 是持久候选状态，`radar/queue.md` 是其可读视图。后续流程更新 JSON 中的 `status`，新一轮采集不会丢弃旧候选。
