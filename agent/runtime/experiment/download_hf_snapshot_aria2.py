#!/usr/bin/env python3
"""用 aria2 并发下载固定 Hugging Face revision，并按远端元数据校验文件。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def transport_complete(target: Path, expected_size: int | None) -> bool:
    """仅当实体大小正确且 aria2 控制文件消失时判定传输完成。"""
    control_path = target.with_name(target.name + ".aria2")
    return (
        target.is_file()
        and expected_size == target.stat().st_size
        and not control_path.exists()
    )


def main() -> int:
    from huggingface_hub import HfApi

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--endpoint", default="https://huggingface.co")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--connections", type=int, default=8)
    args = parser.parse_args()
    if args.workers < 1 or args.connections < 1:
        raise ValueError("workers 和 connections 必须为正数")

    info = HfApi(endpoint=args.endpoint).model_info(
        args.repo, revision=args.revision, files_metadata=True, timeout=60
    )
    if info.sha != args.revision:
        raise RuntimeError(f"revision 漂移：请求 {args.revision}，解析为 {info.sha}")
    args.output.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)

    def download(sibling):
        relative = sibling.rfilename
        target = args.output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        expected_size = sibling.size
        expected_sha = sibling.lfs.sha256 if sibling.lfs is not None else None
        control_path = target.with_name(target.name + ".aria2")
        if not transport_complete(target, expected_size):
            url = (
                f"{args.endpoint}/{args.repo}/resolve/{args.revision}/"
                f"{quote(relative, safe='/')}"
            )
            command = [
                "aria2c",
                "--continue=true",
                f"--max-connection-per-server={args.connections}",
                f"--split={args.connections}",
                "--min-split-size=4M",
                "--file-allocation=none",
                "--auto-file-renaming=false",
                "--allow-overwrite=true",
                f"--dir={target.parent}",
                f"--out={target.name}",
                url,
            ]
            aria_environment = os.environ.copy()
            for name in (
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "ALL_PROXY",
                "http_proxy",
                "https_proxy",
                "all_proxy",
            ):
                aria_environment.pop(name, None)
            subprocess.run(command, check=True, env=aria_environment)
        if control_path.exists():
            raise RuntimeError(f"{relative} 仍存在 aria2 控制文件，传输未完成")
        actual_size = target.stat().st_size
        if expected_size is not None and actual_size != expected_size:
            raise RuntimeError(
                f"{relative} 大小错误：{actual_size} != {expected_size}"
            )
        actual_sha = sha256(target)
        if expected_sha is not None and actual_sha != expected_sha:
            raise RuntimeError(
                f"{relative} SHA-256 错误：{actual_sha} != {expected_sha}"
            )
        return {
            "file": relative,
            "bytes": actual_size,
            "sha256": actual_sha,
            "expected_lfs_sha256": expected_sha,
        }

    records = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(download, item): item.rfilename for item in info.siblings}
        for future in as_completed(futures):
            record = future.result()
            records.append(record)
            print(json.dumps({"completed": record["file"], "bytes": record["bytes"]}))

    result = {
        "schema_version": 1,
        "repo": args.repo,
        "revision": info.sha,
        "endpoint": args.endpoint,
        "file_count": len(records),
        "total_bytes": sum(record["bytes"] for record in records),
        "files": sorted(records, key=lambda record: record["file"]),
        "integrity": "passed",
    }
    args.manifest.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"integrity": "passed", "files": len(records)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
