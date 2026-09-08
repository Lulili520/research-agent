#!/usr/bin/env python3
"""Q-HIST v9 的本机只读模型服务入口；推理实现继承冻结 v8 后端。"""

import qhist_model_server as base
import qhist_v9_spec as spec


class InferenceStateV9(base.InferenceState):
    def summary(self):
        value = super().summary()
        value["protocol_version"] = spec.PROTOCOL_VERSION
        return value


def main() -> int:
    base.InferenceState = InferenceStateV9
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
