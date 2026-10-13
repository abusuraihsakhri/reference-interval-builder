"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { interval, harrisBoyd, analyze, parseCSV, valuesFromCSV, valuesFromManual, exportCSV } = require("./app.js");

test("rank interpolation and n=120 threshold", () => {
  const data = Array.from({length: 200}, (_, i) => i + 1);
  const ri = interval(data);
  assert.ok(Math.abs(ri.lower - 5.025) < 1e-9);
  assert.ok(Math.abs(ri.upper - 195.975) < 1e-9);
  assert.equal(ri.nUsed, 200);
  assert.equal(ri.belowMin, false);
  assert.ok(ri.lowerCI[0] <= ri.lower && ri.lower <= ri.lowerCI[1]);
});
test("Tukey exclusion removes extremes and preserves original count", () => {
  const ri = interval([10,10,10,10,10,10,10,10,100]);
  assert.equal(ri.nUsed, 8);
  assert.deepEqual(ri.outliers, [100]);
  assert.equal(ri.lower, 10);
  const kept = interval([10,10,10,10,10,10,10,10,100],"overall",0.9,false);
  assert.equal(kept.nUsed, 9);
});
test("constant but different groups are flagged by partition screen", () => {
  const p = harrisBoyd([1,1,1,1],[2,2,2,2],"a","b");
  assert.equal(p.z, Infinity);
  assert.equal(p.partition, true);
  const same = harrisBoyd([1,1],[1,1],"a","b");
  assert.equal(same.partition, false);
});
test("quoted CSV with newlines, a missing measurement and finite-only parsing", () => {
  const table = parseCSV('measurement,group,notes\r\n10,A,"quoted, field"\r\n11,B,"multi\nline"\r\nNaN,A,missing\r\n12,B,ok\r\n');
  assert.equal(table.rows.length, 4);
  assert.equal(table.rows[1][2], "multi\nline");
  const extracted = valuesFromCSV(table,"measurement","group");
  assert.deepEqual([...extracted.groups.A], [10]);
  assert.deepEqual([...extracted.groups.B], [11,12]);
  assert.equal(extracted.skipped, 1);
});
test("malformed CSV, nonfinite observations and empty groups are rejected", () => {
  assert.throws(() => parseCSV('x,x\n1,2'), /unique/);
  assert.throws(() => parseCSV('x,y\n1'), /Inconsistent/);
  assert.throws(() => parseCSV('x\n"bad'), /Unterminated/);
  assert.throws(() => valuesFromManual('1 NaN 2'), /finite/);
  assert.throws(() => interval([10,Infinity]), /finite/);
  assert.throws(() => interval([10,20],"overall",1), /Unsupported/);
  assert.throws(() => analyze({}), /No usable/);
});
test("export uses stable schema and quotes arbitrary group labels", () => {
  const analysis = analyze({'group,"B"': [1,2,3,4,5]});
  const csv = exportCSV(analysis);
  assert.match(csv, /"group,""B"""/);
  assert.equal(csv.trim().split("\r\n").length, 3);
});
