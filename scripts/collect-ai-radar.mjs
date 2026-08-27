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
    const aiContext = item.sources.includes("arXiv") || config.aiContextTerms.some((term) => haystack.includes(term.toLowerCase()));
    const lead = inWindow && hasAbstract && relevance >= config.selection.minimumRelevance && (
      sourceCount >= config.selection.leadIfIndependentSources ||
      relevance >= config.selection.leadIfRelevance ||
      item.citedByCount >= config.selection.leadIfEarlyCitations
    );
    return {...item, matchedTopics, relevance, sourceCount, state, inWindow, aiContext, lead: lead && aiContext};
  }).filter((item) => item.inWindow && item.aiContext && item.relevance >= config.selection.minimumRelevance)
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
  const stateLabels = {new: "新增", "late-indexed": "延迟发现", updated: "实质更新", continuing: "持续", corrected: "更正"};
  const statusLabels = {preprint: "预印本", "published-record": "正式记录", "indexed-work": "索引记录"};
  const lines = [
    `# AI 研究热点日报 — ${report.date}`,
    "",
    `- 主要窗口：${report.primaryStart} 至 ${report.generatedAt}`,
    `- 延迟索引回看：${report.lookbackStart} 至 ${report.generatedAt}`,
    `- 时区：${report.timezone}`,
    `- 生成/更新时间：${report.generatedAt}`,
    `- 失败或延迟来源：${report.failures.length ? report.failures.join("；") : "无"}`,
    `- 跟踪主题：${report.topics.join("、")}`,
    "",
    "## 今日信号",
    "",
    report.leads.length ? `${report.leads.length} 个条目通过确定性核心门槛，${report.watch.length} 个条目保留在观察列表。通过门槛表示值得进一步核验，不代表论文质量已经得到确认。` : "平静日：没有条目通过确定性核心门槛。这不表示当天没有 AI 研究发布。",
    "",
    "## 核心条目",
    ""
  ];
  if (!report.leads.length) lines.push("无。", "");
  report.leads.forEach((item, index) => lines.push(
    `### ${index + 1}. ${item.title}`,
    "",
    `- 类型/状态：论文 / ${statusLabels[item.status] || item.status}`,
    `- 变化状态：${stateLabels[item.state] || item.state}`,
    `- 身份：${item.authors.slice(0, 6).join("、") || "不可用"}；${item.stableId}；${item.url}`,
    `- 首次公开/更新：${item.published || "不可用"} / ${item.updated || "不可用"}`,
    `- 访问级别：摘要元数据`,
    `- 原文摘要：${item.abstract.slice(0, 500)}${item.abstract.length > 500 ? "…" : ""}`,
    `- 雷达信号：相关主题=${item.relevance}（${item.matchedTopics.join("、")}）；独立来源=${item.sourceCount}；早期引用=${item.citedByCount}；artifact/证据质量=尚未评估`,
    `- 限制：当前仅完成自动发现；方法、结果、artifact与有效性必须经过全文精读`,
    `- 建议动作：引文扩展`,
    ""
  ));
  lines.push("## 观察列表", "", "| 条目 | 状态 | 主题 | 未进入核心的原因 | 重新检查条件 |", "|---|---|---|---|---|");
  report.watch.forEach((item) => lines.push(`| [${item.title}](${item.url}) | ${stateLabels[item.state] || item.state} | ${item.matchedTopics.join("、")} | 来源或相关性门槛不足 | 新来源、引用、artifact或正式发表状态 |`));
  if (!report.watch.length) lines.push("| 无 | | | | |");
  lines.push("", "## 查询与来源记录", "", "| 来源 | 完整查询 | 结果数 | 状态 |", "|---|---|---:|---|");
  report.provenance.forEach((row) => lines.push(`| ${row.source} | ${row.query.replace(/\|/g, "\\|")} | ${row.results} | ${row.status} |`));
  lines.push("", "## 限制", "", "- 当前是自动化元数据/摘要发现，不是穷尽性综述或论文质量认证。", "- 索引延迟、API失败、早期关注偏差和版本关联可能改变后续结论。", "- 标题和原文摘要保留来源语言；中文技术总结需在全文或摘要经过 Codex 核查后生成。", "");
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
  const actionLabels = {"scholarly-search identity/citation chain": "使用 scholarly-search 核验身份并扩展引文"};
  const statusLabels = {pending: "待处理", analyzing: "分析中", complete: "已完成", rejected: "已排除"};
  const lines = ["# 雷达精读候选队列", "", "| 稳定标识符 | 论文 | 主题 | 首阶段动作 | 状态 |", "|---|---|---|---|---|"];
  Object.values(queue).sort((a, b) => b.addedAt.localeCompare(a.addedAt)).forEach((item) => lines.push(`| ${item.stableId} | [${item.title}](${item.url}) | ${item.topics.join("、")} | ${actionLabels[item.action] || item.action} | ${statusLabels[item.status] || item.status} |`));
  if (!Object.keys(queue).length) lines.push("| | 暂无待处理核心条目 | | | |");
  return `${lines.join("\n")}\n`;
}

export {classifyItems, markdown, mergeItems, parseArxiv, parseOpenAlex};

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
    outputLanguage: config.outputLanguage,
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
