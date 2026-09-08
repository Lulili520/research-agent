#!/usr/bin/env python3
"""Q-HIST v14 的冻结本地模型服务入口。"""

import qhist_model_server as base
import qhist_v14_spec as spec


class InferenceStateV14(base.InferenceState):
    def summary(self):
        value = super().summary()
        value["protocol_version"] = spec.PROTOCOL_VERSION
        return value


def main() -> int:
    base.InferenceState = InferenceStateV14
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
