# 计算机科学科研 Agent

本仓库实现面向计算机科学与 CCF 推荐会议的 Research Agent。Agent 接收用户给定的 topic，完成可追溯的文献调研、新颖性审计、Proposal 构建、理论分析、实验设计与经授权的实验执行。

默认使用简体中文完成检索说明、论文分析、证据综合、限制和建议；论文官方标题、标识符、指标、代码符号及可能因翻译失真的短引文保留原文。

## 基本原则

- 工作强度与问题匹配；普通查找不强制采用系统综述流程。
- 优先使用论文全文、正式 proceedings、官方数据集、标准和可信学术索引。搜索摘要只是线索，不是证据。
- 不得虚构论文、DOI、作者、引文、结果、筛选数量或定位信息。
- 区分来源报告、可复核推导、跨来源推断和研究提案，并记录元数据、摘要、局部正文、预印本或正式版本等访问级别。
- 明示检索缺口、来源不可访问、结果冲突和不确定性；“本次未发现”不等于“尚无人研究”。
- CCF 类别只描述会议范围，不评价单篇论文质量。区分会议届次、track 和 paper type；Workshop、Demo、Short、Findings 不得自动套用主会标签。
- 影响力必须综合年龄归一化传播、官方认可、方法谱系、实际采用、artifact 传播和持续性，不能只看累计引用。
- 研究空白必须经过反向检索和最近工作比较；只能使用有范围、有日期的新颖性表述。

## 能力路由

Research Agent 接收用户给定的 topic，先经过充分调研和 Proposal 门禁，再按用户要求停在 Proposal/调研或继续实验研究。

#### 能力 A：目标课题调研

- 目标：围绕用户指定的研究问题形成可追溯的文献集合、论文分析、证据综合和研究方向。
- 内部 Skills：`review-protocol`（按需）、`scholarly-search`、`paper-analysis`、`evidence-synthesis`。
- 输入：研究问题、范围、会议/年份约束和交付深度。
- 用户输出：`research/<topic-slug>/outputs/` 下的 `01-文献调研总结.md`、`02-验证后Proposal.md` 和 `03-理论分析与实验探究.md`。第三份报告把理论机制、竞争解释、区分性预测和实验验证组织成闭环，并给出可供人工部署的具体资源环境。检索记录、论文卡片、证据账本和来源只作为内部审计材料，不与用户交付物混排。
- 边界：不得把社交热度直接当作纳入标准、论文质量或研究新颖性的证据。

#### 能力 B：迭代科研

- 目标：从用户给定 topic 出发，建立包含 50–100 篇已核验论文及 20–30 篇核心全文精读论文的证据地图，形成并审计 Proposal，再完成理论建模、实验协议、试点、主实验、稳健性分析、Artifact 构建与验证、报告撰写与审查。
- 入口：`iterative-research`；只有用户明确要求开展、推进或完成研究时触发，单纯调研或方向建议仍使用模块二。
- 输入：topic、研究目标，以及已知的数据、模型、算力、时限、伦理和交付约束；不影响方向的缺省项可以保守假设并记录。
- 用户输出仍只有 `outputs/` 下三份成果；机器状态、事件日志、文献、方向决策、理论、实验运行、证据和 Artifact 属于内部工作材料。
- 证据门禁：创新须通过最近工作比较和反向检索；理论须产生可区分预测与反证条件；主实验须先通过试点；完成须通过声明—运行—原始产物审计。
- 交接：可复用 Research Agent 能力 A 的合格上游产物；调研结束不会自动进入迭代科研，除非用户请求继续开展研究。
- 边界：不以涨点或投稿接收作为唯一成功；不得隐藏失败运行、事后改写确认性假设，或未经授权使用付费算力、受限数据、人类参与者和外部发布渠道。

## Skill 路由

项目 Skill 位于 `agent/skills/`。`agent/` 只保存 Agent 定义、Research runtime 和审计，不得写入采集结果或研究报告。

- `review-protocol`：为系统综述或严格证据审查冻结问题、范围和纳排规则。
- `scholarly-search`：发现论文并核验身份、会议状态、版本和影响力线索。
- `paper-analysis`：精读方法、实验、效率、消融、artifact 与有效性。
- `evidence-synthesis`：形成方法分类、发展脉络、证据比较和有边界的研究方向。
- `iterative-research`：编排从 topic 到理论、实验和研究交付的长期状态机，保存失败、回退与停止理由。
- `research-proposal`：从 topic 建立分层文献语料、验证检索饱和与最近近邻，输出通过范围化新颖性审计的可证伪 Proposal。
- `theory-building`：把通过审计的 Proposal 转化为构念、机制、竞争解释、区分性预测、反证条件和实验映射。
- `research-framing`：在检索前冻结研究对象、分析单位、结果、范围、反证条件、资源和伦理约束。
- `experiment-design`：把理论预测映射为实验设计和预先分析计划；审计并冻结协议，但不执行实验。

路由顺序为：判断任务深度 → 选择最窄 Skill → 检查上游证据。正式科研启动依次经过 `research-framing`、`research-proposal`、`theory-building` 和 `experiment-design`；这四步完成后停在已冻结协议，不自动执行实验。只有用户明确要求继续执行时才进入 Pilot 和后续阶段。

## 目标课题调研的阶段契约

```text
研究问题
  -> review-protocol（按需） -> protocol.md
  -> scholarly-search -> search-log.md + literature.md
  -> paper-analysis -> papers/<source-id>.md
  -> evidence-synthesis -> evidence.md + report.md
  -> 证据不足则定向补检（默认最多两轮）
  -> 声明—证据审计
```

- 检索阶段不得给出需要全文支持的方法结论；精读阶段不得暗示文献集合已经穷尽。
- 综合阶段不得引入未在已检查来源中出现的事实。
- 只有任务、数据集、划分、指标、协议和资源条件足够兼容时才能比较数值。
- “某篇论文没有评测 X”不足以证明领域级空白；上游证据不足时必须返回对应阶段。
- 检索进入精读前须具备稳定身份、发表/track 状态、访问级别、纳入理由和版本关系。
- 精读进入综合前，关键声明须具备来源、页码/章节/表图定位和有效性评价。
- 研究方向须具备最近工作差异、反向空白检索和可证伪实验；新颖性审计须记录数据库、查询、日期、引文链和未覆盖范围。
- 正式 Proposal 不是一次生成文本：必须依次留下候选竞争、等价工作碰撞、机制与反证、识别与可行性、独立反方五类内部推演记录。新证据改变核心声明、区别性预测失败或实验不可识别时必须回退；不得把重复搜索或措辞润色计作迭代。
- 广域发现不计入新颖性稳定轮次。每轮定向补检必须记录是否改变 Proposal；任何 `yes` 都会清零稳定性计数，只有最后连续两轮均为 `no` 才能声明范围饱和并把新颖性标为 `audited`。
- Proposal Builder、反方新颖性审计、理论审计和实验协议审计使用相互隔离的角色与产物。审计者不得继承“应该通过”的结论，也不得由生成者自签门禁。

声明类型使用：`reported`（来源直接报告）、`derived`（展示计算的推导）、`inference`（明确标注的综合推断）、`proposal`（待验证方案）。来源冲突必须保留并解释可能原因。

## 产物与状态

用户只需要阅读：

```text
research/<topic-slug>/outputs/
├── 01-文献调研总结.md      # 相关工作、证据共识、争议、研究缺口与参考文献
├── 02-验证后Proposal.md    # 通过新颖性与理论可行性审计的正式方案
└── 03-理论分析与实验探究.md # 理论机制、竞争解释、预测—实验映射、资源部署与执行门禁
```

三份文件是不同阶段的稳定交付物，不是内部文件的简单拼接：

- 第一份回答领域已经知道什么、证据是否可靠、还不知道什么。必须先对 50–100 篇纳入论文形成领域级分类、脉络、共识、冲突和证据强弱分析，再对 20–30 篇实际阅读全文的核心论文逐篇使用“研究动机—方法介绍—总结归纳”结构详细讲解；最后详细说明仍存在的问题、现有证据为何不足、它与最近工作的差异及可验证方式。
- 第二份只收录通过最近邻反向检索、新颖性审计和理论可证伪性检查的方案，详细说明问题重要性、精确研究问题、机制、构念、竞争解释、可证伪假设、测量、最近邻差异、贡献、风险、负结果和停止条件；未通过时必须明确写“未通过”或 `pending`，不得包装成成功 Proposal。
- 第三份把 Proposal 转成可执行实验。必须给出具体官方数据集及稳定链接、使用 split/类别/抽样数量、数据改造方式、处理与对照、每项实验的运行量、模型配置、恢复基线、指标、统计方法、门禁和停止规则；还要量化 GPU/CPU/RAM/磁盘、预计 GPU 小时、人工、日历时间、软件版本和费用计算方式。估算、已具备资源和仍需授权的资源必须分开。

以下为 Agent 内部可审计材料，按研究阶段折叠，用户无需逐项阅读：

```text
research/<topic-slug>/
├── outputs/                # 仅三份用户交付物
└── .research/              # 隐藏的内部审计与工作材料
    ├── control/              # 状态、事件与决策
    ├── review/               # 范围、检索、语料、论文卡与证据综合
    ├── proposal/             # 候选、迭代、新颖性审计与正式 Proposal
    ├── theory/               # 构念、预测、推演与理论审计
    └── experiments/          # 协议、运行登记、原始结果与分析
```

普通课题调研的 `state.md` 只记录问题、当前阶段、已完成查询、已分析来源、待解决证据、下一步、循环次数和更新时间，不作为证据来源。流程状态使用 `not-started`、`in-progress`、`blocked`、`complete`；新颖性状态独立使用 `not-assessed`、`exploratory`、`provisional`、`audited`。

迭代科研在上述调研产物之外按需增加：

```text
research/<topic-slug>/.research/
├── control/
│   ├── project.json
│   ├── state.json
│   ├── state.md
│   ├── events.jsonl
│   └── decisions.jsonl
├── review/
│   ├── scope.md
│   ├── search-log.md
│   ├── literature.md
│   ├── evidence.md
│   ├── literature/{corpus.jsonl,coverage.md,nearest-neighbors.md}
│   ├── papers/
│   └── sources/
├── proposal/
│   ├── proposal.md
│   ├── audit.md
│   ├── novelty.md
│   ├── iterations.jsonl
│   └── archive/
├── theory/
│   ├── theory.md
│   ├── claims.jsonl
│   ├── predictions.jsonl
│   ├── iterations.jsonl
│   └── audit.md
├── experiments/
│   ├── protocol.md
│   ├── pilot.md
│   ├── registry.jsonl
│   └── results.md
├── analysis.md
├── artifact/README.md
└── report.md
```

迭代科研以 `control/project.json`、`control/state.json` 和哈希链接的 `control/events.jsonl` 为机器事实源；`control/state.md` 只是人类摘要。阶段转换、决策、协议、实验和 run 必须由 `agent/runtime/research/researchctl.py` 登记，不能靠改写说明文件推进。

阶段只能在非空上游产物和语义门禁满足后推进；生产阶段与验收阶段分开。新文献、理论失败、无效测量、试点失败、主实验反证和证据冲突分别返回最早受影响阶段，并保留旧版本和原因。`complete` 转换必须通过控制平面的完整产物、协议一致性和 run 终局门禁；它可以表示假设被支持、被反驳、结果混合或当前资源下无法判定，但必须说明剩余不确定性。

完成长期研究前运行：

```powershell
powershell -File agent/audit-research.ps1 research/<topic-slug>
```

完成迭代科研前运行：

```powershell
powershell -File agent/audit-iterative-research.ps1 research/<topic-slug>
```

## 扩展新能力

新增能力模块时必须说明：模块目标、触发条件、输入、输出目录、内部 Skill、证据门禁、与现有模块的交接条件以及明确不负责的事项。优先新增独立 Skill；只有多个 Skill 共享且稳定的约束才上移到本文件。新模块不得改写现有模块的输出语义，也不得默认扩大用户授权。
