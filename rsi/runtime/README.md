# 运行时接口

本实现独立于旧工程，Python 3.10+ 标准库。SQLite 事务事件是机器事实源，材料以 SHA256 快照保存。框架不提供模型账号、联网搜索服务或隐式实验授权。

## 两种运行方式

1. 宿主 Agent 使用自己的检索/阅读工具，通过 `task → claim → submit` 保存真实动作与结果。评审须交给独立上下文/人员，不能更换字符串身份后自签。
2. `run --team` 调用角色对应的独立进程。每个进程从 stdin 读 JSON 请求，使用自身可用工具，stdout 只返回 JSON；日志写 stderr。每项任务一个新进程，不复用作者会话做独立评审。

适配器拥有宿主授予的权限：进程隔离不是安全沙箱。接入前限制文件、网络、预算及外部写权限。`authority` 明示不授权实验/付费/发布，但恶意适配器不会被这一 JSON 自动隔离。不要执行未经审查的 Team 配置。

## 生命周期

```bash
python -m rsi init research/example --topic '用户研究问题' --outcome both
python -m rsi status research/example
python -m rsi maintain research/example
python -m rsi audit research/example
```

`init` 创建负责人任务；不存在模型时不会伪造后续研究。`maintain` 为新报告安排评审，为来源变化安排更新；评审产生的问题自动生成整改任务。`run` 调用 Worker 处理这些任务，直到独立内审通过、真实阻塞或本轮任务预算用尽。

pending → running → completed / blocked / failed。中断遗留 running 需要 `recover <project> <task> --reason '核验结果' --retry|--cancel`，以免重复具有外部副作用的动作。完成任务不自动关闭 finding。输入过期的 pending 任务取消并回到重规划，旧运行结果不能直接覆盖新证据。

## Team

配置保存在用户指定路径，不是内置模型默认值。例如：

```json
{
  "protocol": "rsi-evidence-1",
  "workers": {
    "leader": {"id": "planner", "command": ["/path/to/adapter", "--role", "leader"], "timeout_seconds": 300},
    "searcher": {"id": "finder", "command": ["/path/to/adapter", "--role", "searcher"]},
    "reader": {"id": "reader", "command": ["/path/to/adapter", "--role", "reader"]},
    "synthesizer": {"id": "writer", "command": ["/path/to/adapter", "--role", "synthesizer"]},
    "designer": {"id": "designer", "command": ["/path/to/adapter", "--role", "designer"]},
    "theorist": {"id": "theorist", "command": ["/path/to/adapter", "--role", "theorist"]},
    "reviewer": {"id": "critic", "command": ["/path/to/adapter", "--role", "reviewer"], "context_isolation": "fresh-process"}
  }
}
```

路径仅示意，需要实现的适配器必须能实际读取本地材料、加载 Skills 并调用所需检索工具。可复用模型，但评审上下文及身份与贡献者分开；运行时只能检查身份和请求，不验证供应商是否暗中共享上下文。缺少角色会报告 missing-worker。

```bash
python -m rsi run research/example --team /absolute/path/team.json --max-tasks 20 --parallel 3
```

任务预算不是质量阈值。可以继续调用 run 恢复；blocked/failed 先解释原因并对账。

## Worker 请求与回交

请求包含 protocol、project、task、system_snapshot、root_instructions、skills、materials、knowledge、relations、open_findings、authority。material 的 path 指向真实不可变快照；每份引用形如：

```json
{"key": "paper-a", "version": 1, "sha256": "完整64位哈希"}
```

正常响应：

```json
{
  "status": "completed",
  "summary": "做了什么、证据改变了什么判断",
  "artifacts": [],
  "nodes": [],
  "edges": [],
  "tasks": []
}
```

至少包含实际材料、知识、评审或后继任务，不能只有总结。被阻塞返回 `{"status":"blocked","summary":"实际尝试与结果","needed":"缺少什么"}`。

材料字段：key（稳定）、kind、title、content、parents（证据版本）、metadata。kind 为 source/figure/paper-note/search-log/analysis/literature/proposal。每种正式报告只有一个稳定 key；候选用 idea 节点和 analysis 保存，不争抢正式正文。更新同一 key 自动产生新版本，旧正文、贡献者和评审保留。

source.metadata 必须含 origin 和 access（abstract/full-text/data/code），还应记录实际来源版本。paper-note.metadata 建议记录已读章节、未读内容、理解核验和失败点；填这些字段并不证明理解。

报告必须有证据依赖。任务输入是上下文，只有适当类型被继承为证据；报告不会反向成为来源下载的证据。显式 parents 可以补充依赖，但不能用正文自证。

知识节点：id、kind、text、epistemic、evidence。kind 为 question/paper/claim/gap/idea/hypothesis/argument/decision；epistemic 为 reported/derived/inference/proposal。非 proposal 要有证据引用及 locator。修改同一 id 需 change_reason，自动增加版本。关系指定 `from/to: {id,version}`、relation、reason；用于支持、冲突、派生和候选演化，不只存向量相似度。

任务字段：role、objective、acceptance、inputs、dependencies（已存在任务 ID）。若同一响应要串起新生成材料，可先提交材料，再在下一任务里引用返回版本；不要猜哈希。多份工件可一次提交，但 parents 必须是当前已存在/刚提交的明确引用。

运行时按原子事务提交，每个任务绑定实际执行的系统快照。系统或证据在执行中变化会拒绝直接提交，需要对账。并行分支冲突不靠最后写入者覆盖解决。

## 捕获真实文件与图

```bash
python -m rsi capture research/example --record /path/to/artifact.json --actor reader
```

record 可用 content_file（相对 record 所在目录或绝对路径）代替 content，适合 PDF、裁剪后的方法图和已有 Markdown。源文件只读取，快照按内容寻址。figure.metadata 指定 format（png/jpg/svg/webp）；图导出为 `outputs/assets/<key>-v<version>.<format>`，正文用相对路径引用。每个版本保留自己的图，不让替换图片悄悄改变旧报告。

## 独立评审

reviewer 响应必须包含 review，不能同时改写材料或分派自己的整改任务。评审结构：

- target：当前报告引用；reviewed_refs：正文及全部传递证据依赖。
- dimensions：六维检查，每维 status、reason，supported/partial 需要 evidence（版本引用 + locator）；not-applicable 需要 alternative_check，必要维度不能整体豁免。
- probes：question、answer、check、result（supported/partial/failed）、evidence。检查的是内容，不是标题/字数。
- findings：dimension、severity、concern、location、impact、action、role、closure_check、evidence。
- resolutions：finding_id、disposition（resolved/retained/withdrawn）、reason、evidence。

### 读者契约与正文检查

需要解释性报告时，在报告 `metadata.reader_contract` 中登记当前用户的读者背景，而不是让评审自行假设专业水平：

```json
{
  "audience": "由当前用户目标决定的读者描述",
  "assumed_knowledge": ["明确允许依赖的基础知识"],
  "required_checks": ["mechanism", "worked-example", "condition-change", "evidence-boundary"]
}
```

检查名由任务决定，以上仅示例，不是所有科研类型的固定题库。独立评审须提交 `reader_check`：相同 `audience`、`method: "model-text-audit"`、非空 `limitations`，以及 `exercises`。每个练习含 `check_id`、实际 `question`、`response`、`result`（supported/partial/failed）、定位**当前报告**的 `evidence`、`gaps` 和 `outside_knowledge` 字符串数组。检查覆盖声明任务；需要未提供背景或有缺口时不得 supported。未通过的练习还须提供 `finding_refs`，引用本次 major/fatal finding 唯一的 `review_note_id`；该 finding 带相同 `reader_check_id` 并引用当前正文，不能以另一项无关问题代替解释整改。普通来源核验依旧保留，不能由本项替代。

程序检查版本、记录和缺口的一致性，不知道读者真的懂了多少，也不能自动证明关联finding的自然语言处置充分。当前接口只记录模型文本审计；真实人类理解研究需另有受试和结果证据，不能把 method 字符串换成人类试验。状态会单列 `reader`，历史报告没有契约则显示 `not-assessed`，不追溯宣称通过。新增此可选契约不改写旧事件；变更或移除既有报告契约必须在 metadata 提供 `reader_contract_change_reason`，并产生新版本重新评审。`restore`保留当前读者要求，只恢复旧内容和原来源；若用户确实改变读者目标，应显式capture新契约而非借恢复旧稿绕过。

dim 名称见 [contracts.py](contracts.py) 与 [内容评估](../skills/research-review/references/evaluation-and-evolution.md)。引用仅有格式正确不等于内容支持，评审者必须真正核验。

每个 finding 会创建实际任务，resolved 必须针对更新后的正文；误报可在同一版本 withdrawn。任务完成后 finding 仍 open，直到独立复核。来源或报告新版本使旧审阅不再可复用。review-cleared 只表示当前版本记录通过独立内审。

## 研究与系统历史

```bash
python -m rsi checkpoint research/example --label '检索扩大后' --reason '直接近邻改变了原结论'
python -m rsi history research/example
python -m rsi diff research/example literature 1 2
python -m rsi restore research/example literature 1 --actor maintainer --reason '撤回错误改写，等待复核'
```

检查点保存证据、知识和质量状态，可用多个 `--parent` 表示分支合并。恢复旧内容产生新版本，原依赖不被暗换为新来源，旧验收不会复活。

Agent 版本库放用户指定的独立目录，如仓库 `.rsi-history/`，不是新科研课题：

```bash
python -m rsi system --library .rsi-history snapshot --root . --label baseline --hypothesis '固定改进前基线' --author maintainer
python -m rsi system --library .rsi-history list
python -m rsi system --library .rsi-history evaluate --result /path/to/comparison.json --assessor independent-reviewer
python -m rsi system --library .rsi-history promote EVALUATION_ID --reason '对照证据支持接纳'
python -m rsi system --library .rsi-history checkout VERSION_ID /new/isolated/workspace
python -m rsi system --library .rsi-history rollback VERSION_ID --reason '实用中出现重大回归'
python -m rsi system --library .rsi-history audit
```

snapshot 保存实际 AGENTS、运行时、Skills 和测试的内容，不把 Git 提交号当未提交文件的版本。evaluate 记录 baseline/candidate、protocol_hash、cases_hash、judge_hash、budget、budget_evidence、held_out_analysis、limitations、decision 与配对结果 pairs。每对含 case、baseline_output、candidate_output、evidence、blind_mapping、outcome、critical_regression。

评估 JSON 的 `attachments` 是附件名到实际本地文件路径的映射，必须包含 protocol、cases、judge；对应哈希必须与文件内容一致。budget_evidence 和每对的 baseline_output/candidate_output/evidence/blind_mapping 引用附件名。运行时把附件完整保存为内容快照，不能只填一句“已经比较”。评估原始输入、输出、盲化映射及成本记录随版本库一起审计。blind_mapping 是评估完成后的归档，不能提前提供给评审。

结果记录目前由独立评估者提供；程序不能替你生成领域专家真值，也不证明填入的成本/盲评声明真实。发现退步或无法判断时拒绝自动 adopt。promote/rollback 只改变历史库的接纳记录；checkout 仅导出到全新目录，不覆盖工作树，不隐式运行旧代码。

## 审计边界

audit 校验事件链、快照及输出是否与已登记正文一致。结构一致性与科学质量分别显示。SQLite + 原始哈希提供事务/篡改检测，但持有全部数据库写权限者可重写整个历史；这不是可信第三方签名或多租户安全系统。

当前版本没有声称实现供应商原生适配、真实在线检索服务、跨主机任务租约、实验资源调度或无人监督的自动代码部署。需要这些能力时单独接入并验证，不能以接口存在冒充已实现。
