// Unit tests for the pure helpers. Run with: npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import { buildQuery, formatBytes, formatDateTime, formatScore, humanize, yesterdayIso } from "./format.ts";
import { parseHash } from "./router.ts";

test("formatBytes picks a readable unit", () => {
  assert.equal(formatBytes(512), "512 B");
  assert.equal(formatBytes(2048), "2.0 KB");
  assert.equal(formatBytes(5 * 1024 * 1024), "5.0 MB");
  assert.equal(formatBytes(null), "—");
});

test("formatDateTime shows local time without seconds", () => {
  assert.equal(formatDateTime("2026-10-09T01:32:10"), "2026-10-09 01:32");
  assert.equal(formatDateTime(null), "—");
  const utc = formatDateTime("2026-10-09T10:00:00Z");
  assert.match(utc, /^2026-10-09 \d\d:00$/); // converted to the viewer's time zone
});

test("formatScore keeps one decimal", () => {
  assert.equal(formatScore(91.84), "91.8");
  assert.equal(formatScore(50), "50");
  assert.equal(formatScore(null), "n/a");
});

test("humanize turns enum values into sentence case", () => {
  assert.equal(humanize("FILE_DOWNLOAD"), "File download");
  assert.equal(humanize("FALSE_POSITIVE"), "False positive");
  assert.equal(humanize("USB_TRANSFER"), "USB transfer");
  assert.equal(humanize("download_mb"), "Download MB");
});

test("buildQuery skips empty filters", () => {
  assert.equal(buildQuery({ status: "OPEN", risk_level: "", user_id: null, page: 2 }), "?status=OPEN&page=2");
  assert.equal(buildQuery({ search: undefined }), "");
});

test("yesterdayIso handles month boundaries", () => {
  assert.equal(yesterdayIso(new Date(2026, 9, 1)), "2026-09-30");
});

test("parseHash reads page and id", () => {
  assert.deepEqual(parseHash("#/alerts/12"), { page: "alerts", id: 12 });
  assert.deepEqual(parseHash("#/users"), { page: "users", id: null });
  assert.deepEqual(parseHash("#/nonsense/abc"), { page: "dashboard", id: null });
  assert.deepEqual(parseHash(""), { page: "dashboard", id: null });
});
