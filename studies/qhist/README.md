# Q-HIST 课题实现

本目录承载 Q-HIST 和其使用的 ToolSandbox 实验工具，与通用 `agent/` 分离。它是历史实验实现的源码，不附带真实实验结果，也不表示 Proposal 或科学结论已通过验证。

## 边界与版本

- `runtime/`：模型服务、资产构建、轨迹执行、判分、协议锁检查及 Bash 入口。
- `tests/unit/`：不需要模型或 ToolSandbox 的 CPU 单元测试。
- `tests/integration/`：需要 ToolSandbox 环境的构建器及审计测试。
- `search-plan.json`：课题专用 OpenAlex 查询，交给通用采集器读取。
- `requirements-toolsandbox.txt`、`requirements-precision.txt`：分离的依赖入口。
- `deploy.py`：复制源码和检查部署前提，不运行实验。

v9–v14 文件有显式跨版本导入；无版本后缀的模块也被新版复用。保留这些文件及名称以维持行为和协议可追溯性，不能只复制 v14 文件。旧 v11 启动脚本曾复用 v10 工作区；现在所有版本都要求调用者明确指定工作区，避免隐式串用。

## 源码部署

从仓库根目录执行，工作区应位于本地研究产物目录或指定磁盘：

```bash
export QHIST_WORKSPACE="$PWD/research/qhist/.research/deployment/v14"
python studies/qhist/deploy.py stage "$QHIST_WORKSPACE"
python studies/qhist/deploy.py check "$QHIST_WORKSPACE" --version 14
```

`stage` 复制完整 runtime 至 `code/` 并记录源码 SHA-256；已存在 `code/` 时拒绝覆盖。`check` 列出缺少的部署前提并返回非零状态，不把“源码已复制”当成可执行。

v14 执行器预期：

```text
$QHIST_WORKSPACE/
  code/                          完整部署源码
  toolsandbox-env/bin/python     ToolSandbox 专用环境
  precision-env/bin/python       模型推理专用环境
  models-Qwen3-32B/               对应协议版本的本地模型快照
  protocol/qhist-e0-v14-lock.json 冻结协议及所引用的协议文件
  runs/                          资产、渲染、门禁报告和实验运行
  logs/                          日志和退出码
```

`check` 只检查基础路径存在；实际运行前，`qhist_verify_v14_lock.py` 还会核验源码、协议、资产和预检报告哈希。模型、冻结协议和输入不在仓库内，必须按研究产物恢复或在新协议中构建并审计。不要用空文件、跳过锁验证或重写旧哈希来通过检查。

## 环境

通用 Agent 的安装无需本节依赖。ToolSandbox 与推理环境必须隔离：

```bash
python3.11 -m venv "$QHIST_WORKSPACE/toolsandbox-env"
"$QHIST_WORKSPACE/toolsandbox-env/bin/python" -m pip install -r studies/qhist/requirements-toolsandbox.txt
"$QHIST_WORKSPACE/toolsandbox-env/bin/python" -m pip check
```

ToolSandbox 使用仓库已有约束对应的上游 commit。`requirements-precision.txt` 从既有版本校验器提取，记录历史精度环境的关键版本；它不是完整环境锁，也不保证公共包源提供相应 CUDA wheel。历史复现必须取得原 `pip-freeze`、wheel/镜像、模型 revision 和 manifest，并通过 `runtime/qhist_verify_precision_env.py` 的完整 freeze 哈希检查。新环境需在新协议中记录并验收，不可声称等同原冻结环境。

旧环境准备脚本保留为历史配方。如需使用，必须先设置 `QHIST_BASE_PYTHON` 指向具备所需 PyTorch/Transformers 的基础解释器；脚本不再假设固定机器路径。部分旧脚本的环境名为 `quanto-env`，以相应版本入口为准。准备环境会安装或下载包，应在实际部署任务中执行。

## 验证与执行

```bash
python -m pytest -q studies/qhist/tests/unit
# 安装开发测试依赖后，在 ToolSandbox 环境运行：
"$QHIST_WORKSPACE/toolsandbox-env/bin/python" -m pip install -r requirements-dev.txt
"$QHIST_WORKSPACE/toolsandbox-env/bin/python" -m pytest -q studies/qhist/tests/integration
```

真正执行实验须具备授权、冻结协议、模型及预算，并通过通用 `researchctl.py` 登记。以下仅为部署完成后的执行入口示例：

```bash
bash "$QHIST_WORKSPACE/code/run_qhist_v14_preflight.sh"
bash "$QHIST_WORKSPACE/code/run_qhist_v14_qualification.sh" P00
bash "$QHIST_WORKSPACE/code/run_qhist_v14_trajectory.sh" P00
```

运行器保留原精度条件、种子、模型 revision、端口及拒绝覆盖规则。需要改变这些实验因素时，应修订并审计协议；可移植路径不等于可以任意改变实验条件。历史工作区不要用新版脚本原地覆盖，源码变更后旧协议锁可能按设计拒绝执行。
