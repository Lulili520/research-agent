# RSI 自主科研系统

围绕用户给定方向，通过 Recursive Self-Improvement（递归自改进）持续完善 **文献调研** 与 **方案设计**。

多个研究角色共享证据与问题状态，通过独立评审、定向补证和版本复核推进两条相互反馈的研究循环。科研内容与 Agent 能力分别评估，成功和失败的探索均保留可追溯记录。

## 目录结构

```text
AGENTS.md          全局流程与权限边界
rsi/
├── skills/        检索、精读、综合、设计、评审五类原子能力
├── runtime/       事务状态、证据快照、任务、评审、历史、Worker 接口
└── tests/         运行时、任务协作与证据约束测试
research/          各课题的独立材料与成果（不作为系统默认知识）
```

研究流程见 [AGENTS.md](AGENTS.md)，操作接口见 [运行时说明](rsi/runtime/README.md)，内容评估方法见 [评估与演化](rsi/skills/research-review/references/evaluation-and-evolution.md)。

## 开始

Python 3.10+，核心运行时只用标准库。

```bash
python -m rsi init research/my-topic --topic "你的研究问题" --outcome both
python -m rsi status research/my-topic
python -m rsi run research/my-topic --team /absolute/path/team.json --max-tasks 20
python -m rsi audit research/my-topic
python -m unittest discover -s rsi/tests -v
```

研究任务可由宿主 Agent 使用已有工具，通过 `claim/submit` 执行；也可由 `run --team` 调用自备的模型/工具适配器。模型服务、认证和工具权限由运行环境配置。缺少所需 Worker 时，运行时返回阻塞原因；任务预算控制执行成本，质量由内容评审判断。

长期交付是 `outputs/文献调研.md` 和 `outputs/方案设计.md`；选择 literature/proposal 时只要求相应成果。历史快照与评审保存于课题的 `.rsi/`，不混进正文。

## 历史与改进

`checkpoint / history / diff / restore` 维护研究内容历史。系统级版本库用 `system snapshot / evaluate / promote / rollback` 保存 Agent 候选、独立对照评估和接纳记录。

```bash
python -m rsi checkpoint research/my-topic --label "机制修正后" --reason "新证据改变核心假设"
python -m rsi system --library .rsi-history snapshot --root . --label baseline --hypothesis "建立可复核基线" --author maintainer
```

系统版本的接纳不修改代码工作树。先在隔离工作区形成候选、固定对照评估，再决定是否合并；不能凭自身评分自动重写规则。

## 能力边界

程序能检查来源版本、引用位置字段、角色分离、任务状态、材料哈希、评审闭合和历史一致性；不能自动证明论文理解正确、来源内容真实、评审独立无偏或研究具有创新性。

测试覆盖运行时机制与合成任务协作。真实科研质量仍需通过实际模型、原文核验、盲评和保留集对照验证。
