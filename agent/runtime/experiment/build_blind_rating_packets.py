#!/usr/bin/env python3
"""为 AUTH-MED 构念 Pilot 生成随机化盲评包与隔离映射表。"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--raters", type=int, default=2)
    parser.add_argument("--seed", type=int, default=20260902)
    args = parser.parse_args()
    if args.raters < 2:
        raise ValueError("冻结协议要求至少两名独立盲评者")

    rows = [
        json.loads(line)
        for line in args.manifest.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    args.output.mkdir(parents=True, exist_ok=True)
    keys = []
    for rater_index in range(1, args.raters + 1):
        shuffled = rows.copy()
        random.Random(args.seed + rater_index).shuffle(shuffled)
        packet = []
        for position, row in enumerate(shuffled, start=1):
            opaque = hashlib.sha256(
                f"{args.seed}:{rater_index}:{position}:{row['stimulus_sha256']}".encode()
            ).hexdigest()[:12]
            blind_id = f"R{rater_index}-{opaque}"
            text = (args.manifest.parent / row["stimulus"]).read_text(
                encoding="utf-8"
            )
            packet.append(
                {
                    "blind_id": blind_id,
                    "text": text.strip(),
                    "ratings": {
                        "proposition_matches_reference": None,
                        "perceived_source_authority_0_100": None,
                        "perceived_certainty_0_100": None,
                        "counterevidence_retained": None,
                        "naturalness_1_5": None,
                        "notes": "",
                    },
                }
            )
            keys.append(
                {
                    "rater": rater_index,
                    "blind_id": blind_id,
                    "episode_id": row["episode_id"],
                    "condition": row["condition"],
                    "stimulus_sha256": row["stimulus_sha256"],
                }
            )
        (args.output / f"rater-{rater_index}.jsonl").write_bytes(
            (
                "\n".join(json.dumps(item, ensure_ascii=False) for item in packet)
                + "\n"
            ).encode("utf-8")
        )
    (args.output / "sealed-key.jsonl").write_bytes(
        ("\n".join(json.dumps(item, ensure_ascii=False) for item in keys) + "\n").encode(
            "utf-8"
        )
    )
    print(
        json.dumps(
            {
                "raters": args.raters,
                "items_per_rater": len(rows),
                "seed": args.seed,
                "key": str(args.output / "sealed-key.jsonl"),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
