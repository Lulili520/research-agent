#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const agentRoot = scriptDir;
const workspaceRoot = path.resolve(agentRoot, "..");

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
    const researchAreas = [...entry.matchAll(/<category\s+term=["']([^"']+)["']/gi)].map((match) => match[1]);
    return {
      stableId: idMatch ? `arxiv:${idMatch[1].replace(/v\d+$/, "")}` : `title:${normalizeTitle(xmlText(entry, "title"))}`,
      arxivId: idMatch ? idMatch[1] : null,
      doi: null,
      title: xmlText(entry, "title"),
      abstract: xmlText(entry, "summary"),
      authors,
      researchAreas,
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
      researchAreas: [work.primary_topic?.display_name, work.primary_topic?.subfield?.display_name].filter(Boolean),
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
    existing.researchAreas = [...new Set([...(existing.researchAreas || []), ...(item.researchAreas || [])])];
    existing.citedByCount = Math.max(existing.citedByCount || 0, item.citedByCount || 0);
    existing.abstract ||= item.abstract;
    existing.doi ||= item.doi;
    existing.arxivId ||= item.arxivId;
    existing.openAlexId ||= item.openAlexId;
    if (item.status === "published-record") existing.status = item.status;
  }
  return [...byId.values()];
}

function summarizeHotspotClusters(items) {
  const clusters = new Map();
  for (const item of items) {
    const areas = item.researchAreas?.length ? item.researchAreas : ["未分类 AI 研究"];
    for (const area of areas.slice(0, 2)) {
      const current = clusters.get(area) || {name: area, itemCount: 0, leadCount: 0, citations: 0, examples: []};
      current.itemCount += 1;
      current.leadCount += Number(item.lead);
      current.citations += item.citedByCount || 0;
      if (current.examples.length < 3) current.examples.push(item.title);
      clusters.set(area, current);
    }
  }
  return [...clusters.values()]
    .sort((a, b) => b.leadCount - a.leadCount || b.itemCount - a.itemCount || b.citations - a.citations || a.name.localeCompare(b.name))
    .slice(0, 8);
}

function previousDayWindow(now, timeZone) {
  if (timeZone !== "Asia/Shanghai") throw new Error(`Unsupported deterministic radar timezone: ${timeZone}`);
  const shanghaiOffsetMs = 8 * 3600_000;
  const localNow = new Date(now.getTime() + shanghaiOffsetMs);
  const currentLocalMidnightAsUtc = Date.UTC(localNow.getUTCFullYear(), localNow.getUTCMonth(), localNow.getUTCDate());
  const end = new Date(currentLocalMidnightAsUtc - shanghaiOffsetMs);
  const start = new Date(end.getTime() - 24 * 3600_000);
  return {start, end};
}

function classifyItems(items, config, now, history = {}) {
  const {start: primaryStart, end: primaryEnd} = previousDayWindow(now, config.timezone);
  const lookbackStart = new Date(primaryEnd.getTime() - config.lateIndexLookbackHours * 3600_000);
  const terms = config.topics.flatMap((topic) => topic.terms.map((term) => ({topic: topic.name, term: term.toLowerCase()})));
  return items.map((item) => {
    const haystack = `${item.title} ${item.abstract}`.toLowerCase();
    const matchedTopics = [...new Set(terms.filter(({term}) => haystack.includes(term)).map(({topic}) => topic))];
    const relevance = matchedTopics.length;
    const published = item.published ? new Date(item.published) : null;
    const updated = item.updated ? new Date(item.updated) : published;
    const seen = history[item.stableId];
    const publishedYesterday = published && published >= primaryStart && published < primaryEnd;
    const updatedYesterday = updated && updated >= primaryStart && updated < primaryEnd && (!published || updated > published);
    const delayedDiscovery = !seen && published && published >= lookbackStart && published < primaryStart;
    let state = "continuing";
    if (!seen && publishedYesterday) state = "new";
    else if (delayedDiscovery) state = "late-indexed";
    else if (seen && updatedYesterday && new Date(seen.lastUpdated || 0) < updated) state = "updated";
    const inWindow = Boolean(publishedYesterday || updatedYesterday || delayedDiscovery);
    const sourceCount = new Set(item.sources).size;
    const hasAbstract = Boolean(item.abstract);
    const aiContext = item.sources.includes("arXiv") || config.aiContextTerms.some((term) => haystack.includes(term.toLowerCase()));
    const ageDays = published ? Math.max(1, (primaryEnd - published) / 86400_000) : null;
    const citationVelocityPerDay = ageDays ? (item.citedByCount || 0) / ageDays : 0;
    const hotspotSignals = [];
    if (sourceCount >= config.selection.leadIfIndependentSources) hotspotSignals.push("多源独立收录");
    if (item.citedByCount >= config.selection.leadIfEarlyCitations) hotspotSignals.push("早期引用关注");
    if (citationVelocityPerDay >= config.selection.leadIfCitationVelocityPerDay) hotspotSignals.push("引用增长较快");
    const lead = inWindow && state !== "late-indexed" && hasAbstract && (
      sourceCount >= config.selection.leadIfIndependentSources ||
      item.citedByCount >= config.selection.leadIfEarlyCitations ||
      citationVelocityPerDay >= config.selection.leadIfCitationVelocityPerDay
    );
    return {...item, matchedTopics, relevance, sourceCount, state, inWindow, aiContext, publishedYesterday,
      citationVelocityPerDay, hotspotSignals, lead: lead && aiContext};
  }).filter((item) => item.inWindow && item.aiContext && item.abstract)
    .sort((a, b) => Number(b.lead) - Number(a.lead)
      || Number(b.publishedYesterday) - Number(a.publishedYesterday)
      || b.sourceCount - a.sourceCount
      || b.citationVelocityPerDay - a.citationVelocityPerDay
      || b.citedByCount - a.citedByCount
      || new Date(b.updated || b.published || 0) - new Date(a.updated || a.published || 0));
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

  const {end: primaryEnd} = previousDayWindow(now, config.timezone);
  const lookback = new Date(primaryEnd.getTime() - config.lateIndexLookbackHours * 3600_000).toISOString().slice(0, 10);
  for (const query of config.discoveryQueries) {
    const url = `https://api.openalex.org/works?search=${encodeURIComponent(query)}&filter=from_publication_date:${lookback},has_abstract:true&sort=publication_date:desc&per_page=25`;
    try {
      const response = await fetchWithRetry(url);
      const parsed = parseOpenAlex(await response.json());
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
  const stateLabels = {new: "昨日新增", "late-indexed": "延迟补录", updated: "昨日更新", continuing: "持续", corrected: "更正"};
  const statusLabels = {preprint: "预印本", "published-record": "正式记录", "indexed-work": "索引记录"};
  const lines = [
    `# AI 研究热点日报 — ${report.date}（回顾前一日）`,
    "",
    `- 分析窗口：${report.primaryStart} 至 ${report.primaryEnd}`,
    `- 延迟索引回看起点：${report.lookbackStart}`,
    `- 时区：${report.timezone}`,
    `- 生成/更新时间：${report.generatedAt}`,
    `- 失败或延迟来源：${report.failures.length ? report.failures.join("；") : "无"}`,
    `- 个性化研究映射：${report.topics.join("、")}（不参与热点准入和排序）`,
    "",
    "## 昨日热点概览",
    "",
    report.leads.length ? `${report.leads.length} 个条目具有可核验的多源关注或早期传播信号，${report.watch.length} 个新近条目保留观察。热点表示前一日受到关注，不代表科学质量已经确认。` : "平静日：前一自然日没有条目达到当前可核验热点门槛；这不表示没有 AI 研究发布。",
    "",
    "## 热点方向总结",
    ""
  ];
  if (!report.clusters.length) lines.push("未形成具有足够证据的方向簇。", "");
  report.clusters.forEach((cluster, index) => lines.push(
    `${index + 1}. **${cluster.name}**：覆盖 ${cluster.itemCount} 个新近条目，其中 ${cluster.leadCount} 个具有热点信号；代表条目：${cluster.examples.join("；")}。`
  ));
  lines.push(
    "",
    "## 昨日热点条目",
    ""
  );
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
    `- 热点依据：${item.hotspotSignals.join("、") || "仅新近发布"}；独立来源=${item.sourceCount}；早期引用=${item.citedByCount}；日均引用≈${item.citationVelocityPerDay.toFixed(2)}`,
    `- 与你的研究关系：${item.matchedTopics.length ? item.matchedTopics.join("、") : "暂无直接匹配"}（仅作后置标注，不影响排名）`,
    `- 限制：当前仅完成自动发现；方法、结果、artifact与有效性必须经过全文精读`,
    `- 建议动作：引文扩展`,
    ""
  ));
  lines.push("## 新近研究观察", "", "| 条目 | 状态 | 个性化主题映射 | 未进入热点的原因 | 重新检查条件 |", "|---|---|---|---|---|");
  report.watch.forEach((item) => lines.push(`| [${item.title}](${item.url}) | ${stateLabels[item.state] || item.state} | ${item.matchedTopics.join("、") || "无直接匹配"} | 尚无足够的独立关注或传播信号 | 新来源、年龄归一化引用、artifact 或正式发表记录 |`));
  if (!report.watch.length) lines.push("| 无 | | | | |");
  lines.push("", "## 查询与来源记录", "", "| 来源 | 完整查询 | 结果数 | 状态 |", "|---|---|---:|---|");
  report.provenance.forEach((row) => lines.push(`| ${row.source} | ${row.query.replace(/\|/g, "\\|")} | ${row.results} | ${row.status} |`));
  lines.push("", "## 限制", "", "- 当前热点依据来自学术索引的多源收录和早期引用，尚未覆盖社交讨论、下载量、GitHub 增长及全部官方发布，因此是学术热点代理信号。", "- 热度不等于质量；方法有效性、实验严谨性和科研价值需要后续精读。", "- 索引延迟、API 失败、早期关注偏差和版本关联可能改变后续结论。", "- 个性化主题只用于解释热点与你的研究有何关系，不参与全域热点筛选。", "");
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

export {classifyItems, markdown, mergeItems, parseArxiv, parseOpenAlex, previousDayWindow, summarizeHotspotClusters};

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const configPath = path.resolve(argValue("--config", path.join(agentRoot, "radar.json")));
  const outputRoot = path.resolve(argValue("--output-root", path.join(workspaceRoot, "data", "radar")));
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
  const primaryWindow = previousDayWindow(now, config.timezone);
  const report = {
    schemaVersion: 2,
    date: new Intl.DateTimeFormat("en-CA", {timeZone: config.timezone, year: "numeric", month: "2-digit", day: "2-digit"}).format(now),
    generatedAt,
    primaryStart: primaryWindow.start.toISOString(),
    primaryEnd: primaryWindow.end.toISOString(),
    lookbackStart: new Date(primaryWindow.end.getTime() - config.lateIndexLookbackHours * 3600_000).toISOString(),
    timezone: config.timezone,
    outputLanguage: config.outputLanguage,
    topics: config.topics.map((topic) => topic.name),
    clusters: summarizeHotspotClusters(classified),
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
