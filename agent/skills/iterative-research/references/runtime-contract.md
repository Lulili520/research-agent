# Research runtime contract

`agent/runtime/research/researchctl.py` 是 Research Agent 的确定性控制平面。Markdown 保存科研内容；JSON/JSONL 保存机器状态。不得手工覆盖 `control/events.jsonl`、`control/decisions.jsonl`、实验 registry 或 run outcome。

## 初始化与恢复

```powershell
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

```powershell
python agent/runtime/research/researchctl.py transition research/<topic> literature-mapping --reason "scope frozen" --evidence scope.md
python agent/runtime/research/researchctl.py decide research/<topic> --decision "select D2" --reason "distinguishing experiment is feasible" --alternative D1 --evidence selected-direction.md
```

控制器拒绝非法跳转、空上游产物和缺少上游产物的转换。生产阶段与验收阶段分开；`complete` 会执行不可绕过的完整产物、协议和 run 终局检查。回退会增加 iteration；旧产物和失败理由不删除。

进入文献映射前必须通过问题范围审计；进入 `theory-building` 前必须通过 Proposal 语料与新颖性审计；进入 `experiment-protocol` 前必须通过理论审计。理论审计要求稳定的 Claim/Hypothesis/Prediction 标识、至少一个竞争解释、不同于竞争解释的可观察预测、反证条件和实验映射。协议冻结前必须通过设计与分析计划审计，并覆盖全部理论预测。

`audit-pre-experiment` 是实验前终点：它同时复核四道门禁、当前阶段和冻结协议一致性，成功状态为 `ready-for-explicit-execution-decision`。该状态不构成运行 Pilot、使用 GPU 或提交远端任务的授权。

## 协议与实验

```powershell
python agent/runtime/research/researchctl.py freeze-protocol research/<topic>
python agent/runtime/research/researchctl.py register-experiment research/<topic> --id exp-001 --claim C1 --hypothesis H1 --purpose "distinguish H1 from H0"
python agent/runtime/research/researchctl.py register-run research/<topic> --id run-001 --experiment exp-001 --config configs/run-001.json --code-revision <commit> --environment <digest> --seed 1
python agent/runtime/research/researchctl.py finish-run research/<topic> --id run-001 --status failed --reason "OOM" --artifact runs/run-001
```

协议冻结后按字节计算 SHA-256，并归档到 `experiments/protocols/vNNN.md`；任何改动都要求生成新版本。实验和 run 只能在匹配阶段登记，ID 不可重复。run 配置必须存在且记录 SHA-256，成功 run 必须提供实际产物及其 SHA-256。失败、超时、取消和无效运行同样写入 append-only outcome。注册 run 时执行权限、非负数值与预算检查；实际消耗超预算仍保留结果并显式标记。

所有变更命令使用 `.research/control/.research.lock` 串行执行。事件链可以发现非预期修改，但不是密码学签名或外部时间戳；具有文件写权限的攻击者仍可能重算整条链，因此不能把它表述为防篡改证明。

控制器只登记和治理实验，不直接执行任意 shell、SSH 或 GPU 作业。执行器必须是后续独立组件，并消费已注册的结构化 run。
