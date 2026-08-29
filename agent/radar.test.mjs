import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import {classifyItems, markdown, mergeItems, summarizeHotspotClusters} from "./radar.mjs";

const config = JSON.parse(fs.readFileSync(path.resolve("agent/radar.json"), "utf8"));
assert.equal(config.outputLanguage, "zh-CN", "radar reports should default to Simplified Chinese");
const fixture = {
  items: [
    {stableId: "arxiv:2608.00001", arxivId: "2608.00001v1", title: "Evaluating Quantized LLM Agents with Long Context and Memory", abstract: "We study quantization and agent evaluation across long context, agent memory, trajectory evaluation, and tool use.", authors: ["A. Researcher"], published: "2026-08-27T00:00:00Z", updated: "2026-08-27T00:00:00Z", url: "https://arxiv.org/abs/2608.00001", status: "preprint", sources: ["arXiv"], citedByCount: 0},
    {stableId: "openalex:W1", title: "Evaluating Quantized LLM Agents with Long Context and Memory", abstract: "Duplicate indexed record.", authors: ["A. Researcher"], published: "2026-08-27", updated: "2026-08-27", url: "https://openalex.org/W1", status: "indexed-work", sources: ["OpenAlex"], citedByCount: 1},
    {stableId: "arxiv:2608.00002", title: "A Narrow Tool Use Observation", abstract: "A tool use note for language model systems.", authors: ["B. Researcher"], published: "2026-08-25T12:00:00Z", updated: "2026-08-25T12:00:00Z", url: "https://arxiv.org/abs/2608.00002", status: "preprint", sources: ["arXiv"], citedByCount: 0}
  ]
};
const merged = mergeItems(fixture.items);
assert.equal(merged.length, 2, "title-identical arXiv/OpenAlex versions should merge");
const classified = classifyItems(merged, config, new Date("2026-08-28T00:30:00Z"), {});
assert.equal(classified.length, 2, "both fixture items should be in the 72h discovery window");
const lead = classified.find((item) => item.title.startsWith("Evaluating Quantized"));
assert.equal(lead.lead, true, "multi-source previous-day item should pass hotspot gate");
assert.equal(lead.sourceCount, 2);
const watch = classified.find((item) => item.title.startsWith("A Narrow"));
assert.equal(watch.lead, false, "single-topic single-source item should remain watchlist");
assert.equal(watch.state, "late-indexed");
const rendered = markdown({
  date: "2026-08-28", primaryStart: "2026-08-26T16:00:00Z", primaryEnd: "2026-08-27T16:00:00Z", lookbackStart: "2026-08-24T16:00:00Z",
  generatedAt: "2026-08-27T00:00:00Z", timezone: "Asia/Shanghai", failures: [], topics: ["模型量化"],
  clusters: summarizeHotspotClusters(classified), leads: [], watch: [], provenance: []
});
for (const heading of ["# AI 研究热点日报", "## 昨日热点概览", "## 热点方向总结", "## 昨日热点条目", "## 新近研究观察", "## 查询与来源记录", "## 限制"]) {
  assert.ok(rendered.includes(heading), `missing Chinese heading: ${heading}`);
}
console.log("AI radar fixture tests passed.");
