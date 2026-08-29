# CCF Computer Science Research Agent

这是一个以 Codex 为运行时、面向计算机科学与 CCF 推荐会议论文的调研 Agent。它可以围绕技术方向检索会议论文、识别主会与 track、关联预印本和正式版本、精读方法与实验，并生成方法谱系和中文综述。

默认交付语言为简体中文；论文官方标题、稳定标识符、指标名、代码符号以及为避免科学含义失真的原文摘录可以保留来源语言，并明确标注。

## Agent 结构

```text
Research-Agent/
├── AGENTS.md                    # Codex 根级入口
├── agent/                       # Agent 本体，不存采集结果
│   ├── skills/                  # 五个科研 Skills
│   ├── radar.json               # 日报配置
│   ├── radar.mjs                # 日报采集器
│   ├── radar.test.mjs           # 确定性回归测试
│   ├── audit-radar.ps1
│   ├── audit-research.ps1
│   └── evals.md                 # Agent 路由评测
├── data/radar/                  # 每日采集数据、索引与队列
├── research/                    # 正式调研成果
└── .github/workflows/           # 自动调度
```

## 能力边界

| Skill | 负责 | 不负责 |
|---|---|---|
| `review-protocol` | 冻结 CCF 范围、会议届次、paper type、任务和纳入标准 | 实际检索或根据结果事后改变规则 |
| `scholarly-search` | CCF 会议检索、venue/year/track 核验、版本关联和方向图谱 | 全文方法结论和跨论文综合 |
| `paper-analysis` | 创新点、方法、基准、结果、消融、计算成本和代码精读 | 宣称方向覆盖全面 |
| `evidence-synthesis` | 方法分类、发展脉络、可比实验、权衡、空白和阅读路线 | 用不兼容实验拼排行榜 |
| `daily-ai-radar` | 每日 AI 论文、benchmark、artifact 和研究发布的增量发现与热点画像 | 用热度替代论文精读或科学有效性 |

## 优化后的流程

```text
计算机技术方向
  ↓
review-protocol（仅系统/严谨综述）
  └─ protocol.md
        ↓
scholarly-search
  ├─ search-log.md
  └─ literature.md（CCF/venue/year/track/type/version）
        ↓
paper-analysis
  └─ papers/<source-id>.md（method/benchmark/result/artifact）
        ↓
evidence-synthesis
  ├─ evidence.md（claim ledger）
  └─ report.md（taxonomy/timeline/tradeoffs/gaps）
        ↓
证据仍不足？
  ├─ 是 → 定向检索 → 精读 → 再综合（默认最多两轮）
  └─ 否 → 声明—证据审计 → 完成
```

长任务使用 `research/<topic>/state.md` 保存当前阶段、协议版本、已完成查询、已精读来源、未解决问题、循环次数和下一步，以支持中断恢复。

## 研究产物

```text
research/<topic>/
├── state.md
├── protocol.md                 # 仅严谨综述
├── search-log.md
├── literature.md
├── papers/<source-id>.md
├── evidence.md
├── report.md
└── sources/manifest.md
```

只创建实际需要的文件。普通论文查找不需要协议或完整产物目录。

## 使用示例

```text
$review-protocol 为“2022—2026 年 CCF-A/B 会议上的代码大模型推理优化”制定调研协议，限定主会 Full/Regular paper。

$scholarly-search 检索 2023 年以来 CCF-A/B 会议上的图神经网络推荐系统论文，核验会议届次和 track，关联 arXiv/正式版本并给出精读清单。

$paper-analysis 分析 sources/ 中的论文，提取创新点、算法流程、数据集、基线、指标、结果、消融、计算开销和代码可用性。

$evidence-synthesis 根据 papers/ 中的论文卡片生成方法分类、发展时间线、可比实验表、性能—成本权衡和研究空白。
```

端到端请求无需手动点名全部 Skills：

```text
调研 2023 年以来 CCF-A/B 会议中 RAG 用于代码生成的方法，区分主会与 Workshop/Findings，精读代表论文并总结方法谱系、基准结果、效率和研究空白。
```

每日雷达由 GitHub Actions 在北京时间约 08:30 运行，回顾前一自然日的全域 AI 热点；个人研究主题只做后置映射。输出写入 `data/radar/`，不写入 `agent/`。

本地生成并审计日报：

```text
node agent/radar.test.mjs
node agent/radar.mjs
powershell -File agent/audit-radar.ps1 data/radar
```

## CCF 使用规则

- 每次需要 CCF 分类时查询 CCF 官方当前目录，记录目录版本和访问日期。
- CCF A/B/C 仅作为会议范围标签，不作为单篇论文质量分数。
- 只有 Full/Regular paper 可以直接沿用 CCF 会议目录口径；Short、Demo、Findings、Workshop 等必须单独标注。
- 优先核验正式 proceedings；OpenReview、arXiv、代码和项目页作为关联来源保存。
- 不同数据集版本、split、指标定义、评测协议或资源条件下的结果不得直接拼接成排行榜。

## 回归检查

[agent/evals.md](agent/evals.md) 定义 Skill 路由场景、证据不变量和产物检查项。修改 `AGENTS.md` 或任何科研 Skill 后，应使用这些场景检查真实行为，而不是只检查文件格式。

保存长期调研后运行：

```text
powershell -File agent/audit-research.ps1 research/<topic>
```

该门禁检查阶段产物、状态时效、检索日志、claim ledger 和研究方向的新颖性限定。它只能发现结构性问题，不能替代论文精读、同行评审或人工新颖性判断。

## 加载机制

`AGENTS.md` 保留在仓库根目录，作为 Codex 启动时的项目入口；Skill 内容、配置、脚本和评测统一收拢在 `agent/`。`data/` 与 `research/` 只保存运行产物，避免 Agent 定义和采集内容混杂。
