# Research runtime contract

`agent/runtime/research/researchctl.py` 是 Research Agent 的确定性控制平面。Markdown 保存科研内容；JSON/JSONL 保存机器状态。不得手工覆盖 `control/events.jsonl`、`control/decisions.jsonl`、实验 registry 或 run outcome。

## 初始化与恢复

```bash
python agent/runtime/research/researchctl.py init research/<topic> --topic "<topic>" --research-type benchmark --gpu-hours 0 --cost 0
python agent/runtime/research/researchctl.py status research/<topic>
python agent/runtime/research/researchctl.py verify-log research/<topic>
python agent/runtime/research/researchctl.py audit-scope research/<topic>
python agent/runtime/research/researchctl.py audit-proposal research/<topic>
python agent/runtime/research/researchctl.py audit-theory research/<topic>
python agent/runtime/research/researchctl.py audit-protocol research/<topic>
python agent/runtime/research/researchctl.py audit-pre-experiment research/<topic>
```

初始化默认关闭外部算力、受限数据、人类参与研究和外部发布权限。只有用户明确授权后才能运行 `authorize`；记录必须说明授权原因。

初始化后若用户批准新的资源上限，使用 `set-budget --gpu-hours <n> --cost <n> --reason <reason>` 更新；新预算不得低于已记录用量，禁止手工修改项目配置绕过事件登记。

## 阶段转换与决策

```bash
python agent/runtime/research/researchctl.py transition research/<topic> problem-framing --reason "start scoped design"
# 写入并审查 research/<topic>/.research/review/scope.md 后：
python agent/runtime/research/researchctl.py audit-scope research/<topic>
python agent/runtime/research/researchctl.py transition research/<topic> literature-mapping --reason "scope frozen" --evidence research/<topic>/.research/review/scope.md
python agent/runtime/research/researchctl.py decide research/<topic> --decision "select D2" --reason "distinguishing experiment is feasible" --alternative D1 --evidence research/<topic>/.research/proposal/selected-direction.md
```

控制器拒绝非法跳转、空上游产物和缺少上游产物的转换。生产阶段与验收阶段分开；`complete` 会执行不可绕过的完整产物、协议和 run 终局检查。回退会增加 iteration；旧产物和失败理由不删除。

进入文献映射前必须通过问题范围审计；进入 `theory-building` 前必须通过 Proposal 实验前科学门禁；进入 `experiment-protocol` 前必须通过理论审计。Proposal 门禁要求四轴状态、`Q-K-M-D-C`、分层 threat register、结果—贡献矩阵和计划中的决定性实验，但不要求实验已经执行。理论审计要求稳定的 Claim/Hypothesis/Prediction 标识、至少一个竞争解释、不同于竞争解释的可观察预测、反证条件和实验映射。协议冻结前必须通过设计与分析计划审计，并覆盖全部理论预测。

`control/state.json` 分别保存 `proposal_decision`、`novelty_status`、`empirical_status` 和 `execution_readiness`。旧项目升级 gate policy 后必须运行 `migrate-policy` 和 `revalidate-policy`，不能沿用旧 `pass` 的含义。

`audit-pre-experiment` 是实验前终点：它同时复核四道门禁、实验前新颖性刷新、当前阶段和冻结协议一致性，成功状态为 `ready-for-explicit-execution-decision`。该状态不构成运行 Pilot、使用 GPU 或提交远端任务的授权。

## 协议与实验

```bash
python agent/runtime/research/researchctl.py freeze-protocol research/<topic>
python agent/runtime/research/researchctl.py register-experiment research/<topic> --id exp-001 --claim C1 --hypothesis H1 --purpose "distinguish H1 from H0"
python agent/runtime/research/researchctl.py register-run research/<topic> --id run-001 --experiment exp-001 --config configs/run-001.json --code-revision <commit> --environment <digest> --seed 1
python agent/runtime/research/researchctl.py finish-run research/<topic> --id run-001 --status failed --reason "OOM" --artifact runs/run-001/manifest.json
```

协议冻结按完整文件集合计算 SHA-256，并归档正文和各成员文件；具体归档与授权规则见下方 v6 契约。任何冻结成员改动都要求生成新版本。`protocol-audit.md` 必须声明被审查的 Protocol ID/version，并与正文和结构化设计一致。实验和 run 只能在匹配阶段登记，ID 不可重复。run 配置必须存在且记录 SHA-256，成功 run 必须提供实际产物及其 SHA-256。失败、超时、取消和无效运行同样写入 append-only outcome。注册 run 时执行权限、非负数值与预算检查；实际消耗超预算仍保留结果并显式标记。

所有变更命令使用 `.research/control/.research.lock` 串行执行。事件链可以发现非预期修改，但不是密码学签名或外部时间戳；具有文件写权限的攻击者仍可能重算整条链，因此不能把它表述为防篡改证明。

控制器只登记和治理实验，不直接执行任意 shell、SSH 或 GPU 作业。执行器必须是后续独立组件，并消费已注册的结构化 run。

## execution-contract-v6：冻结、授权和运行证据

当前 schema 为 4，门禁策略为 `proposal-evidence-v7`；下述v6执行契约继续适用。Python 审计、阶段转换和迁移复核共用 `gates.py` 的阶段要求。

`freeze-protocol` 只在 `experiment-protocol` 阶段运行，且不能存在未登记终局的 run。冻结文件集合包含：`protocol.md`、`design.json`、`analysis-plan.md`、`protocol-audit.md`、范围、Proposal、理论正文、理论声明及预测。归档同时保存 `experiments/protocols/vNNN.md`、`vNNN.bundle/` 和 `vNNN.lock.json`，当前锁与 `protocol-frozen` 事件必须一致。冻结文件的正文、配置或分析方法发生变化都需要新版本，不能只保持 protocol.md 不变。

`design.json` 新增以下声明：

```json
{
  "required_permissions": [],
  "research_materials": {
    "mode": "external",
    "sources": [{"url": "https://example.org/dataset", "version": "v1", "selection": "test split, 50 samples"}]
  }
}
```

示例链接是格式占位符，实际研究必须替换为已核验来源。材料可以是一个或多个数据集，不设固定数量；生成或无数据研究使用 `mode: generated|none` 并填写 `rationale`。通用报告使用“数据与研究材料”，课题专用处理方法由研究设计决定。

用户明确授权执行后，将原始指令或可定位的指令记录保存在项目内部证据文件中，再登记：

```bash
python agent/runtime/research/researchctl.py authorize-execution research/<topic> true --evidence control/user-execution.md --reason "用户已明确要求执行当前协议"
python agent/runtime/research/researchctl.py transition research/<topic> pilot --reason "授权及协议门禁通过"
```

授权记录绑定协议版本、文件集合哈希及指令证据 SHA-256。新版本不能复用旧授权记录；已有用户授权涵盖新版本时可据原始指令直接登记，无须重复确认。撤销使用同一命令的 `false`。冻结设计声明的资源权限必须先通过 `authorize` 登记，不能用 `register-run --permission none` 绕过。审计文件里的 `Execution authorization` 只描述设计时授权情况，不代替控制平面的有效授权事件。

主实验入口还要求 `experiments/pilot-gate.json`：

```json
{
  "protocol_version": 1,
  "decision": "pass",
  "run_ids": ["pilot-001"],
  "reviewer": "独立试点评审角色",
  "rationale": "测量、操纵、方差和成本满足协议要求"
}
```

所有引用必须是当前协议下执行成功的 Pilot run，登记配置与结果产物的 SHA-256 必须匹配，不能引用不存在、未结束或旧版本的 run。人工科学审查仍需核实 rationale；JSON 字段不证明操纵真的有效。

`finish-run --artifact` 接受项目内部的非空文件；目录产物应先生成含成员哈希的 manifest 文件并登记该文件。`succeeded` 必须有产物；`failed`、`timed-out` 可用日志作为产物。只有具有可核验产物的这些执行终局才推进实证状态：Pilot 为 `pilot`，主实验/稳健性为 `tested`。取消、无效运行以及仅登记未执行的 run 不会推进状态。`tested` 只表示已发生可核验的主实验执行，不表示结论为正或论文已完成。

v6 对登记表与事件链做双向核对，删除任何已登记运行或终局记录都会阻止门禁通过。产物清单使用以下固定格式（哈希须替换为真实 SHA-256）：

```json
{
  "manifest_schema": 1,
  "files_sha256": {
    "runs/run-001/raw.json": "<64 位小写 SHA-256>"
  }
}
```

成员路径相对于项目内部 `.research/`，沿用 runtime 路径映射规则，不相对于清单所在目录。清单可引用嵌套清单；登记终局和后续审计均递归检查成员存在、路径边界与哈希。`manifest.json`、`*.manifest.json` 或包含 `manifest_schema` / `files_sha256` 字段的 JSON 被视为清单；格式错误不能作为普通文件跳过检查。普通结果 JSON 和日志仍可直接登记。清单只能证明列出的文件，不能证明未列出产物的完整性。

配置被修改或删除时，运行只能以 `invalid` 或 `cancelled` 关闭，并填写真实原因和实际消耗。终局保留配置变化标记及关闭时可读取的配置哈希，原登记哈希不变；这类终局不产生实证进度，也不能作为 Pilot 成功证据。它们允许后续回到协议阶段重新冻结，避免无法关闭的运行阻塞研究。其他终局仍要求配置匹配。

`blocked` 记录暂停前阶段，恢复时必须先返回该阶段，再按正常转换推进或回退。

### 旧项目迁移

```bash
python agent/runtime/research/researchctl.py migrate-policy research/<topic> --reason "升级执行证据门禁"
python agent/runtime/research/researchctl.py revalidate-policy research/<topic>
```

迁移把旧配置、状态和当前协议锁保存到 `control/migrations/`。已进入实验或后续阶段的项目回到协议设计阶段；不会删除历史运行和结果，也不会给历史记录补造阶段、授权或证据。旧 run 缺少新版登记事件及阶段绑定时不能用于新版实证状态或 Pilot 门禁。

补齐新设计字段，审计并冻结下一协议版本，登记有效执行授权后才能继续。旧版通过状态不可静默沿用。仍在运行的历史任务须先按真实情况登记终局，再冻结新协议；迁移不自动执行或重跑任何实验。


## 持久证据任务

`taskqueue.py` 仅管理已初始化项目的取证工作，不推进阶段、不授权或启动实验。所有变更均验证项目事件链与当前策略；待迁移项目只能查看队列，完成迁移和重验后再变更。宿主按研究价值选择下一任务；任务完成只表示已登记产物与验收解释，不表示科学门禁通过。

```bash
python agent/runtime/research/taskqueue.py research/example add read-source --question "原文是否支持当前主张？" --acceptance "定位正文、核查方法与限制" --inputs review/sources/paper.txt
python agent/runtime/research/taskqueue.py research/example list
python agent/runtime/research/taskqueue.py research/example claim read-source --owner reader
# 宿主实际阅读并写入论文卡；使用 claim 返回的 token：
python agent/runtime/research/taskqueue.py research/example finish read-source --token CLAIM_TOKEN --outputs review/papers/paper.md --note "已核对正文位置与限制，见论文卡"
python agent/runtime/research/taskqueue.py research/example add synthesize --question "证据是否相互支持？" --acceptance "解释共识、冲突与访问缺口" --depends read-source
```

路径相对 `.research/`；输入与产物必须是非空文件，不能逃逸项目、使用 `control/` 或包含符号链接；本地来源需使用稳定的实际文件路径。仅登记实际依赖；远端来源应保存本地正文/版本记录再作为输入，队列不能自动感知网页变更。依赖只能引用已有任务，阻止循环；每次领取生成新凭证。文件内容、上游尝试版本或上游产物变化都会阻止旧结果复用，`list` 的 `usable/ready` 是当前版本的计算结果，`reasons` 区分输入变化、产物变化、依赖不可用和上游尝试变化。依赖图按拓扑顺序检查，每次操作内同一文件只校验一次，损坏记录或循环依赖会明确报错并保留原文件。

失败使用 `fail ID --token TOKEN --note 原因`。来源永久丢失或决定放弃时，先核实外部工作已停止，再用 `cancel ID --note 对账发现及取消理由` 关闭任务；无需恢复已丢失输入。取消保留已有输入/产物哈希、撤销旧凭证并阻止下游继续。取消登记不会停止外部进程。中断后先检查原任务、现有产物及外部调用是否结束，再执行 `reconcile ID --note 对账发现及重试理由`；它归档旧尝试、更新现有输入的哈希并撤销旧凭证，重新领取后再做工作。改用其他输入或改变问题时建立新任务，保留旧记录。不得因等待超时直接重试外部提交，不得把反证标成工具失败。重复无新增依据的重试须返回范围/策略判断。

`control/tasks.json` 将队列与尝试历史原子写入同一文档，并共用项目锁；写盘使用独占临时文件、文件 fsync 和原子替换，失败保留原文件并清理临时文件，不宣称具备断电后的跨文件事务保证；不保证外部工具恰好执行一次，没有自动心跳、租约回收或后台工作进程。来源修订只会使依赖结果不可复用，宿主仍须更新受影响的论文卡、主张和报告，并通过 `researchctl.py` 登记科学回退。

## proposal-evidence-v7：Proposal证据验收

取消Proposal固定完整循环次数及连续稳定检索次数，保留迭代历史。七项科学要求见[验收契约](../../research-proposal/references/acceptance-criteria.md)，运行时检查`proposal/acceptance.json`、当前方案和证据快照、独立审查声明及未解决致命威胁。证据改变需重新审查；哈希与字段验证不证明科学正确性或真实独立性。理论和实验执行门禁不由本次策略自动放宽。

旧项目先`migrate-policy <topic> --reason "adopt proposal-evidence-v7"`，再`revalidate-policy <topic>`。迁移保存旧控制状态、重置旧门禁，不虚构新的通过记录；若新验收不足，返回受影响阶段补证。无需为旧项目补造历史循环。

Proposal生成入口按问题缺口调度，详见[问题到方案](../../research-proposal/references/problem-to-proposal.md)。七项验收的`mechanism`键可承载系统设计依据、测量效度或形式关系，保留键名不代表所有研究必须进行因果中介分析；此次为语义说明，无新schema或机器门槛。
