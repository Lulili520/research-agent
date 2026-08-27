#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "..");

function argValue(name, fallback = undefined) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : fallback;
}

function normalizeText(value = "") {
  return value.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}

function normalizeTitle(value = "") {
  return normalizeText(value).toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff]+/g, " ").trim();
}

function xmlText(block, tag) {
  const match = block.match(new RegExp(`<${tag}(?:\\s[^>]*)?>([\\s\\S]*?)</${tag}>`, "i"));
  return match ? normalizeText(match[1].replace(/<!\[CDATA\[|\]\]>/g, "")) : "";
}

function parseArxiv(xml) {
  const entries = xml.match(/<entry>[\s\S]*?<\/entry>/gi) || [];
  return entries.map((entry) => {
    const idUrl = xmlText(entry, "id");
    const idMatch = idUrl.match(/abs\/(.+)$/);
    const authors = [...entry.matchAll(/<author>[\s\S]*?<name>([\s\S]*?)<\/name>[\s\S]*?<\/author>/gi)]
      .map((match) => normalizeText(match[1]));
    return {
      stableId: idMatch ? `arxiv:${idMatch[1].replace(/v\d+$/, "")}` : `title:${normalizeTitle(xmlText(entry, "title"))}`,
      arxivId: idMatch ? idMatch[1] : null,
      doi: null,
      title: xmlText(entry, "title"),
      abstract: xmlText(entry, "summary"),
      authors,
      published: xmlText(entry, "published"),
      updated: xmlText(entry, "updated"),
      url: idUrl,
      status: "preprint",
      sources: ["arXiv"],
      citedByCount: 0
    };
  });
}

function decodeOpenAlexAbstract(index) {
  if (!index) return "";
  const words = [];
  for (const [word, positions] of Object.entries(index)) {
    for (const position of positions) words[position] = word;
  }
  return words.filter(Boolean).join(" ");
}

function parseOpenAlex(payload) {
  return (payload.results || []).map((work) => {
    const doi = work.doi ? work.doi.replace(/^https?:\/\/doi.org\//, "").toLowerCase() : null;
    return {
      stableId: doi ? `doi:${doi}` : `openalex:${work.id?.split("/").pop()}`,
      openAlexId: work.id?.split("/").pop() || null,
      doi,
      title: normalizeText(work.title || work.display_name || ""),
      abstract: decodeOpenAlexAbstract(work.abstract_inverted_index),
      authors: (work.authorships || []).map((entry) => entry.author?.display_name).filter(Boolean),
      published: work.publication_date || null,
      updated: work.updated_date || work.publication_date || null,
      url: work.doi || work.primary_location?.landing_page_url || work.id,
      status: work.primary_location?.source?.type === "conference" ? "published-record" : "indexed-work",
      sources: ["OpenAlex"],
      citedByCount: work.cited_by_count || 0
    };
  });
}

function mergeItems(items) {
  const byId = new Map();
  const titleToId = new Map();
  for (const item of items) {
    if (!item.title) continue;
    const titleKey = normalizeTitle(item.title);
    const existingKey = byId.has(item.stableId) ? item.stableId : titleToId.get(titleKey);
    if (!existingKey) {
      byId.set(item.stableId, {...item});
      titleToId.set(titleKey, item.stableId);
      continue;
    }
    const existing = byId.get(existingKey);
    existing.sources = [...new Set([...existing.sources, ...item.sources])];
    existing.citedByCount = Math.max(existing.citedByCount || 0, item.citedByCount || 0);
    existing.abstract ||= item.abstract;
    existing.doi ||= item.doi;
    existing.arxivId ||= item.arxivId;
    existing.openAlexId ||= item.openAlexId;
    if (item.status === "published-record") existing.status = item.status;
  }
  return [...byId.values()];
}

function classifyItems(items, config, now, history = {}) {
  const primaryStart = new Date(now.getTime() - config.primaryWindowHours * 3600_000);
  const lookbackStart = new Date(now.getTime() - config.lateIndexLookbackHours * 3600_000);
  const terms = config.topics.flatMap((topic) => topic.terms.map((term) => ({topic: topic.name, term: term.toLowerCase()})));
  return items.map((item) => {
    const haystack = `${item.title} ${item.abstract}`.toLowerCase();
    const matchedTopics = [...new Set(terms.filter(({term}) => haystack.includes(term)).map(({topic}) => topic))];
    const relevance = matchedTopics.length;
    const published = item.published ? new Date(item.published) : null;
    const updated = item.updated ? new Date(item.updated) : published;
    const seen = history[item.stableId];
    let state = "continuing";
    if (!seen && published && published >= primaryStart) state = "new";
    else if (!seen && published && published >= lookbackStart) state = "late-indexed";
    else if (seen && updated && new Date(seen.lastUpdated || 0) < updated) state = "updated";
    const inWindow = (published && published >= lookbackStart) || (updated && updated >= primaryStart);
    const sourceCount = new Set(item.sources).size;
    const hasAbstract = Boolean(item.abstract);
    const lead = inWindow && hasAbstract && relevance >= config.selection.minimumRelevance && (
      sourceCount >= config.selection.leadIfIndependentSources ||
      relevance >= config.selection.leadIfRelevance ||
      item.citedByCount >= config.selection.leadIfEarlyCitations
    );
    return {...item, matchedTopics, relevance, sourceCount, state, inWindow, lead};
  }).filter((item) => item.inWindow && item.relevance >= config.selection.minimumRelevance)
    .sort((a, b) => Number(b.lead) - Number(a.lead) || b.relevance - a.relevance || b.sourceCount - a.sourceCount || b.citedByCount - a.citedByCount);
}

async function fetchWithRetry(url, attempts = 3) {
  let lastError;
  for (let attempt = 1; attempt <= attempts; attempt++) {
    try {
      const response = await fetch(url, {headers: {"User-Agent": "research-agent-radar/1.0 (https://github.com/Lulili520/research-agent)"}});
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      return response;
    } catch (error) {
      lastError = error;
      if (attempt < attempts) await new Promise((resolve) => setTimeout(resolve, attempt * 1000));
    }
  }
  throw lastError;
}

async function collect(config, now) {
  const items = [];
  const provenance = [];
  const failures = [];
  const categoryQuery = config.arxivCategories.map((category) => `cat:${category}`).join(" OR ");
  const arxivUrl = `https://export.arxiv.org/api/query?search_query=${encodeURIComponent(categoryQuery)}&start=0&max_results=100&sortBy=submittedDate&sortOrder=descending`;
  try {
    const response = await fetchWithRetry(arxivUrl);
    const parsed = parseArxiv(await response.text());
    items.push(...parsed);
    provenance.push({source: "arXiv API", query: categoryQuery, results: parsed.length, status: "ok"});
  } catch (error) {
    failures.push(`arXiv API: ${error.message}`);
    provenance.push({source: "arXiv API", query: categoryQuery, results: 0, status: error.message});
  }

  const lookback = new Date(now.getTime() - config.lateIndexLookbackHours * 3600_000).toISOString().slice(0, 10);
  for (const topic of config.topics) {
    const query = topic.terms[0];
    const url = `https://api.openalex.org/works?search=${encodeURIComponent(query)}&filter=from_publication_date:${lookback},has_abstract:true&sort=publication_date:desc&per_page=25`;
    try {
      const response = await fetchWithRetry(url);
      const parsed = parseOpenAlex(await response.json());
      items.push(...parsed);
      provenance.push({source: "OpenAlex", query, results: parsed.length, status: "ok"});
    } catch (error) {
      failures.push(`OpenAlex/${topic.name}: ${error.message}`);
      provenance.push({source: "OpenAlex", query, results: 0, status: error.message});
    }
  }
  return {items: mergeItems(items), provenance, failures};
}

function markdown(report) {
  const lines = [
    `# AI Research Radar — ${report.date}`,
    "",
    `- Primary window: ${report.primaryStart} to ${report.generatedAt}`,
    `- Late-index lookback: ${report.lookbackStart} to ${report.generatedAt}`,
    `- Timezone: ${report.timezone}`,
    `- Generated/updated: ${report.generatedAt}`,
    `- Sources failed or delayed: ${report.failures.length ? report.failures.join("; ") : "none"}`,
    `- Tracked topics: ${report.topics.join(", ")}`,
    "",
    "## Executive signal",
    "",
    report.leads.length ? `${report.leads.length} item(s) passed the deterministic lead gate; ${report.watch.length} remain on the watchlist.` : "Quiet day: no item passed the deterministic lead gate. This does not imply that no AI research was published.",
    "",
    "## Lead items",
    ""
  ];
  if (!report.leads.length) lines.push("None.", "");
  report.leads.forEach((item, index) => lines.push(
    `### ${index + 1}. ${item.title}`,
    "",
    `- Type/status: paper / ${item.status}`,
    `- State: ${item.state}`,
    `- Identity: ${item.authors.slice(0, 6).join(", ") || "unavailable"}; ${item.stableId}; ${item.url}`,
    `- First public / updated: ${item.published || "unavailable"} / ${item.updated || "unavailable"}`,
    `- Access: abstract metadata`,
    `- Source-reported abstract: ${item.abstract.slice(0, 500)}${item.abstract.length > 500 ? "…" : ""}`,
    `- Radar signals: relevance=${item.relevance} (${item.matchedTopics.join(", ")}); independent sources=${item.sourceCount}; early citations=${item.citedByCount}; artifact/evidence quality=not assessed`,
    `- Caveats: automated discovery only; method, results, artifact and validity require full-text analysis`,
    `- Recommended action: search-chain`,
    ""
  ));
  lines.push("## Watchlist", "", "| Item | State | Topics | Why not promoted | Recheck trigger |", "|---|---|---|---|---|");
  report.watch.forEach((item) => lines.push(`| [${item.title}](${item.url}) | ${item.state} | ${item.matchedTopics.join(", ")} | source/relevance gate not met | new source, citation, artifact, or formal status |`));
  if (!report.watch.length) lines.push("| None | | | | |");
  lines.push("", "## Query and provenance log", "", "| Source | Exact query | Results | Status |", "|---|---|---:|---|");
  report.provenance.forEach((row) => lines.push(`| ${row.source} | ${row.query.replace(/\|/g, "\\|")} | ${row.results} | ${row.status} |`));
  lines.push("", "## Limitations", "", "- Automated metadata/abstract discovery, not an exhaustive review or quality certification.", "- Index delays, API failures, early-attention bias and version linkage may change later conclusions.", "");
  return lines.join("\n");
}

function updateHistory(history, items, generatedAt) {
  for (const item of items) {
    const existing = history[item.stableId] || {};
    history[item.stableId] = {
      stableId: item.stableId,
      title: item.title,
      url: item.url,
      firstSeen: existing.firstSeen || generatedAt,
      lastSeen: generatedAt,
      lastUpdated: item.updated || existing.lastUpdated || null,
      sources: [...new Set([...(existing.sources || []), ...item.sources])]
    };
  }
  return history;
}

function updateQueue(queue, leads, generatedAt) {
  for (const item of leads) {
    const existing = queue[item.stableId] || {};
    queue[item.stableId] = {
      stableId: item.stableId,
      title: item.title,
      url: item.url,
      topics: item.matchedTopics,
      addedAt: existing.addedAt || generatedAt,
      lastSeen: generatedAt,
      action: existing.action || "scholarly-search identity/citation chain",
      status: existing.status || "pending"
    };
  }
  return queue;
}

function queueMarkdown(queue) {
  const lines = ["# Radar analysis queue", "", "| Stable ID | Paper | Topics | First-stage action | Status |", "|---|---|---|---|---|"];
  Object.values(queue).sort((a, b) => b.addedAt.localeCompare(a.addedAt)).forEach((item) => lines.push(`| ${item.stableId} | [${item.title}](${item.url}) | ${item.topics.join(", ")} | ${item.action} | ${item.status} |`));
  if (!Object.keys(queue).length) lines.push("| | No pending lead item | | | |");
  return `${lines.join("\n")}\n`;
}

export {classifyItems, mergeItems, parseArxiv, parseOpenAlex};

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const configPath = path.resolve(argValue("--config", path.join(repoRoot, "config", "ai-radar.json")));
  const outputRoot = path.resolve(argValue("--output-root", path.join(repoRoot, "radar")));
  const fixturePath = argValue("--fixture");
  const now = new Date(argValue("--now", new Date().toISOString()));
  const config = JSON.parse(fs.readFileSync(configPath, "utf8"));
  const indexPath = path.join(outputRoot, "index.json");
  const history = fs.existsSync(indexPath) ? JSON.parse(fs.readFileSync(indexPath, "utf8")) : {};
  const queuePath = path.join(outputRoot, "queue.json");
  const queue = fs.existsSync(queuePath) ? JSON.parse(fs.readFileSync(queuePath, "utf8")) : {};
  const collected = fixturePath
    ? JSON.parse(fs.readFileSync(path.resolve(fixturePath), "utf8"))
    : await collect(config, now);
  const classified = classifyItems(mergeItems(collected.items), config, now, history);
  const leads = classified.filter((item) => item.lead).slice(0, config.maxLeadItems);
  const watch = classified.filter((item) => !item.lead).slice(0, config.maxWatchItems);
  const generatedAt = now.toISOString();
  const report = {
    date: new Intl.DateTimeFormat("en-CA", {timeZone: config.timezone, year: "numeric", month: "2-digit", day: "2-digit"}).format(now),
    generatedAt,
    primaryStart: new Date(now.getTime() - config.primaryWindowHours * 3600_000).toISOString(),
    lookbackStart: new Date(now.getTime() - config.lateIndexLookbackHours * 3600_000).toISOString(),
    timezone: config.timezone,
    topics: config.topics.map((topic) => topic.name),
    leads,
    watch,
    provenance: collected.provenance || [],
    failures: collected.failures || []
  };
  const yearDir = path.join(outputRoot, report.date.slice(0, 4));
  fs.mkdirSync(yearDir, {recursive: true});
  fs.writeFileSync(path.join(yearDir, `${report.date}.md`), markdown(report), "utf8");
  fs.writeFileSync(path.join(yearDir, `${report.date}.json`), `${JSON.stringify(report, null, 2)}\n`, "utf8");
  fs.writeFileSync(indexPath, `${JSON.stringify(updateHistory(history, classified, generatedAt), null, 2)}\n`, "utf8");
  const updatedQueue = updateQueue(queue, leads, generatedAt);
  fs.writeFileSync(queuePath, `${JSON.stringify(updatedQueue, null, 2)}\n`, "utf8");
  fs.writeFileSync(path.join(outputRoot, "queue.md"), queueMarkdown(updatedQueue), "utf8");
  console.log(`Radar ${report.date}: ${leads.length} lead(s), ${watch.length} watch item(s), ${report.failures.length} source failure(s).`);
  if (report.failures.length && !collected.provenance?.some((row) => row.status === "ok")) process.exitCode = 2;
}
