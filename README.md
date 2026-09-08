# 计算机科学 Research Agent

本仓库提供可追溯的科研工作流：从用户 topic 到文献调研、Proposal、新颖性审计、理论机制、实验协议和经授权的实验研究。默认使用简体中文，研究质量要求及授权边界以 [AGENTS.md](AGENTS.md) 为准；内部审计不构成论文录用保证。

## 目录与职责

```text
AGENTS.md                         科研约束和路由
agent/
  skills/                         10 个科研 Skill、模板及参考契约
  runtime/research/               通用状态机、检索工具与跨平台审计
  audit-*.ps1                    Windows 兼容入口，委托同一 Python 审计
  evals.md                        科研行为验收场景
studies/
  qhist/                          Q-HIST / ToolSandbox 专用代码、依赖、配置与测试
research/<topic>/                 本地生成产物，Git 忽略
  outputs/                        用户阅读的成果
  .research/                      控制状态、文献、证据、协议、运行与论文源文件
tests/                            通用工具及架构边界回归
```

`agent/` 不导入或自动运行 `studies/` 的代码。课题实现可以独立部署，通过显式路径和 `researchctl.py` 登记协议与运行；通用 Agent 不预设模型、数据集或 GPU 环境。当前仓库不附带真实课题产物、模型或冻结实验工作区。

## Linux 开发环境

通用运行时仅依赖 Python 3.11+ 标准库，无需 GPU 或 PowerShell。从仓库根目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
python agent/runtime/research/researchctl.py --help
python agent/runtime/research/audit.py --help
```

默认测试包含控制平面、通用工具和 Q-HIST 的轻量单元测试。需要 ToolSandbox 的集成测试独立放置，安装与运行方式见 [Q-HIST 部署说明](studies/qhist/README.md)。模型推理及 GPU 实验不会由默认测试启动。

## 科研流程与 Skills

普通查找使用满足问题的最窄流程；系统综述才需要冻结完整综述协议。正式科研按范围、Proposal、理论、实验设计顺序推进，在协议冻结后等待用户明确执行指令。

| Skill | 职责 |
|---|---|
| review-protocol | 系统综述的范围和纳排标准 |
| scholarly-search | 论文发现、身份、版本和会议状态核验 |
| paper-analysis | 全文方法、实验和有效性分析 |
| evidence-synthesis | 分类、脉络、证据比较和有边界的研究方向 |
| research-framing | 冻结问题、分析单位、结果和资源约束 |
| research-proposal | 候选竞争、最近邻审计、机制和可反证 Proposal |
| theory-building | 理论机制、竞争解释、区分性预测及审计 |
| experiment-design | 实验协议、预先分析计划和执行门禁 |
| iterative-research | 可回退的长期科研状态机 |
| paper-development | 证据审计后的论文构建、复现与模拟审稿 |

正式研究通常预算纳入 50–100 篇、全文精读 20–30 篇，以覆盖与范围饱和为准，数量不替代质量。Proposal、实证状态和论文完成状态分开管理；未运行实验不导致 Proposal 自动失败。

初始化只建立状态，不开展检索或实验：

```bash
python agent/runtime/research/researchctl.py init research/example --topic "示例课题" --research-type benchmark --gpu-hours 0 --cost 0
python agent/runtime/research/researchctl.py status research/example
```

完整命令见 [runtime contract](agent/skills/iterative-research/references/runtime-contract.md)。状态机 schema 和 gate-policy 版本由运行时维护，旧项目须显式迁移并重新验收。

## 交付与审计

用户交付物位于 `research/<topic>/outputs/`：

1. `01-文献调研总结.md`：领域地图、全文精读、共识、争议与缺口。
2. `02-验证后Proposal.md`：方案、最近邻差异、可证伪机制和四轴状态。
3. `03-理论分析与实验探究.md`：预测—实验映射、具体资源、协议及门禁。
4. `04-论文与投稿审计.md`：仅论文阶段生成，概括证据支持的贡献与审稿状态。

检索日志、来源和论文卡放在 `.research/review/`，机器状态和事件链放在 `.research/control/`，其他内部材料按 proposal、theory、experiments、runs、paper 等阶段保存。普通查找只创建实际需要的材料。

```bash
python agent/runtime/research/audit.py review research/example
python agent/runtime/research/audit.py iterative research/example
```

审计为只读操作；退出码 0 表示结构检查通过，1 表示不满足门禁，2 表示输入目录不存在。初始化项目尚未具备完整调研产物，不能期待通过调研完成审计。Windows 可继续使用 `agent/audit-research.ps1` 和 `agent/audit-iterative-research.ps1`，它们调用同一个 Python 实现。

格式和哈希校验不能证明科学正确性。修改 Skill 或科学门禁后，还需检查 [agent/evals.md](agent/evals.md) 中的路由、证据与授权行为。

## 配置文献发现

OpenAlex 采集工具接受调用方提供的 JSON 查询表和起始日期，不含默认课题：

```bash
python agent/runtime/research/collect_openalex.py research/example/.research/review/literature/candidates.jsonl --queries studies/qhist/search-plan.json --from-date 2022-01-01 --mailto you@example.org
```

查询文件为非空 `{ "cluster": "query text" }` 对象。上述配置是 Q-HIST 示例，应替换为实际研究问题。每个查询只获取最多 `--per-query` 条候选（默认 35），不是分页穷尽检索，也不代替身份核验、全文阅读或新颖性审计。API 网络访问按实际检索任务执行。

## 扩展与迁移

新增通用能力优先放入独立 Skill；新增课题实现放入 `studies/<topic>/`，并附专用依赖、配置和部署说明。生成数据与结果仍进入 `research/`，不提交进 Agent 定义。

原 `agent/runtime/experiment/` 已迁至 `studies/qhist/runtime/`，测试迁至 `studies/qhist/tests/`。历史版本之间仍有导入依赖，需整体部署。迁移不重写旧协议哈希或实验结果；已有冻结工作区按原版本保留，新源码部署须按科研协议重新验收。

控制平面的模块边界、本轮证据门禁及后续优化顺序见 [项目结构说明](docs/architecture.md)。`execution-contract-v5` 将协议冻结、执行授权与运行证据统一校验；旧项目需要显式迁移，操作见 [runtime contract](agent/skills/iterative-research/references/runtime-contract.md#旧项目迁移)。
