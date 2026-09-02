# 设计与识别规则

实验首先服务于识别，而不是覆盖尽可能多的 benchmark。明确实验单元、处理或自变量、结果变量、控制变量和主要混杂因素；说明为何对照能区分主机制与竞争解释。基线必须对应当前强方法、简单替代解释和必要的消融，不因运行成本省略最关键对照。

数据划分、模型选择、提示模板、工具环境、验证器和预算都可能成为混杂因素。记录污染与泄漏检查、失败判定、任务天花板/地板以及测量可靠性。只在任务、划分、指标和资源条件兼容时比较数值。

`experiments/design.json` 至少包含 `protocol_id`、`protocol_version`、`research_type`、`claims`、`hypotheses`、`predictions`、`experimental_units`、`independent_variables`、`dependent_variables`、`controls`、`baselines`、`data_splits`、`leakage_checks`、`metrics`、`randomness`、`resource_budget` 和 `stopping_rules`。
