import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const require = createRequire(import.meta.url);
const read = path => readFileSync(new URL(path, import.meta.url), "utf8");
const compiled = new Map();
function load(path, imports, globals = {}) {
  if (!compiled.has(path)) {
    compiled.set(path, ts.transpileModule(read(path), {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
      },
    }).outputText);
  }
  const exports = {};
  vm.runInNewContext(compiled.get(path), {
    exports,
    require: name => {
      if (Object.hasOwn(imports, name)) return imports[name];
      if (name === "react/jsx-runtime") return require(name);
      assert.fail(`Unexpected dependency: ${name}`);
    },
    ...globals,
  }, { filename: path });
  return exports;
}

const config = Object.freeze({
  schemaVersion: 1,
  bankName: 'North "Partners" $& $1 <Trust>',
  bankShortName: 'North Partners "$&" $1',
  primaryColor: "#334155",
  accentColor: "#64748b",
});

function documentStub() {
  const variables = {};
  let icon;
  const document = {
    title: "",
    documentElement: { style: { setProperty: (name, value) => { variables[name] = value; } } },
    querySelector: () => icon,
    createElement: tag => {
      assert.equal(tag, "link");
      return { remove: () => { icon = undefined; } };
    },
    head: { appendChild: element => { icon = element; } },
  };
  return { document, variables, icon: () => icon };
}

function branding(value = config, dom = documentStub()) {
  return load("./src/brand.ts", { "virtual:bank-config": { default: value } }, { document: dom.document });
}

test("validated config is the sole identity; special characters remain literal", () => {
  const dom = documentStub();
  const ui = branding(config, dom);
  assert.equal(ui.brand, config);
  ui.applyBrand();
  assert.equal(dom.document.title, `${config.bankName} | Capital Markets Client Intelligence`);
  assert.equal(dom.variables["--brand"], config.primaryColor);
  assert.equal(dom.variables["--accent"], config.accentColor);
  assert.equal(ui.logoSrc, undefined);
  assert.equal(dom.icon(), undefined);
  assert.equal(ui.replaceBankPlaceholder("The Bank and the Bank's decision"),
    `${config.bankShortName} and ${config.bankShortName}'s decision`);
  for (const value of [
    "The Bank of Canada", "the Bank of Canada", "The Bank\nof Montreal",
    "Royal Bank of Canada", "BMO Capital Markets", "RBC", "Scotiabank",
    "Gibson Energy Inc.", "the bank", "THE BANK", "The Banker", "Other Bank",
  ]) {
    assert.equal(ui.replaceBankPlaceholder(value), value);
  }
});

test("typed authored traversal changes narrative only, never IDs, URLs, citations or unknown fields", () => {
  const ui = branding();
  const narrative = "The Bank";
  const source = {
    id: narrative, url: "https://example.test/The Bank", text: narrative, title: narrative,
  };
  const story = {
    persona: { name: narrative, title: narrative, org: narrative, goal: narrative,
      objectives: [narrative], points: [narrative], citations: [source] },
    personaByRole: { [narrative]: { goal: narrative, objectives: [narrative], points: [narrative] } },
    chapters: [{
      id: narrative, iq: "work", layout: "iq", title: narrative, kicker: narrative, body: narrative,
      prompt: narrative, points: [narrative], expect: [narrative], assurances: [narrative], note: narrative,
      columns: [{ title: narrative, tag: narrative, items: [{ name: narrative, detail: narrative, url: source.url }] }],
      metrics: [{ label: narrative, value: narrative, sub: narrative, tone: "neutral" }],
      wrong: { head: narrative, lines: [narrative] }, right: { head: narrative, lines: [narrative] },
      layerTable: { headers: [narrative, narrative, narrative, narrative],
        rows: [{ iq: "work", holds: narrative, tells: narrative, cannot: narrative }] },
      pathSteps: [{ constraint: narrative, clears: narrative, owner: narrative, tone: "ok" }],
      plain: { heading: narrative, lead: narrative, punch: narrative,
        cards: [{ icon: narrative, title: narrative, sub: narrative, body: narrative }],
        gauges: [{ label: narrative, sub: narrative, value: narrative, caption: narrative, pct: 20, tone: "ok" }] },
      url: source.url, citations: [source], answer: source,
    }],
    suggestions: [narrative, "The Bank of Canada", "Gibson Energy Inc."], unknown: source,
  };
  const original = JSON.stringify(story);
  const output = ui.brandStory(story);
  const c = output.chapters[0];
  assert.equal(output.persona.org, config.bankName);
  assert.equal(output.persona.name, narrative);
  assert.equal(output.persona.goal, config.bankShortName);
  assert.equal(output.personaByRole[narrative].goal, config.bankShortName);
  for (const value of [
    c.title, c.kicker, c.body, c.prompt, c.points[0], c.expect[0], c.assurances[0], c.note,
    c.columns[0].title, c.columns[0].tag, c.columns[0].items[0].name, c.columns[0].items[0].detail,
    c.metrics[0].label, c.metrics[0].value, c.metrics[0].sub,
    c.wrong.head, c.wrong.lines[0], c.right.head, c.right.lines[0],
    ...c.layerTable.headers, c.layerTable.rows[0].holds, c.layerTable.rows[0].tells, c.layerTable.rows[0].cannot,
    c.pathSteps[0].constraint, c.pathSteps[0].clears, c.pathSteps[0].owner,
    c.plain.heading, c.plain.lead, c.plain.punch,
    c.plain.cards[0].title, c.plain.cards[0].sub, c.plain.cards[0].body,
    c.plain.gauges[0].label, c.plain.gauges[0].sub, c.plain.gauges[0].value, c.plain.gauges[0].caption,
    output.suggestions[0],
  ]) assert.equal(value, config.bankShortName);
  assert.equal(c.id, narrative);
  assert.equal(c.iq, "work");
  assert.equal(c.url, source.url);
  assert.equal(c.columns[0].items[0].url, source.url);
  assert.equal(c.plain.cards[0].icon, narrative);
  assert.equal(c.citations, story.chapters[0].citations);
  assert.equal(c.answer, source);
  assert.equal(output.unknown, source);
  assert.equal(output.suggestions[1], "The Bank of Canada");
  assert.equal(output.suggestions[2], "Gibson Energy Inc.");
  assert.equal(JSON.stringify(story), original);

  const app = { tenantId: narrative, apiScope: narrative, agentName: narrative,
    bank: narrative, disclaimer: narrative, mockMode: true, citations: [source] };
  const changed = ui.brandAppConfig(app);
  assert.equal(changed.bank, config.bankName);
  assert.equal(changed.agentName, config.bankShortName);
  assert.equal(changed.disclaimer, config.bankShortName);
  assert.equal(changed.tenantId, narrative);
  assert.equal(changed.apiScope, narrative);
  assert.equal(changed.citations, app.citations);
});

test("optional story sections and null prompts are supported", () => {
  const story = {
    persona: { name: "Alex", title: "Coverage", org: "The Bank", goal: "the Bank", objectives: [] },
    chapters: [{ id: "meeting", title: "Meeting", kicker: "", layout: "persona", body: "", prompt: null }],
    suggestions: [],
  };
  const output = branding().brandStory(story);
  assert.equal(output.chapters[0].prompt, null);
  assert.equal(output.personaByRole, undefined);
  assert.equal(branding().brandStory({
    ...story, persona: { ...story.persona, org: "Gibson Energy Inc." },
  }).persona.org, "Gibson Energy Inc.");
  assert.equal(branding().brandStory({
    ...story, persona: { ...story.persona, org: "The Bank of Canada" },
  }).persona.org, "The Bank of Canada");
  assert.equal(branding().brandStory({
    ...story, persona: { ...story.persona, org: "The Bank · Capital Markets" },
  }).persona.org, `${config.bankName} · Capital Markets`);
});

test("initials and logo marks are accessible, escaped and strictly local", () => {
  const ui = branding();
  for (const [name, expected] of [
    ["North Partners", "NP"], ["North", "NO"], ["  North   Partners  ", "NP"],
    ["épargne crédit", "ÉC"], ["北方銀行", "北方"], ["A", "A"], ["$&", "$&"],
  ]) assert.equal(ui.bankInitials(name), expected);
  for (const hasLogo of [false, true]) {
    const current = branding({ ...config, ...(hasLogo ? { logo: "logo.png" } : {}) });
    const { BankMark } = load("./src/components/BankMark.tsx", { "../brand": current, react: React });
    for (const className of ["brand-mark", "signin-mark"]) {
      const html = renderToStaticMarkup(React.createElement(BankMark, { className }));
      assert.ok(html.includes("North &quot;Partners&quot; $&amp; $1 &lt;Trust&gt;"));
      assert.doesNotMatch(html, /<Trust>|https?:\/\//);
      if (hasLogo) assert.match(html, /<img[^>]+src="\/brand\/logo.png"[^>]+alt=/);
      else {
        assert.match(html, /role="img" aria-label=/);
        assert.match(html, />NP<\/span>/);
        assert.doesNotMatch(html, /<img/);
      }
    }
  }
  assert.equal(branding({ ...config, logo: "https://example.test/logo.png" }).logoSrc, undefined);
});

test("missing logo falls back to initials and favicon application is idempotent", () => {
  const dom = documentStub();
  const ui = branding({ ...config, logo: "logo.png" }, dom);
  ui.applyBrand();
  const icon = dom.icon();
  assert.equal(icon.href, "/brand/logo.png");
  assert.equal(icon.type, "image/png");
  ui.applyBrand();
  assert.equal(dom.icon(), icon);
  branding(config, dom).applyBrand();
  assert.equal(dom.icon(), undefined);

  let failed = false;
  const { BankMark } = load("./src/components/BankMark.tsx", {
    "../brand": ui,
    react: { useState: () => [failed, value => { failed = value; }] },
  });
  const image = BankMark({ className: "brand-mark" });
  assert.equal(image.type, "img");
  image.props.onError();
  const fallback = BankMark({ className: "brand-mark" });
  assert.equal(fallback.type, "span");
  assert.equal(fallback.props["aria-label"], config.bankName);
  assert.equal(fallback.props.children, "NP");
});

const luminance = hex => {
  const [r, g, b] = hex.match(/[a-f\d]{2}/gi).map(value => {
    const channel = parseInt(value, 16) / 255;
    return channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4;
  });
  return r * .2126 + g * .7152 + b * .0722;
};
const contrast = (a, b) => {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (light + .05) / (dark + .05);
};

test("primary and accent foregrounds stay legible for light, dark and saturated palettes", () => {
  const colors = ["#000000", "#ffffff", "#ffff00", "#ff0000", "#00ff00", "#0000ff", "#777777", "#334155", "#64748b"];
  for (const primaryColor of colors) for (const accentColor of colors) {
    const dom = documentStub();
    branding({ ...config, primaryColor, accentColor }, dom).applyBrand();
    const v = dom.variables;
    for (const [foreground, background] of [
      [v["--brand-fg"], primaryColor], [v["--brand-fg"], v["--brand-hover"]],
      [v["--accent-fg"], accentColor], [v["--brand-ink"], v["--brand-tint"]],
      [v["--brand-deep"], "#ffffff"], [v["--brand-on-dark"], "#17171a"],
      [v["--accent-ink"], "#ffffff"],
    ]) assert.ok(contrast(foreground, background) >= 4.5, `${foreground} on ${background}`);
  }
  const css = read("./src/styles.css");
  assert.match(css, /\.topbar\s*\{[^}]*color: var\(--brand-fg\)/);
  assert.match(css, /\.btn-primary\s*\{[^}]*color: var\(--brand-fg\)/);
  assert.match(css, /\.fabcap\s*\{[^}]*color: var\(--brand-fg\)/);
  assert.match(read("./src/dashboard/dashboard.css"), /--cp-accent-fg: var\(--brand-fg\)/);
});

const appConfig = { tenantId: "", apiScope: "", bank: "The Bank", agentName: "Agent",
  disclaimer: "The Bank demo", mockMode: true };
const appStory = { persona: { name: "Alex", title: "Coverage", org: "The Bank",
  goal: "Help the Bank", objectives: [] }, chapters: [], suggestions: ["Ask the Bank"] };
const walk = node => {
  if (node == null || typeof node !== "object") return [];
  if (Array.isArray(node)) return node.flatMap(walk);
  return [node, ...walk(node.props?.children)];
};

async function appHarness(authEnabled = false) {
  const state = [];
  const effects = [];
  let cursor = 0;
  let mounted = false;
  let handlers;
  let question;
  const pulse = Object.freeze({ text: "The Bank of Canada and the Bank", citations: [{ title: "The Bank" }] });
  const imports = {
    react: {
      useState: initial => {
        const index = cursor++;
        if (!(index in state)) state[index] = typeof initial === "function" ? initial() : initial;
        return [state[index], value => { state[index] = typeof value === "function" ? value(state[index]) : value; }];
      },
      useMemo: fn => fn(), useCallback: fn => fn, useRef: () => ({ current: null }),
      useEffect: fn => { if (!mounted) effects.push(fn); },
    },
    "./brand": branding(),
    "./api": {
      fetchConfig: async () => appConfig, fetchStory: async () => appStory, fetchIQs: async () => [],
      fetchMe: async () => null, fetchWebPulse: async () => pulse,
      streamChat: async (q, _thread, callbacks) => { question = q; handlers = callbacks; },
      runDiagnostics: async () => ({}),
    },
    "./auth": { authEnabled, account: () => null, login: () => {}, logout: () => {} },
    "./components/ChatSplit": { SplitHandle: "SplitHandle", SplitRail: "SplitRail",
      useChatSplit: () => ({ open: true, width: 50, setOpen: () => {} }) },
  };
  for (const name of ["BankMark", "ChatPanel", "FabricCapacityControl", "IQPanel", "StoryPanel"]) {
    imports[`./components/${name}`] = { [name]: name };
  }
  imports["./dashboard/Dashboard"] = { Dashboard: "Dashboard" };
  imports["./scenarios/ScenariosView"] = { ScenariosView: "ScenariosView" };
  const App = load("./src/App.tsx", imports, { AbortController }).default;
  const render = () => { cursor = 0; return walk(App()); };
  render();
  mounted = true;
  effects.forEach(fn => fn());
  await new Promise(resolve => setImmediate(resolve));
  return { render, handlers: () => handlers, question: () => question, pulse };
}

test("Guided, Explore, Dashboard, Scenarios and auth remain; no runtime bank selector", async () => {
  const app = await appHarness();
  let nodes = app.render();
  const buttons = nodes.filter(node => node.type === "button");
  for (const label of ["Guided", "Explore", "Dashboard", "Scenarios"]) {
    const button = buttons.find(node => node.props.children === label);
    assert.ok(button, label);
    button.props.onClick();
    nodes = app.render();
    assert.equal(nodes.find(node => node.type === "button" && node.props.children === label).props["aria-pressed"], true);
  }
  assert.equal(nodes.find(node => node.type === "Dashboard").props.bankName, config.bankName);
  assert.equal(nodes.find(node => node.type === "ScenariosView").props.bankName, config.bankName);
  assert.ok(nodes.some(node => node.type === "BankMark" && node.props.className === "brand-mark"));
  assert.ok(!nodes.some(node => node.type === "select"));
  const signin = (await appHarness(true)).render();
  assert.ok(signin.some(node => node.type === "button" && node.props.children === "Sign in with Microsoft"));
  assert.ok(signin.some(node => node.type === "BankMark" && node.props.className === "signin-mark"));
  assert.ok(!signin.some(node => node.type === "select"));
});

test("arbitrary queries, streamed answers, final answers, citations and web pulse are never rebranded", async () => {
  const app = await appHarness();
  const query = 'Compare BMO, RBC and Scotiabank with The Bank of Canada and the Bank "$&"';
  await app.render().find(node => node.type === "ChatPanel").props.onSend(query);
  assert.equal(app.question(), query);
  const callbacks = app.handlers();
  callbacks.onToken(query);
  let messages = app.render().find(node => node.type === "ChatPanel").props.messages;
  assert.equal(messages[0].content, query);
  assert.equal(messages[1].content, query);
  const citations = [{ text: "The Bank", title: "The Bank of Canada", url: "https://example.test/the-Bank" }];
  callbacks.onMessage(query, citations);
  callbacks.onDone({ threadId: "the Bank" });
  messages = app.render().find(node => node.type === "ChatPanel").props.messages;
  assert.equal(messages[1].content, query);
  assert.equal(messages[1].citations, citations);
  assert.equal(app.pulse.text, "The Bank of Canada and the Bank");
});

test("source contains no bank presets, switches, shipped logos or general-purpose rewriting", () => {
  const files = readdirSync(new URL("./src/", import.meta.url), { recursive: true })
    .filter(path => /\.(tsx?|css|json)$/.test(path));
  for (const path of files) {
    const source = readFileSync(join(fileURLToPath(new URL("./src/", import.meta.url)), path), "utf8");
    assert.doesNotMatch(source, /\b(?:BMO|RBC|Scotiabank|BRANDS|BRAND_ORDER|BrandPicker|initialBrand|rebrand)\b/i, path);
    if (path.endsWith("brand.ts") || path.endsWith("App.tsx")) {
      assert.doesNotMatch(source, /localStorage|URLSearchParams|location\.search/);
    }
  }
  for (const path of [
    "_source-bmo.png", "cm-lockup.png", "cm-logo-white.png", "cm-logo.png", "favicon.png",
    "make_bank_brands.py", "make_brand.py",
    "rbc/_source-rbc.png", "rbc/favicon.png", "rbc/lockup.png", "rbc/mark.png",
    "scotia/_source-scotia.png", "scotia/favicon.png", "scotia/lockup.png", "scotia/mark.png",
  ]) assert.equal(existsSync(new URL(`./public/brand/${path}`, import.meta.url)), false, path);
  assert.doesNotMatch(read("./index.html"), /\/brand\//);
});
