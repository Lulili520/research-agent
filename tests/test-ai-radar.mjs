import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import {classifyItems, markdown, mergeItems} from "../scripts/collect-ai-radar.mjs";

const config = JSON.parse(fs.readFileSync(path.resolve("config/ai-radar.json"), "utf8"));
assert.equal(config.outputLanguage, "zh-CN", "radar reports should default to Simplified Chinese");
const fixture = JSON.parse(fs.readFileSync(path.resolve("tests/fixtures/radar-candidates.json"), "utf8"));
const merged = mergeItems(fixture.items);
assert.equal(merged.length, 2, "title-identical arXiv/OpenAlex versions should merge");
const classified = classifyItems(merged, config, new Date("2026-08-27T08:30:00Z"), {});
assert.equal(classified.length, 2, "both fixture items should be in the 72h discovery window");
const lead = classified.find((item) => item.title.startsWith("Evaluating Quantized"));
assert.equal(lead.lead, true, "multi-topic, multi-source item should pass lead gate");
assert.equal(lead.sourceCount, 2);
const watch = classified.find((item) => item.title.startsWith("A Narrow"));
assert.equal(watch.lead, false, "single-topic single-source item should remain watchlist");
assert.equal(watch.state, "late-indexed");
const rendered = markdown({
  date: "2026-08-27", primaryStart: "2026-08-26T00:00:00Z", lookbackStart: "2026-08-24T00:00:00Z",
  generatedAt: "2026-08-27T00:00:00Z", timezone: "Asia/Shanghai", failures: [], topics: ["模型量化"],
  leads: [], watch: [], provenance: []
});
for (const heading of ["# AI 研究热点日报", "## 今日信号", "## 核心条目", "## 观察列表", "## 查询与来源记录", "## 限制"]) {
  assert.ok(rendered.includes(heading), `missing Chinese heading: ${heading}`);
}
console.log("AI radar fixture tests passed.");
