# CCF 计算机科学科研 Agent

本仓库实现一个计算机科学 Research Agent：接收 topic，完成课题调研，或在用户明确要求时推进从创新审计、理论建模到实验和证据交付的长期迭代科研。

默认交付语言为简体中文；论文官方标题、稳定标识符、指标名、代码符号以及为避免科学含义失真的原文摘录可以保留来源语言，并明确标注。

## Agent 结构

```text
Research-Agent/
├── AGENTS.md                    # Codex 根级入口
├── agent/                       # Agent 定义、Skills 与运行时
│   ├── skills/                  # 独立路由的 Skills
│   ├── runtime/research/        # Research Agent 控制平面
│   ├── audit-research.ps1
│   ├── audit-iterative-research.ps1
│   └── evals.md                 # Agent 路由评测
├── research/                    # 正式调研成果
└── .gitignore
```

## 两种科研深度

| 模块 | 目标 | 内部能力 | 主要输出 |
|---|---|---|---|
| Research Agent：课题调研 | 围绕用户 topic 完成检索、精读、综合和方向分析 | 四个调研 Skills | `research/<topic>/` |
| Research Agent：迭代科研 | 从 topic 完成创新审计、理论、实验与证据交付 | `iterative-research` 与 Research runtime | `research/<topic>/` |

## Skill 能力边界

| Skill | 负责 | 不负责 |
|---|---|---|
| `review-protocol` | 冻结 CCF 范围、会议届次、paper type、任务和纳入标准 | 实际检索或根据结果事后改变规则 |
| `scholarly-search` | CCF 会议检索、venue/year/track 核验、版本关联和方向图谱 | 全文方法结论和跨论文综合 |
| `paper-analysis` | 创新点、方法、基准、结果、消融、计算成本和代码精读 | 宣称方向覆盖全面 |
| `evidence-synthesis` | 方法分类、发展脉络、可比实验、权衡、空白和阅读路线 | 用不兼容实验拼排行榜 |
| `iterative-research` | 相关工作、创新审计、理论预测、实验迭代、证据和 Artifact 的端到端编排 | 为追求正结果隐藏失败、事后改假设或自动取得外部授权 |

## 迭代科研流程

当用户明确要求“围绕 topic 开展/完成科研”时进入：

```text
topic
→ 问题空间与约束
→ 候选发现与身份/版本核验
→ 50–100 篇左右的纳入语料与覆盖矩阵
→ 至少 15 篇核心近邻全文精读
→ 检索饱和与最近工作反向检索
→ Proposal 生成、新颖性审计与方向选择
→ 理论/机制模型、竞争解释和可证伪预测
→ Claim—Hypothesis—Prediction—Experiment 映射与理论审计
→ 实验设计、预先分析计划与协议审计
→ 冻结实验协议，等待明确执行指令
→ 试点验证测量、方差、成本和复现性
→ 主实验
→ 消融、稳健性、反例和独立复核
→ 声明—run ID—原始产物审计
→ Artifact 构建与独立验证
→ 中文报告撰写与审查
→ 不可绕过的完成门禁
```

这是一套可回退状态机：新工作推翻创新时返回方向阶段，理论没有区分性预测时返回问题阶段，试点暴露指标或实现问题时返回协议阶段，主实验反驳假设时保留负结果并分析边界。只有用户明确要求长期科研时才启用，不会把普通文献调研自动升级成昂贵实验。

Research runtime 使用 `.research/control/` 保存项目配置、状态、事件链和决策日志；调研、Proposal、理论和实验材料分别进入对应阶段目录。初始化示例：

```powershell
python agent/runtime/research/researchctl.py init research/<topic> --topic "<topic>" --research-type benchmark --gpu-hours 0 --cost 0
```

完整命令与权限、协议和实验登记规则见 `agent/skills/iterative-research/references/runtime-contract.md`。

## 目标课题调研流程

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

新增能力时，应优先在 `agent/skills/<new-skill>/` 增加独立 Skill，并在 `AGENTS.md` 中登记模块目标、输入、输出、边界和交接条件，避免继续把所有功能堆进单一调研流程。
