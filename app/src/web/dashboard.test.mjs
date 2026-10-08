import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";

const snapshot = JSON.parse(readFileSync(new URL("./src/dashboard/snapshot.json", import.meta.url)));
const source = readFileSync(new URL("./src/dashboard/data.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const exports = {};
vm.runInNewContext(compiled, {
  exports,
  require: name => {
    assert.equal(name, "./snapshot.json");
    return { default: snapshot };
  },
});

// Companies whose Work IQ and Foundry IQ cards are backed by a local synthetic
// record. Everything else must stay honestly "unavailable".
const LOCAL_IQ_EVIDENCE = {
  "CLI-1001": { email: "EM-003", policy: "CP-012" },
  "CLI-1002": { email: "EM-024", policy: "CP-001" },
  "CLI-1007": { email: "EM-027", policy: "CP-005" },
};

const iq = (company, name) => company.evidence.find(e => e.iq === name);

test("ten distinct companies, explicit CAD units and reconciled maturity", () => {
  assert.equal(exports.companies.length, 10);
  assert.equal(new Set(exports.companies.map(c => c.id)).size, 10);
  for (const company of exports.companies) {
    assert.equal(company.exposure, null);
    assert.equal(company.revenue, null);
    assert.equal(company.asOf, exports.snapshotAsOf);
    assert.ok(Math.abs(company.maturityCad.reduce((s, m) => s + m.amount, 0) - company.commitmentCad) < .0001);
    assert.equal(company.evidence.length, 4);
    assert.deepEqual(company.evidence.map(e => e.iq), ["Fabric IQ", "Work IQ", "Foundry IQ", "Web IQ"]);
    // Web IQ has no offline record by design and must never be presented as available.
    assert.equal(iq(company, "Web IQ").status, "unavailable");
    // Fabric IQ is held locally for every company and must not regress.
    assert.equal(iq(company, "Fabric IQ").status, "synthetic");
  }
});

test("exactly three companies carry local Work IQ and Foundry IQ evidence", () => {
  const held = exports.companies
    .filter(c => iq(c, "Work IQ").status === "synthetic")
    .map(c => c.id);
  assert.deepEqual(held, Object.keys(LOCAL_IQ_EVIDENCE));
  assert.deepEqual(
    exports.companies.filter(c => iq(c, "Foundry IQ").status === "synthetic").map(c => c.id),
    Object.keys(LOCAL_IQ_EVIDENCE),
  );
});

for (const company of exports.companies) {
  const expected = LOCAL_IQ_EVIDENCE[company.id];
  test(`${company.name}: Work IQ and Foundry IQ evidence is ${expected ? "held locally and cited" : "honestly unavailable"}`, () => {
    for (const name of ["Work IQ", "Foundry IQ"]) {
      const card = iq(company, name);
      if (!expected) {
        assert.equal(card.status, "unavailable");
        assert.match(card.text, /No company-specific .* evidence selected for this snapshot\./);
        continue;
      }
      assert.equal(card.status, "synthetic");
      // Never imply live retrieval, and always name the local record shown.
      assert.match(card.text, /Not a live retrieval\.$/);
      assert.match(card.text, /Illustrative local/);
    }
    if (!expected) {
      assert.ok(!company.sources.some(s => s.includes("work-iq") || s.includes("foundry-iq")));
      return;
    }
    assert.ok(iq(company, "Work IQ").text.includes(expected.email));
    assert.ok(iq(company, "Foundry IQ").text.includes(expected.policy));
    assert.ok(company.sources.includes(`data/work-iq/emails.json#${expected.email}`));
    assert.ok(company.sources.includes(`data/foundry-iq/cm_policies.json#${expected.policy}`));
    // A firm-wide standard may not be dressed up as a company-specific document.
    const policyText = iq(company, "Foundry IQ").text;
    if (expected.policy === "CP-012") {
      assert.ok(policyText.includes(company.name));
    } else {
      assert.ok(!policyText.includes(company.name));
      assert.match(policyText, /not a company-specific document/);
    }
    // The local evidence has to reach the answers the dashboard actually serves.
    for (const topic of ["briefing", "risks", "opportunities"]) {
      const answer = exports.answerQuestion(company, topic);
      assert.ok(answer.includes(expected.email));
      assert.ok(answer.includes(expected.policy));
      // Stated once per answer rather than repeated on every evidence line.
      assert.ok(answer.includes("not live retrievals"));
    }
  });
}

for (const company of exports.companies) {
  test(`${company.name}: deterministic, scoped answers and unsupported fallback`, () => {    for (const topic of ["briefing", "opportunities", "risks", "maturity"]) {
      const answer = exports.answerQuestion(company, topic);
      assert.equal(answer, exports.answerQuestion(company.id, topic));
      assert.ok(answer.includes(company.name));
      assert.ok(answer.includes(company.asOf));
      assert.ok(answer.includes("SYNTHETIC"));
      assert.ok(answer.includes("Sources:"));
      assert.ok(!answer.includes("undefined"));
    }
    for (const unsupported of ["latest news", "risks and buy recommendation", "transfer this to live chat"]) {
      assert.ok(exports.answerQuestion(company, unsupported).includes("Supported topics:"));
    }
    const spoofed = { ...company, exposureCad: 9999999 };
    assert.equal(exports.answerQuestion(spoofed, "briefing"), exports.answerQuestion(company.id, "briefing"));
  });
}

test("answers are sectioned, and provenance is disclosed once rather than per line", () => {
  for (const company of exports.companies) {
    const answer = exports.buildAnswer(company, "briefing");
    assert.equal(answer.company, company.name);
    assert.equal(answer.asOf, company.asOf);
    assert.equal(answer.supported, true);
    // Readable structure: headline figures first, provenance folded away last.
    // Joined because arrays built inside the vm sandbox are a different realm.
    assert.equal(answer.blocks.map(b => b.title).join(" | "), [
      "Position", "Opportunities", "Risks", "Facility maturities",
      "Evidence", "Basis and caveats", "Sources",
    ].join(" | "));
    const evidence = answer.blocks.find(b => b.title === "Evidence");
    assert.equal(evidence.evidence.length, 4);
    assert.match(evidence.note, /not live retrievals/);
    // The repeated per-line disclaimer is gone from the rendered evidence.
    for (const item of evidence.evidence) assert.ok(!item.text.includes("Not a live retrieval"));
    // Long-form provenance stays available, just collapsed.
    for (const title of ["Basis and caveats", "Sources"]) {
      assert.equal(answer.blocks.find(b => b.title === title).collapsible, true);
    }
    assert.ok(answer.blocks.find(b => b.title === "Position").figures.length >= 5);
    assert.match(answer.footnote, /SYNTHETIC DEMO ONLY/);
    // One synthetic disclosure per answer, not one per line.
    assert.equal(exports.answerQuestion(company, "briefing").match(/SYNTHETIC/g).length, 1);
  }
  const unsupported = exports.buildAnswer(exports.companies[0], "latest news");
  assert.equal(unsupported.supported, false);
  assert.equal(unsupported.blocks.map(b => b.title).join(" | "), "Supported questions | Sources");
});

test("no 'cached' label survives anywhere the dashboard is rendered or printed", () => {
  // Every string the dashboard can show: the snapshot it renders from, and the
  // flattened transcript of every supported and unsupported answer.
  const rendered = [
    JSON.stringify(snapshot),
    ...exports.companies.flatMap(company => [
      "briefing", "opportunities", "risks", "maturity", "latest news",
    ].map(topic => exports.answerQuestion(company, topic))),
    exports.answerQuestion("CLI-0000", "briefing"),
    exports.snapshotDisclaimer,
    exports.snapshotUnits,
  ].join("\n");
  assert.equal(rendered.match(/cach(e|ed|ing)/gi), null);
  // Removing the label must not have removed the honesty it sat next to.
  assert.match(rendered, /SYNTHETIC DEMO ONLY/);
  // The banner no longer advertises the snapshot's plumbing ("local", "no API
  // calls"); the per-answer evidence caveat below still says it is not live.
  assert.doesNotMatch(exports.snapshotDisclaimer, /local snapshot|no API calls/i);
  for (const company of exports.companies) {
    const answer = exports.answerQuestion(company, "briefing");
    assert.equal(answer.match(/SYNTHETIC/g).length, 1);
    assert.match(answer, /not live retrievals/);
  }
});
