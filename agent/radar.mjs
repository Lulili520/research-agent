#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import {fileURLToPath} from "node:url";

const agentRoot = path.dirname(fileURLToPath(import.meta.url));
const workspaceRoot = path.resolve(agentRoot, "..");

const TOPICS = [
  ["AI Agent", ["agent", "tool use", "mcp", "planning", "trajectory", "harness"]],
  ["推理", ["reasoning", "test-time", "chain-of-thought", "verifier", "judge", "self-evolution", "self-evolving"]],
  ["机器人", ["robot", "robotics", "embodied", "manipulation", "navigation", "vision-language-action", "vla"]],
  ["多模态", ["multimodal", "vision-language", "vlm", "diffusion", "video", "audio", "visual"]],
  ["模型效率", ["quantization", "low-bit", "compression", "distillation", "efficient", "sparse", "moe"]],
  ["长上下文与记忆", ["long context", "memory", "retrieval", "continual learning", "recurrent"]],
  ["安全与对齐", ["safety", "alignment", "jailbreak", "security", "bias", "trustworthy"]],
  ["评测与数据", ["benchmark", "evaluation", "dataset", "leaderboard", "metric"]]
];

function argValue(name, fallback) {
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
  return (xml.match(/<entry>[\s\S]*?<\/entry>/gi) || []).map((entry) => {
    const idUrl = xmlText(entry, "id");
    const arxivId = idUrl.match(/abs\/(.+)$/)?.[1] || "";
    return {
      stableId: `arxiv:${arxivId.replace(/v\d+$/, "")}`,
      arxivId,
      title: xmlText(entry, "title"),
      abstract: xmlText(entry, "summary"),
      authors: [...entry.matchAll(/<author>[\s\S]*?<name>([\s\S]*?)<\/name>[\s\S]*?<\/author>/gi)].map((match) => normalizeText(match[1])),
      published: xmlText(entry, "published"),
      updated: xmlText(entry, "updated"),
      url: idUrl,
      status: "preprint",
      sources: ["arXiv"],
      researchAreas: [...entry.matchAll(/<category\s+term=["']([^"']+)["']/gi)].map((match) => match[1]),
      citedByCount: 0,
      hfUpvotes: 0
    };
  });
}

function decodeAbstract(invertedIndex) {
  if (!invertedIndex) return "";
  return Object.entries(invertedIndex).flatMap(([word, positions]) => positions.map((position) => [position, word]))
    .sort((a, b) => a[0] - b[0]).map((entry) => entry[1]).join(" ");
}

function parseOpenAlex(payload) {
  return (payload.results || []).map((work) => ({
    stableId: work.doi ? `doi:${work.doi.replace(/^https?:\/\/(dx\.)?doi\.org\//i, "").toLowerCase()}` : `openalex:${work.id.split("/").pop()}`,
    openAlexId: work.id,
    doi: work.doi?.replace(/^https?:\/\/(dx\.)?doi\.org\//i, "") || null,
    title: work.display_name || work.title || "",
    abstract: decodeAbstract(work.abstract_inverted_index),
    authors: (work.authorships || []).map((entry) => entry.author?.display_name).filter(Boolean),
    published: work.publication_date || work.created_date,
    updated: work.updated_date || work.publication_date,
    url: work.doi || work.id,
    status: "indexed-work",
    sources: ["OpenAlex"],
    researchAreas: (work.topics || []).map((topic) => topic.display_name).filter(Boolean),
    citedByCount: work.cited_by_count || 0,
    hfUpvotes: 0
  }));
}

function parseHuggingFace(payload) {
  return (payload || []).map((entry) => {
    const paper = entry.paper || entry;
    const arxivId = paper.id || paper.paper?.id;
    return {
      stableId: `arxiv:${String(arxivId).replace(/v\d+$/, "")}`,
      arxivId,
      title: paper.title || "",
      abstract: paper.summary || "",
      authors: (paper.authors || []).map((author) => author.name || author).filter(Boolean),
      published: paper.publishedAt || paper.published_at,
      updated: paper.submittedOnDailyAt || paper.updatedAt || paper.publishedAt,
      featuredAt: paper.submittedOnDailyAt,
      url: `https://huggingface.co/papers/${arxivId}`,
      status: "preprint",
      sources: ["Hugging Face Daily Papers"],
      researchAreas: paper.ai_keywords || [],
      citedByCount: 0,
      hfUpvotes: paper.upvotes || 0
    };
  }).filter((item) => item.arxivId && item.title);
}

function mergeItems(items) {
  const merged = new Map();
  const titleIndex = new Map();
  for (const item of items) {
    if (!item.title) continue;
    const titleKey = normalizeTitle(item.title);
    const key = merged.has(item.stableId) ? item.stableId : titleIndex.get(titleKey);
    if (!key) {
      merged.set(item.stableId, {...item});
      titleIndex.set(titleKey, item.stableId);
      continue;
    }
    const current = merged.get(key);
    current.sources = [...new Set([...current.sources, ...item.sources])];
    current.researchAreas = [...new Set([...(current.researchAreas || []), ...(item.researchAreas || [])])];
    current.citedByCount = Math.max(current.citedByCount || 0, item.citedByCount || 0);
    current.hfUpvotes = Math.max(current.hfUpvotes || 0, item.hfUpvotes || 0);
    current.abstract ||= item.abstract;
    current.doi ||= item.doi;
    current.arxivId ||= item.arxivId;
  }
  return [...merged.values()];
}

function previousDayWindow(now, timezone) {
  if (timezone !== "Asia/Shanghai") throw new Error(`Unsupported timezone: ${timezone}`);
  const offset = 8 * 3600_000;
  const local = new Date(now.getTime() + offset);
  const midnight = Date.UTC(local.getUTCFullYear(), local.getUTCMonth(), local.getUTCDate());
  const end = new Date(midnight - offset);
  return {start: new Date(end.getTime() - 24 * 3600_000), end};
}

function classifyItems(items, config, now) {
  const end = now;
  return items.map((item) => {
    const published = item.published ? new Date(item.published) : null;
    const text = `${item.title} ${item.abstract}`.toLowerCase();
    const aiRelated = item.sources.includes("arXiv") || config.aiContextTerms.some((term) => text.includes(term.toLowerCase()));
    const ageDays = published ? Math.max(1, (end - published) / 86400_000) : 1;
    const signals = [];
    if (item.sources.length >= 2) signals.push("多源确认");
    if (item.hfUpvotes > 0) signals.push(`HF ${item.hfUpvotes} 票`);
    if (item.citedByCount > 0) signals.push(`${item.citedByCount} 次早期引用`);
    if (!signals.length) signals.push("新近发布");
    return {...item, aiRelated, sourceCount: item.sources.length, citationVelocityPerDay: item.citedByCount / ageDays, signals};
  }).filter((item) => item.aiRelated !== false && item.abstract);
}

function topicOf(item) {
  const text = `${item.title} ${item.abstract} ${(item.researchAreas || []).join(" ")}`.toLowerCase();
  return TOPICS.find(([, terms]) => terms.some((term) => text.includes(term)))?.[0] || "其他 AI 研究";
}

function scholarly(item) {
  return Boolean(item.arxivId || item.sources.includes("Hugging Face Daily Papers") || (item.doi && !item.doi.toLowerCase().startsWith("10.5281/zenodo")));
}

function compareDiscoveryPriority(a, b) {
  return b.sourceCount - a.sourceCount
    || new Date(b.updated || b.published || 0) - new Date(a.updated || a.published || 0);
}

function selectDailyPapers(items, limit = 3) {
  const papers = items.filter(scholarly);
  const selected = [];
  const ids = new Set();
  const topics = new Set();
  for (const pool of [papers.sort(compareDiscoveryPriority)]) {
    for (const item of pool) {
      const topic = topicOf(item);
      if (topics.has(topic) || selected.length >= limit) continue;
      selected.push({...item, selectionTopic: topic, selectionWindow: "recent"});
      ids.add(item.stableId);
      topics.add(topic);
    }
    for (const item of pool) {
      if (selected.length >= limit) break;
      if (ids.has(item.stableId)) continue;
      selected.push({...item, selectionTopic: topicOf(item), selectionWindow: "recent"});
      ids.add(item.stableId);
    }
    if (selected.length >= limit) break;
  }
  return selected;
}

async function fetchJsonOrText(url, json = false) {
  let lastError;
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      const response = await fetch(url, {headers: {"User-Agent": "research-agent-radar/2.0"}});
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      return json ? response.json() : response.text();
    } catch (error) {
      lastError = error;
      if (attempt < 3) await new Promise((resolve) => setTimeout(resolve, attempt * 1000));
    }
  }
  throw lastError;
}

async function collect(config, now) {
  const items = [];
  const provenance = [];
  const failures = [];
  const end = now;
  const start = new Date(end.getTime() - config.arxivDiscoveryDays * 86400_000);
  const stamp = (date) => `${date.toISOString().slice(0, 10).replace(/-/g, "")}${date.toISOString().slice(11, 16).replace(":", "")}`;
  const arxivQuery = `(${config.arxivCategories.map((category) => `cat:${category}`).join(" OR ")}) AND submittedDate:[${stamp(start)} TO ${stamp(end)}]`;
  try {
    const parsed = parseArxiv(await fetchJsonOrText(`https://export.arxiv.org/api/query?search_query=${encodeURIComponent(arxivQuery)}&start=0&max_results=100&sortBy=submittedDate&sortOrder=descending`));
    items.push(...parsed);
    provenance.push({source: "arXiv", query: arxivQuery, results: parsed.length, status: "ok"});
  } catch (error) {
    failures.push(`arXiv: ${error.message}`);
    provenance.push({source: "arXiv", query: arxivQuery, results: 0, status: error.message});
  }
  const coverageDate = new Intl.DateTimeFormat("en-CA", {timeZone: config.timezone}).format(now);
  try {
    const parsed = parseHuggingFace(await fetchJsonOrText(`https://huggingface.co/api/daily_papers?date=${coverageDate}`, true));
    items.push(...parsed);
    provenance.push({source: "Hugging Face Daily Papers", query: coverageDate, results: parsed.length, status: "ok"});
  } catch (error) {
    failures.push(`Hugging Face Daily Papers: ${error.message}`);
    provenance.push({source: "Hugging Face Daily Papers", query: coverageDate, results: 0, status: error.message});
  }
  const lookbackDate = start.toISOString().slice(0, 10);
  for (const query of config.discoveryQueries) {
    try {
      const payload = await fetchJsonOrText(`https://api.openalex.org/works?search=${encodeURIComponent(query)}&filter=from_publication_date:${lookbackDate},has_abstract:true&sort=publication_date:desc&per_page=25`, true);
      const parsed = parseOpenAlex(payload);
      items.push(...parsed);
      provenance.push({source: "OpenAlex", query, results: parsed.length, status: "ok"});
    } catch (error) {
      failures.push(`OpenAlex/${query}: ${error.message}`);
      provenance.push({source: "OpenAlex", query, results: 0, status: error.message});
    }
  }
  return {items: mergeItems(items), provenance, failures};
}

function markdown(report) {
  const lines = [
    `# 每日 AI 三篇论文精读 — ${report.date}`,
    "",
    `> 自动增量候选 ${report.papers.length} 篇｜阶段：${report.analysisLevel}`,
    "",
    "## 速览",
    ""
  ];
  if (!report.papers.length) lines.push("候选库中没有尚未精读且通过身份初筛的 AI 论文。", "");
  report.papers.forEach((paper, index) => lines.push(`${index + 1}. **${paper.title}** — ${paper.selectionTopic}；${paper.signals.join("、")}。`));
  lines.push("", "## 精读", "");
  report.papers.forEach((paper, index) => lines.push(
    `### ${index + 1}. ${paper.title}`,
    "",
    `- **一句话：** ${paper.abstract.slice(0, 100)}${paper.abstract.length > 100 ? "…" : ""}`,
    "- **问题：** 待全文精读后用一句通俗中文说明。",
    `- **方法：** ${paper.abstract.slice(0, 220)}${paper.abstract.length > 220 ? "…" : ""}`,
    "- **证据：** 待核对数据集、基线、指标、消融和失败案例。",
    "- **判断：** 待区分作者结论、证据支持范围与 Agent 推断。",
    "- **Take away：** 待全文精读后给出 2-4 条可行动结论。",
    `- **候选线索：** ${paper.selectionTopic}；${paper.signals.join("、")}。`,
    `- **来源：** [论文](${paper.url})｜${paper.authors.slice(0, 5).join("、") || "作者未知"}`,
    ""
  ));
  lines.push(
    "## 方法附录",
    "",
    `- arXiv 增量发现窗口：${report.arxivDiscoveryStart} 至 ${report.generatedAt}；最终选文不设时间下限。`,
    `- 来源状态：${report.failures.length ? report.failures.join("；") : "全部成功"}`,
    "- 当前文件是候选采集结果，不代表论文质量或最终入选。",
    ""
  );
  return lines.join("\n");
}

function identityKeys(item) {
  const keys = [];
  if (item.stableId) keys.push(item.stableId.replace(/v\d+$/i, ""));
  if (item.arxivId) keys.push(`arxiv:${String(item.arxivId).replace(/v\d+$/i, "")}`);
  if (item.doi) keys.push(`doi:${String(item.doi).replace(/^https?:\/\/(dx\.)?doi\.org\//i, "").toLowerCase()}`);
  if (item.title) keys.push(`title:${normalizeTitle(item.title)}`);
  return new Set(keys);
}

function fullTextHistory(outputRoot, currentDate) {
  const seen = new Set();
  if (!fs.existsSync(outputRoot)) return seen;
  const visit = (directory) => {
    for (const entry of fs.readdirSync(directory, {withFileTypes: true})) {
      const fullPath = path.join(directory, entry.name);
      if (entry.isDirectory()) visit(fullPath);
      else if (entry.name === "report.json" && path.basename(path.dirname(fullPath)) !== currentDate) {
        try {
          const report = JSON.parse(fs.readFileSync(fullPath, "utf8"));
          if (report.analysisLevel === "full-text") for (const paper of report.papers || []) for (const key of identityKeys(paper)) seen.add(key);
        } catch {}
      }
    }
  };
  visit(outputRoot);
  return seen;
}

function updateHistory(history, items, generatedAt) {
  for (const item of items) history[item.stableId] = {stableId: item.stableId, title: item.title, url: item.url, firstSeen: history[item.stableId]?.firstSeen || generatedAt, lastSeen: generatedAt, lastUpdated: item.updated || null, sources: item.sources};
  return history;
}

export {classifyItems, fullTextHistory, identityKeys, markdown, mergeItems, parseArxiv, parseOpenAlex, parseHuggingFace, previousDayWindow, selectDailyPapers};

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const config = JSON.parse(fs.readFileSync(path.resolve(argValue("--config", path.join(agentRoot, "radar.json"))), "utf8"));
  const outputRoot = path.resolve(argValue("--output-root", path.join(workspaceRoot, "data", "radar")));
  const fixture = argValue("--fixture", null);
  const now = new Date(argValue("--now", new Date().toISOString()));
  const indexPath = path.join(outputRoot, "index.json");
  const history = fs.existsSync(indexPath) ? JSON.parse(fs.readFileSync(indexPath, "utf8")) : {};
  const collected = fixture ? JSON.parse(fs.readFileSync(path.resolve(fixture), "utf8")) : await collect(config, now);
  const dateFormat = new Intl.DateTimeFormat("en-CA", {timeZone: config.timezone});
  const reportDate = dateFormat.format(now);
  const seen = fullTextHistory(outputRoot, reportDate);
  const classified = classifyItems(mergeItems(collected.items), config, now)
    .filter((paper) => ![...identityKeys(paper)].some((key) => seen.has(key)));
  const papers = selectDailyPapers(classified, config.maxWatchItems || 15);
  const arxivDiscoveryStart = new Date(now.getTime() - config.arxivDiscoveryDays * 86400_000);
  const report = {
    schemaVersion: 5,
    analysisLevel: "abstract-screening",
    selectionPolicy: "recent-unread-quality-review",
    date: reportDate,
    coverageDate: dateFormat.format(now),
    generatedAt: now.toISOString(),
    arxivDiscoveryDays: config.arxivDiscoveryDays,
    arxivDiscoveryStart: arxivDiscoveryStart.toISOString(),
    timezone: config.timezone,
    outputLanguage: config.outputLanguage,
    excludedPreviouslyReadCount: seen.size,
    papers,
    provenance: collected.provenance || [],
    failures: collected.failures || []
  };
  const dateDir = path.join(outputRoot, report.date.slice(0, 4), report.date);
  fs.mkdirSync(dateDir, {recursive: true});
  fs.writeFileSync(path.join(dateDir, "report.md"), markdown(report), "utf8");
  fs.writeFileSync(path.join(dateDir, "report.json"), `${JSON.stringify(report, null, 2)}\n`, "utf8");
  fs.writeFileSync(indexPath, `${JSON.stringify(updateHistory(history, classified, report.generatedAt), null, 2)}\n`, "utf8");
  console.log(`Radar ${report.date}: collected ${papers.length} unread candidates; ${report.failures.length} source failure(s).`);
}
