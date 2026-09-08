#!/usr/bin/env python3
"""Q-HIST v12 的冻结本地模型服务入口。"""

import qhist_model_server as base
import qhist_v12_spec as spec


class InferenceStateV12(base.InferenceState):
    def summary(self):
        value = super().summary()
        value["protocol_version"] = spec.PROTOCOL_VERSION
        return value


def main() -> int:
    base.InferenceState = InferenceStateV12
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
