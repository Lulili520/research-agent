import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import {classifyItems, markdown, mergeItems, selectDailyPapers} from "./radar.mjs";

const config = JSON.parse(fs.readFileSync(path.resolve("agent/radar.json"), "utf8"));
assert.equal(config.maxLeadItems, 3);
assert.equal("selection" in config, false, "不得保留绝对热度门槛");

const items = [
  {stableId: "arxiv:1", arxivId: "1v1", title: "Agent Memory", abstract: "An LLM agent memory method.", authors: ["A"], published: "2026-08-27T00:00:00Z", updated: "2026-08-27T00:00:00Z", url: "https://arxiv.org/abs/1", status: "preprint", sources: ["arXiv"], researchAreas: [], citedByCount: 0, hfUpvotes: 0},
  {stableId: "openalex:dup", title: "Agent Memory", abstract: "Duplicate.", authors: ["A"], published: "2026-08-27", updated: "2026-08-27", url: "https://openalex.org/dup", status: "indexed-work", sources: ["OpenAlex"], researchAreas: [], citedByCount: 1, hfUpvotes: 0},
  {stableId: "arxiv:2", arxivId: "2v1", title: "Vision Language Robot", abstract: "A vision-language-action robot policy.", authors: ["B"], published: "2026-08-25T12:00:00Z", updated: "2026-08-25T12:00:00Z", url: "https://arxiv.org/abs/2", status: "preprint", sources: ["arXiv"], researchAreas: [], citedByCount: 0, hfUpvotes: 0},
  {stableId: "doi:zenodo", doi: "10.5281/zenodo.1", title: "Repository Document", abstract: "An AI repository note.", authors: ["C"], published: "2026-08-27", updated: "2026-08-27", url: "https://doi.org/10.5281/zenodo.1", status: "indexed-work", sources: ["OpenAlex"], researchAreas: [], citedByCount: 9, hfUpvotes: 0}
];

const merged = mergeItems(items);
assert.equal(merged.length, 3, "同题论文版本应合并");
const classified = classifyItems(merged, config, new Date("2026-08-28T00:30:00Z"));
const selected = selectDailyPapers(classified, 3);
assert.equal(selected.length, 2, "应选择合格论文并排除普通 Zenodo 文档");
assert.equal(selected[0].selectionWindow, "recent");
assert.equal(selected[1].selectionWindow, "recent");
assert.notEqual(selected[0].selectionTopic, selected[1].selectionTopic, "候选发现阶段可用主题差异扩大覆盖");

const report = {date: "2026-08-28", arxivDiscoveryDays: 30, arxivDiscoveryStart: "2026-07-29T00:30:00Z", generatedAt: "2026-08-28T00:30:00Z", timezone: "Asia/Shanghai", analysisLevel: "abstract-screening", papers: selected, provenance: [], failures: []};
const rendered = markdown(report);
for (const heading of ["# 每日 AI 三篇论文精读", "## 速览", "## 精读", "## 方法附录"]) assert.ok(rendered.includes(heading));
assert.equal(rendered.includes("## 横向结论"), false);
for (const removedHeading of ["阅读顺序", "今日共同信号", "未入选观察池", "查询与来源记录"]) assert.equal(rendered.includes(removedHeading), false);

console.log("Radar tests passed.");
