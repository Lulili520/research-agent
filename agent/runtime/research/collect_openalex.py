#!/usr/bin/env python3
"""Collect deduplicated OpenAlex candidates for one research project's search plan."""

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path

try:
    from .stdio import configure_utf8_stdio
except ImportError:
    from stdio import configure_utf8_stdio


def load_queries(path: Path) -> dict[str, str]:
    queries = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(queries, dict) or not queries or any(
        not isinstance(k, str) or not k.strip() or not isinstance(v, str) or not v.strip()
        for k, v in queries.items()
    ):
        raise ValueError("search plan must be a nonempty JSON object of cluster: query strings")
    return queries


def abstract(work: dict) -> str:
    inverted = work.get("abstract_inverted_index") or {}
    positioned = [(position, token) for token, positions in inverted.items() for position in positions]
    return " ".join(token for _, token in sorted(positioned))


def fetch(query: str, per_page: int, mailto: str, from_date: str) -> list[dict]:
    params = urllib.parse.urlencode({
        "search": query,
        "filter": f"from_publication_date:{from_date}",
        "per-page": per_page,
        "mailto": mailto,
    })
    request = urllib.request.Request("https://api.openalex.org/works?" + params, headers={"User-Agent": f"Research-Agent/1.0 ({mailto})"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)["results"]


def main() -> None:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    parser.add_argument("--mailto", required=True)
    parser.add_argument("--per-query", type=int, default=35)
    parser.add_argument("--queries", type=Path, required=True, help="JSON object mapping cluster names to queries")
    parser.add_argument("--from-date", required=True, help="inclusive publication date, YYYY-MM-DD")
    args = parser.parse_args()
    from datetime import date
    try:
        date.fromisoformat(args.from_date)
        queries = load_queries(args.queries)
        if not 1 <= args.per_query <= 200:
            raise ValueError("--per-query must be between 1 and 200")
    except (ValueError, OSError) as error:
        parser.error(str(error))
    records: dict[str, dict] = {}
    for cluster, query in queries.items():
        for work in fetch(query, args.per_query, args.mailto, args.from_date):
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
