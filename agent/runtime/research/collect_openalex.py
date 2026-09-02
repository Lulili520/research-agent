#!/usr/bin/env python3
"""Collect deduplicated OpenAlex candidates for one research project's search plan."""

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path


QUERIES = {
    "error-recovery": "LLM agent error recovery trajectory",
    "memory": "LLM agent memory long horizon",
    "reflection": "language agent reflection failure experience",
    "evaluation": "LLM agent trajectory evaluation benchmark",
    "context": "LLM agent context compression history",
    "poisoning": "LLM agent memory poisoning",
    "self-correction": "LLM self correction external feedback agent",
}


def abstract(work: dict) -> str:
    inverted = work.get("abstract_inverted_index") or {}
    positioned = [(position, token) for token, positions in inverted.items() for position in positions]
    return " ".join(token for _, token in sorted(positioned))


def fetch(query: str, per_page: int, mailto: str) -> list[dict]:
    params = urllib.parse.urlencode({
        "search": query,
        "filter": "from_publication_date:2022-01-01",
        "per-page": per_page,
        "mailto": mailto,
    })
    request = urllib.request.Request("https://api.openalex.org/works?" + params, headers={"User-Agent": f"Research-Agent/1.0 ({mailto})"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)["results"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    parser.add_argument("--mailto", required=True)
    parser.add_argument("--per-query", type=int, default=35)
    args = parser.parse_args()
    records: dict[str, dict] = {}
    for cluster, query in QUERIES.items():
        for work in fetch(query, args.per_query, args.mailto):
            source_id = (work.get("doi") or work["id"]).replace("https://doi.org/", "doi:").replace("https://openalex.org/", "openalex:")
            location = work.get("primary_location") or {}
            source = location.get("source") or {}
            item = records.setdefault(source_id, {
                "source_id": source_id,
                "title": work.get("display_name"),
                "year": work.get("publication_year"),
                "stable_url": work.get("doi") or location.get("landing_page_url") or work["id"],
                "venue": source.get("display_name"),
                "type": work.get("type"),
                "cited_by_count": work.get("cited_by_count", 0),
                "open_access_url": (work.get("open_access") or {}).get("oa_url"),
                "abstract": abstract(work),
                "clusters": [],
                "queries": [],
            })
            if cluster not in item["clusters"]:
                item["clusters"].append(cluster)
            if query not in item["queries"]:
                item["queries"].append(query)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(records.values(), key=lambda item: (-len(item["clusters"]), -item["cited_by_count"], -(item["year"] or 0), item["title"] or ""))
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for item in ordered:
            stream.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(json.dumps({"candidates": len(ordered), "output": str(path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
