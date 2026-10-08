import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import {
  cpSync, existsSync, lstatSync, mkdirSync, readFileSync, readdirSync,
  readlinkSync, renameSync, rmSync, symlinkSync, unlinkSync, writeFileSync,
} from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { deflateSync } from "node:zlib";
import { loadBankConfig, SETUP_GUIDANCE, validateBankConfig } from "./scripts/bank-config.mjs";
import { validatePng } from "./scripts/png-validation.mjs";

const webRoot = path.dirname(fileURLToPath(import.meta.url));
const wrapperPath = path.resolve(webRoot, "..", "..", "..", "setup-bank.ps1");
const CONFIG_LIMIT = 16 * 1024;
const LOGO_LIMIT = 2 * 1024 * 1024;
const windows = process.platform === "win32";
const validConfig = (changes = {}) => ({
  schemaVersion: 1,
  bankName: "Example Bank",
  bankShortName: "Example",
  primaryColor: "#334155",
  accentColor: "#64748b",
  ...changes,
});

function fixture(t) {
  const root = path.join(webRoot, `.bank-config-test-${process.pid}-${randomUUID()}`);
  mkdirSync(root);
  const links = [];
  t.after(() => {
    try {
      for (const link of links.reverse()) {
        try {
          if (lstatSync(link).isSymbolicLink()) unlinkSync(link);
        } catch (error) {
          if (error.code !== "ENOENT") throw error;
        }
      }
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
  const rootWeb = path.join(root, "app", "src", "web");
  mkdirSync(rootWeb, { recursive: true });
  cpSync(path.join(webRoot, "scripts"), path.join(rootWeb, "scripts"), { recursive: true });
  cpSync(wrapperPath, path.join(root, "setup-bank.ps1"));
  const cwd = path.join(root, "caller with spaces");
  mkdirSync(cwd);
  return {
    root, web: rootWeb, cwd, links,
    script: path.join(rootWeb, "scripts", "bank-config.mjs"),
    wrapper: path.join(root, "setup-bank.ps1"),
  };
}

function processResult(executable, args, f, options = {}) {
  const result = spawnSync(executable, args, {
    cwd: f.cwd,
    shell: false,
    windowsHide: true,
    encoding: "utf8",
    timeout: 90_000,
    maxBuffer: 1024 * 1024,
    input: "",
    ...options,
  });
  assert.ifError(result.error);
  assert.equal(result.signal, null, `process terminated: ${result.signal}`);
  assert.equal(typeof result.status, "number");
  return result;
}

function cli(f, args, input = "") {
  return processResult(process.execPath, [f.script, ...args], f, { input });
}

function success(result) {
  assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
}

function failure(result, guidance = false) {
  assert.notEqual(result.status, 0, "invalid input unexpectedly succeeded");
  const output = `${result.stdout}\n${result.stderr}`.trim();
  assert.ok(output.length > 0, "failure must explain the error");
  if (guidance) assert.match(output, /setup-bank\.ps1/i);
  return output;
}

function noPromptFailure(result, guidance = false) {
  const output = failure(result, guidance);
  assert.doesNotMatch(output, /Read-Host|read and prompt functionality is not available|interactive input is not supported/i);
  return output;
}

function snapshot(root) {
  const entries = {};
  function walk(directory, relative = "") {
    for (const name of readdirSync(directory).sort()) {
      const full = path.join(directory, name);
      const key = path.join(relative, name);
      const stat = lstatSync(full);
      if (stat.isSymbolicLink()) {
        entries[key] = { link: readlinkSync(full) };
      } else if (stat.isDirectory()) {
        entries[key] = { directory: true };
        walk(full, key);
      } else {
        entries[key] = { bytes: readFileSync(full).toString("base64") };
      }
    }
  }
  walk(root);
  return entries;
}

function unchanged(f, action) {
  const before = snapshot(f.root);
  try {
    return action();
  } finally {
    assert.deepEqual(snapshot(f.root), before, "failed operation changed fixture files");
  }
}

function discoverConfig(f) {
  const files = Object.keys(snapshot(f.web))
    .filter(name => name.endsWith(".json") && !name.startsWith(`scripts${path.sep}`));
  assert.deepEqual(files, [path.join("public", "brand", "bank.json")],
    "the generated config must use the fixed public/brand/bank.json contract");
  f.configPath = path.join(f.web, "public", "brand", "bank.json");
  f.brand = path.dirname(f.configPath);
  f.logo = path.join(f.brand, "logo.png");
  return f;
}

function seed(f, config = validConfig(), logoPath) {
  success(cli(f, ["--write"], JSON.stringify({ config, ...(logoPath ? { logoPath } : {}) })));
  return discoverConfig(f);
}

function writeConfig(f, value) {
  writeFileSync(f.configPath, JSON.stringify(value), "utf8");
}

function crc32(bytes) {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function chunk(type, data = Buffer.alloc(0)) {
  const tag = Buffer.from(type, "ascii");
  const result = Buffer.alloc(data.length + 12);
  result.writeUInt32BE(data.length, 0);
  tag.copy(result, 4);
  data.copy(result, 8);
  result.writeUInt32BE(crc32(Buffer.concat([tag, data])), data.length + 8);
  return result;
}

const pngSignature = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
function png({
  width = 1, height = 1, bitDepth = 8, colorType = 6,
  compression = 0, filter = 0, interlace = 0,
  pixels = Buffer.from([0, 30, 90, 150, 255]),
  compressed = deflateSync(pixels), beforeData = [], afterData = [],
} = {}) {
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = bitDepth;
  ihdr[9] = colorType;
  ihdr[10] = compression;
  ihdr[11] = filter;
  ihdr[12] = interlace;
  return Buffer.concat([
    pngSignature, chunk("IHDR", ihdr), ...beforeData,
    chunk("IDAT", compressed), ...afterData, chunk("IEND"),
  ]);
}

function sourceLogo(f, bytes = png(), name = "source logo.png") {
  const target = path.join(f.cwd, name);
  writeFileSync(target, bytes);
  return target;
}

function directoryLink(f, target, link) {
  symlinkSync(target, link, windows ? "junction" : "dir");
  f.links.push(link);
}

function fileLink(t, f, target, link) {
  try {
    symlinkSync(target, link, "file");
    f.links.push(link);
    return true;
  } catch (error) {
    if (!["EPERM", "EACCES", "ENOTSUP"].includes(error.code)) throw error;
    t.skip(`file symlink creation is unavailable: ${error.code}`);
    return false;
  }
}

// All text supplied by a test travels as JSON data, never as PowerShell source.
const psLauncher = `
$ErrorActionPreference = 'Stop'
try {
  $request = ConvertFrom-Json -InputObject $env:BANK_CONFIG_TEST_REQUEST
  $parameters = @{}
  foreach ($property in $request.parameters.PSObject.Properties) {
    $parameters[$property.Name] = $property.Value
  }
  & $env:BANK_CONFIG_TEST_WRAPPER @parameters
  if (-not $?) { exit 1 }
} catch {
  [Console]::Error.WriteLine($_.Exception.Message)
  exit 1
}
`;

function powershell(executable, f, parameters) {
  return processResult(executable, [
    "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
    "-Command", psLauncher,
  ], f, {
    env: {
      ...process.env,
      BANK_CONFIG_TEST_WRAPPER: f.wrapper,
      BANK_CONFIG_TEST_REQUEST: JSON.stringify({ parameters }),
    },
  });
}

const psInteractiveLauncher = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
try {
  $request = ConvertFrom-Json -InputObject $env:BANK_CONFIG_TEST_REQUEST
  $global:BankConfigTestAnswers = New-Object System.Collections.Queue
  $global:BankConfigTestPrompts = New-Object 'System.Collections.Generic.List[string]'
  foreach ($answer in $request.answers) {
    $global:BankConfigTestAnswers.Enqueue([string]$answer)
  }
  function global:Read-Host {
    param([string]$Prompt)
    $global:BankConfigTestPrompts.Add($Prompt)
    if ($global:BankConfigTestAnswers.Count -eq 0) {
      throw ('Unexpected extra Read-Host prompt: ' + $Prompt)
    }
    return [string]$global:BankConfigTestAnswers.Dequeue()
  }
  & $env:BANK_CONFIG_TEST_WRAPPER
  if (-not $?) { exit 1 }
  if ($global:BankConfigTestAnswers.Count -ne 0) {
    throw 'Interactive setup returned before consuming every queued answer.'
  }
  $prompts = ConvertTo-Json -InputObject @($global:BankConfigTestPrompts.ToArray()) -Compress
  Write-Output ('BANK_CONFIG_TEST_INTERACTIVE=' + $prompts)
} catch {
  [Console]::Error.WriteLine($_.Exception.Message)
  exit 1
}
`;

function interactivePowershell(executable, f, answers) {
  // Only the host is noninteractive; the wrapper receives no bound parameters.
  return processResult(executable, [
    "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
    "-Command", psInteractiveLauncher,
  ], f, {
    env: {
      ...process.env,
      BANK_CONFIG_TEST_WRAPPER: f.wrapper,
      BANK_CONFIG_TEST_REQUEST: JSON.stringify({ answers }),
    },
  });
}

test("public API is synchronous and supplies setup guidance", () => {
  assert.equal(typeof SETUP_GUIDANCE, "string");
  assert.match(SETUP_GUIDANCE, /setup-bank\.ps1/i);
  const value = validConfig();
  assert.deepEqual(validateBankConfig(value), value);
  assert.equal(validateBankConfig(value)?.then, undefined);
});

test("schema accepts Unicode codepoint limits, punctuation and mixed-case hex", () => {
  for (const value of [
    validConfig({ bankName: "A", bankShortName: "B" }),
    validConfig({ bankName: "A".repeat(120), bankShortName: "B".repeat(32) }),
    validConfig({ bankName: "\u{1f3e6}".repeat(120), bankShortName: "\u{1f3e6}".repeat(32) }),
    validConfig({ bankName: '\u00c9lan \u4e2d\u56fd O\'Brien "Bank" & Co', bankShortName: "\u4e2d\u56fd & \u00c9lan" }),
    validConfig({ primaryColor: "#aBcDeF", accentColor: "#012aF9" }),
    validConfig({ logo: "logo.png" }),
  ]) {
    const expected = structuredClone(value);
    const result = validateBankConfig(value);
    assert.equal(result.bankName, expected.bankName);
    assert.equal(result.bankShortName, expected.bankShortName);
    assert.equal(result.primaryColor.toLowerCase(), expected.primaryColor.toLowerCase());
    assert.equal(result.accentColor.toLowerCase(), expected.accentColor.toLowerCase());
  }
});

for (const [label, value] of [
  ["null", null], ["array", []], ["string", "config"], ["number", 1], ["boolean", true],
  ["undefined", undefined], ["empty object", {}],
  ["unknown key", validConfig({ unexpected: "no" })],
  ["prototype key", JSON.parse(JSON.stringify(validConfig()).replace(/}$/, ',"__proto__":{}}'))],
  ["wrong version", validConfig({ schemaVersion: 2 })],
  ["string version", validConfig({ schemaVersion: "1" })],
  ["null version", validConfig({ schemaVersion: null })],
  ["untrimmed full name", validConfig({ bankName: " Example Bank " })],
  ["untrimmed short name", validConfig({ bankShortName: " Example " })],
  ["Unicode edge whitespace", validConfig({ bankName: "\u00a0Example\u00a0" })],
  ["empty full name", validConfig({ bankName: "" })],
  ["empty short name", validConfig({ bankShortName: "" })],
  ["blank full name", validConfig({ bankName: "   " })],
  ["blank short name", validConfig({ bankShortName: "   " })],
  ["nonstring full name", validConfig({ bankName: 99 })],
  ["nonstring short name", validConfig({ bankShortName: null })],
  ["long full name", validConfig({ bankName: "A".repeat(121) })],
  ["long short name", validConfig({ bankShortName: "A".repeat(33) })],
  ["long Unicode full name", validConfig({ bankName: "\u{1f3e6}".repeat(121) })],
  ["long Unicode short name", validConfig({ bankShortName: "\u{1f3e6}".repeat(33) })],
]) {
  test(`schema rejects ${label}`, () => assert.throws(() => validateBankConfig(value), Error));
}

for (const key of ["schemaVersion", "bankName", "bankShortName", "primaryColor", "accentColor"]) {
  test(`schema requires ${key}`, () => {
    const value = validConfig();
    delete value[key];
    assert.throws(() => validateBankConfig(value), Error);
  });
}

test("names reject embedded controls, bidi formatting and line separators", () => {
  const forbidden = [
    ...Array.from({ length: 32 }, (_, i) => i),
    ...Array.from({ length: 33 }, (_, i) => 0x7f + i),
    0x061c, 0x200e, 0x200f, 0x2028, 0x2029,
    0x202a, 0x202b, 0x202c, 0x202d, 0x202e,
    0x2066, 0x2067, 0x2068, 0x2069,
  ];
  for (const key of ["bankName", "bankShortName"]) {
    for (const codepoint of forbidden) {
      assert.throws(
        () => validateBankConfig(validConfig({ [key]: `A${String.fromCodePoint(codepoint)}B` })),
        Error, `${key} accepted U+${codepoint.toString(16)}`,
      );
    }
  }
});

test("both colors require exactly six hexadecimal digits and a leading hash", () => {
  for (const key of ["primaryColor", "accentColor"]) {
    for (const color of [undefined, null, 123456, "", " ", "#abc", "123456", "#12345678",
      "#12345g", "#123456\n", " #123456", "red", "var(--color)", "#123456;display:none"]) {
      assert.throws(() => validateBankConfig(validConfig({ [key]: color })), Error, `${key}: ${color}`);
    }
  }
});

test("logo references accept only the exact optional generated filename", () => {
  for (const logo of [undefined, null, false, "", "Logo.png", "logo.PNG", "./logo.png",
    "../logo.png", "..\\logo.png", "brand/logo.png", "other.png", "logo.svg",
    "C:\\logo.png", "https://example.invalid/logo.png", "logo.png:stream"]) {
    assert.throws(() => validateBankConfig(validConfig({ logo })), Error, String(logo));
  }
});

test("loader and CLI report missing configuration without creating anything", t => {
  const f = fixture(t);
  unchanged(f, () => {
    assert.throws(() => loadBankConfig(f.web), Error);
    failure(cli(f, ["--check"]), true);
  });
});

test("writer, loader and --check roundtrip without a logo and ignore caller cwd", t => {
  const f = seed(fixture(t));
  assert.deepEqual(loadBankConfig(f.web), validConfig());
  assert.equal(loadBankConfig(f.web)?.then, undefined);
  assert.ok(!existsSync(f.logo));
  const decoy = path.join(f.cwd, "public", "brand");
  mkdirSync(decoy, { recursive: true });
  writeFileSync(path.join(decoy, path.basename(f.configPath)), "{wrong cwd");
  unchanged(f, () => success(cli(f, ["--check"])));
});

for (const [label, contents] of [
  ["malformed JSON", '{"schemaVersion":'],
  ["empty file", ""],
  ["JSON null", "null"],
  ["unknown config key", JSON.stringify(validConfig({ extra: 1 }))],
  ["missing required colors", '{"schemaVersion":1,"bankName":"Bank","bankShortName":"Bank"}'],
  ["nontrimmed name", JSON.stringify(validConfig({ bankName: " Bank " }))],
  ["invalid logo reference", JSON.stringify(validConfig({ logo: "../source.png" }))],
  ["invalid UTF-8", Buffer.concat([Buffer.from(JSON.stringify(validConfig()).slice(0, -1)), Buffer.from([0xff]), Buffer.from("}")])],
  ["one byte above limit", JSON.stringify(validConfig()).padEnd(CONFIG_LIMIT + 1, " ")],
  ["far above limit", " ".repeat(CONFIG_LIMIT * 2)],
]) {
  test(`loader and --check reject ${label} without mutation`, t => {
    const f = seed(fixture(t));
    writeFileSync(f.configPath, contents);
    unchanged(f, () => {
      assert.throws(() => loadBankConfig(f.web), Error);
      failure(cli(f, ["--check"]), true);
    });
  });
}

test("config size limit counts UTF-8 bytes and accepts exactly 16 KiB", t => {
  const config = validConfig({ bankName: "\u4e2d".repeat(120) });
  const f = seed(fixture(t), config);
  const bytes = Buffer.from(JSON.stringify(config));
  writeFileSync(f.configPath, Buffer.concat([bytes, Buffer.alloc(CONFIG_LIMIT - bytes.length, 32)]));
  assert.deepEqual(loadBankConfig(f.web), config);
  success(cli(f, ["--check"]));
  writeFileSync(f.configPath, Buffer.concat([bytes, Buffer.alloc(CONFIG_LIMIT + 1 - bytes.length, 32)]));
  unchanged(f, () => {
    assert.throws(() => loadBankConfig(f.web), Error);
    failure(cli(f, ["--check"]), true);
  });
});

test("unreferenced unrelated brand files are not treated as logos", t => {
  const f = seed(fixture(t));
  writeFileSync(path.join(f.brand, "unrelated.svg"), "<svg>unrelated artwork</svg>");
  writeFileSync(path.join(f.brand, "unrelated.png"), "not a PNG; not configured");
  unchanged(f, () => {
    assert.deepEqual(loadBankConfig(f.web), validConfig());
    success(cli(f, ["--check"]));
  });
});

test("loader rejects a missing referenced logo and a config directory", t => {
  const f = seed(fixture(t));
  writeConfig(f, validConfig({ logo: "logo.png" }));
  unchanged(f, () => {
    assert.throws(() => loadBankConfig(f.web), Error);
    failure(cli(f, ["--check"]), true);
  });
  rmSync(f.configPath);
  mkdirSync(f.configPath);
  unchanged(f, () => {
    assert.throws(() => loadBankConfig(f.web), Error);
    failure(cli(f, ["--check"]), true);
  });
});

const corruptCrc = png();
corruptCrc[29] ^= 1;
const badSignature = png();
badSignature[0] = 0;
const singleEntryPalette = chunk("PLTE", Buffer.from([30, 90, 150]));
const rgbaCompressed = deflateSync(Buffer.from([0, 30, 90, 150, 255]));
const invalidPngs = [
  ["empty PNG", Buffer.alloc(0)],
  ["SVG disguised as PNG", Buffer.from('<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>')],
  ["signature only", pngSignature],
  ["bad signature", badSignature],
  ["bad chunk CRC", corruptCrc],
  ["zero width", png({ width: 0 })],
  ["zero height", png({ height: 0 })],
  ["illegal dimension", png({ width: 0x80000000 })],
  ["illegal bit depth", png({ bitDepth: 3 })],
  ["illegal color type", png({ colorType: 1 })],
  ["illegal compression method", png({ compression: 1 })],
  ["illegal filter method", png({ filter: 1 })],
  ["illegal interlace method", png({ interlace: 2 })],
  ["invalid zlib IDAT with valid CRC", png({ compressed: Buffer.from("not deflate data") })],
  ["truncated deflate stream", png({ compressed: deflateSync(Buffer.from([0, 1, 2, 3, 4])).subarray(0, 5) })],
  ["decoded data too short", png({ pixels: Buffer.from([0, 1]) })],
  ["decoded data too long", png({ pixels: Buffer.from([0, 1, 2, 3, 4, 5]) })],
  ["invalid scanline filter", png({ pixels: Buffer.from([5, 1, 2, 3, 4]) })],
  ["indexed pixel 255 with only one palette entry", png({
    colorType: 3, beforeData: [singleEntryPalette], pixels: Buffer.from([0, 255]),
  }), /nonexistent palette entry/i],
  ["indexed PNG missing PLTE", png({ colorType: 3, pixels: Buffer.from([0, 0]) })],
  ["indexed PLTE after IDAT", png({
    colorType: 3, afterData: [singleEntryPalette], pixels: Buffer.from([0, 0]),
  })],
  ["truecolor PLTE after IDAT", png({ afterData: [singleEntryPalette] })],
  ["PLTE before IHDR", Buffer.concat([pngSignature, singleEntryPalette, png().subarray(8)])],
  ["duplicate PLTE", png({
    colorType: 3, beforeData: [singleEntryPalette, singleEntryPalette], pixels: Buffer.from([0, 0]),
  })],
  ["empty PLTE", png({ colorType: 3, beforeData: [chunk("PLTE")], pixels: Buffer.from([0, 0]) })],
  ["incomplete PLTE entry", png({
    colorType: 3, beforeData: [chunk("PLTE", Buffer.from([30, 90]))], pixels: Buffer.from([0, 0]),
  })],
  ["palette exceeding indexed bit depth", png({
    colorType: 3, bitDepth: 1, beforeData: [chunk("PLTE", Buffer.alloc(9))], pixels: Buffer.from([0, 0]),
  })],
  ["ancillary chunk interspersed between IDAT chunks", png({
    compressed: rgbaCompressed.subarray(0, 3),
    afterData: [chunk("tEXt", Buffer.from("Author\0Example")), chunk("IDAT", rgbaCompressed.subarray(3))],
  })],
  ["trailing byte inside compressed IDAT", png({
    compressed: Buffer.concat([rgbaCompressed, Buffer.from([0])]),
  })],
  ["second compressed stream inside IDAT", png({
    compressed: Buffer.concat([rgbaCompressed, rgbaCompressed]),
  })],
  ["nonletter chunk type with valid CRC", png({ beforeData: [chunk("t1Xt")] })],
  ["lowercase reserved chunk type bit with valid CRC", png({ beforeData: [chunk("texT")] })],
  ["missing IDAT", Buffer.concat([png().subarray(0, 33), chunk("IEND")])],
  ["missing IEND", png().subarray(0, -12)],
  ["truncated chunk", png().subarray(0, -3)],
  ["oversized chunk length", Buffer.concat([pngSignature, Buffer.from([127, 255, 255, 255]), Buffer.from("IHDR")])],
  ["duplicate IHDR", png({ beforeData: [chunk("IHDR", png().subarray(16, 29))] })],
  ["unknown critical chunk", png({ beforeData: [chunk("ABCD")] })],
  ["trailing bytes", Buffer.concat([png(), Buffer.from("unexpected")])],
  ["over 2 MiB", Buffer.concat([png(), Buffer.alloc(LOGO_LIMIT)])],
];

for (const [label, bytes, expectedError = Error] of invalidPngs) {
  test(`loader and writer reject ${label}; failed writes preserve all bytes`, t => {
    assert.throws(() => validatePng(bytes), expectedError);
    const f = fixture(t);
    const original = sourceLogo(f);
    const config = validConfig({ logo: "logo.png" });
    seed(f, config, original);
    writeFileSync(path.join(f.brand, "keep-me.txt"), "unrelated branding");
    const invalidSource = sourceLogo(f, bytes, "invalid.png");
    unchanged(f, () => failure(cli(f, ["--write"], JSON.stringify({
      config: validConfig({ bankName: "Replacement", logo: "logo.png" }),
      logoPath: invalidSource,
    }))));
    writeFileSync(f.logo, bytes);
    unchanged(f, () => {
      assert.throws(() => loadBankConfig(f.web), Error);
      failure(cli(f, ["--check"]), true);
    });
  });
}

const validIndexedPngs = [
  ...[
    [1, [0, 0xbf]], [2, [0, 0xcf]], [4, [0, 0xf0, 0xff]], [8, [0, 255, 0, 255]],
  ].map(([bitDepth, pixels]) => [
    `${bitDepth}-bit indices at palette bounds${bitDepth < 8 ? " with unused padding bits" : ""}`,
    png({
      colorType: 3, bitDepth, width: 3, pixels: Buffer.from(pixels),
      beforeData: [chunk("PLTE", Buffer.alloc(3 * 2 ** bitDepth, 90))],
    }),
  ]),
  // Each filtered fixture reconstructs rows [1, 2, 3] and [3, 2, 1].
  ...[
    [1, [1, 1, 1, 1, 1, 3, 255, 255]],
    [2, [2, 1, 2, 3, 2, 2, 0, 254]],
    [3, [3, 1, 2, 2, 3, 3, 0, 255]],
    [4, [4, 1, 1, 1, 4, 2, 255, 254]],
  ].map(([filter, pixels]) => [
    `filter ${filter} with left and previous-row predictors`,
    png({
      colorType: 3, width: 3, height: 2, pixels: Buffer.from(pixels),
      beforeData: [chunk("PLTE", Buffer.alloc(12, 90))],
    }),
  ]),
  ["1x1 Adam7 with empty later passes", png({
    colorType: 3, interlace: 1, beforeData: [singleEntryPalette], pixels: Buffer.from([0, 0]),
  })],
];

for (const [label, bytes] of validIndexedPngs) {
  test(`indexed PNG accepts ${label}`, t => {
    assert.doesNotThrow(() => validatePng(bytes));
    const f = fixture(t);
    const config = validConfig({ logo: "logo.png" });
    seed(f, config, sourceLogo(f, bytes));
    assert.deepEqual(readFileSync(f.logo), bytes);
    unchanged(f, () => {
      assert.deepEqual(loadBankConfig(f.web), config);
      success(cli(f, ["--check"]));
    });
  });
}

test("valid PNG fixture CRCs, split IDAT and ancillary chunks are accepted", t => {
  assert.equal(crc32(Buffer.from("123456789")), 0xcbf43926);
  const compressed = deflateSync(Buffer.from([0, 30, 90, 150, 255]));
  const bytes = Buffer.concat([
    pngSignature, chunk("IHDR", png().subarray(16, 29)),
    chunk("tEXt", Buffer.from("Author\0Example")),
    chunk("IDAT", compressed.subarray(0, 3)),
    chunk("IDAT", compressed.subarray(3)), chunk("IEND"),
  ]);
  const f = fixture(t);
  const source = sourceLogo(f, bytes);
  seed(f, validConfig({ logo: "logo.png" }), source);
  assert.deepEqual(readFileSync(f.logo), bytes);
  assert.deepEqual(loadBankConfig(f.web), validConfig({ logo: "logo.png" }));
  unchanged(f, () => success(cli(f, ["--check"])));
});

test("PNG exactly 2 MiB is valid; one byte beyond the limit is rejected", t => {
  const base = png();
  function sizedPng(size) {
    const padding = chunk("tEXt", Buffer.concat([
      Buffer.from("Padding\0"), Buffer.alloc(size - base.length - 12 - 8, 65),
    ]));
    return Buffer.concat([base.subarray(0, -12), padding, chunk("IEND")]);
  }
  const f = fixture(t);
  const exact = sizedPng(LOGO_LIMIT);
  assert.equal(exact.length, LOGO_LIMIT);
  const source = sourceLogo(f, exact);
  seed(f, validConfig({ logo: "logo.png" }), source);
  assert.deepEqual(readFileSync(f.logo), exact);
  success(cli(f, ["--check"]));
  const tooLarge = sourceLogo(f, sizedPng(LOGO_LIMIT + 1), "too-large.png");
  unchanged(f, () => failure(cli(f, ["--write"], JSON.stringify({
    config: validConfig({ logo: "logo.png" }), logoPath: tooLarge,
  }))));
  writeFileSync(f.logo, sizedPng(LOGO_LIMIT + 1));
  unchanged(f, () => assert.throws(() => loadBankConfig(f.web), Error));
});

test("writer accepts relative and absolute local PNG sources and safely removes only generated logo", t => {
  const f = fixture(t);
  const source = sourceLogo(f);
  for (const logoPath of [path.basename(source), source]) {
    seed(f, validConfig({ logo: "logo.png" }), logoPath);
    assert.deepEqual(readFileSync(f.logo), readFileSync(source));
    assert.deepEqual(loadBankConfig(f.web), validConfig({ logo: "logo.png" }));
    success(cli(f, ["--check"]));
  }
  const keep = path.join(f.brand, "customer-original.png");
  writeFileSync(keep, "unrelated artwork");
  const keepNested = path.join(f.brand, "other-bank");
  mkdirSync(keepNested);
  writeFileSync(path.join(keepNested, "logo.png"), "another bank's logo");
  const config = validConfig({ bankName: "Updated Bank" });
  success(cli(f, ["--write"], JSON.stringify({ config })));
  assert.deepEqual(loadBankConfig(f.web), config);
  assert.ok(!existsSync(f.logo), "omitting logo must remove the previously generated logo");
  assert.equal(readFileSync(keep, "utf8"), "unrelated artwork");
  assert.equal(readFileSync(path.join(keepNested, "logo.png"), "utf8"), "another bank's logo");
  assert.deepEqual(readFileSync(source), png(), "source logo must not be removed or modified");
});

for (const args of [
  [], ["--unknown"], ["--check", "--write"], ["--write", "--check"],
  ["--check", "--check"], ["--write", "--write"], ["--check", "extra"],
]) {
  test(`CLI rejects unsupported options ${JSON.stringify(args)} without mutation`, t => {
    const f = seed(fixture(t));
    unchanged(f, () => failure(cli(f, args, JSON.stringify({ config: validConfig() }))));
  });
}

for (const [label, input] of [
  ["empty stdin", ""], ["malformed envelope", "{no"], ["null envelope", "null"],
  ["array envelope", "[]"], ["missing config", "{}"],
  ["bare config", JSON.stringify(validConfig())],
  ["invalid config", JSON.stringify({ config: validConfig({ bankName: "" }) })],
  ["missing color", JSON.stringify({ config: { ...validConfig(), primaryColor: undefined } })],
  ["logo without source", JSON.stringify({ config: validConfig({ logo: "logo.png" }) })],
  ["nonstring source", JSON.stringify({ config: validConfig({ logo: "logo.png" }), logoPath: 1 })],
  ["invalid UTF-8 stdin", Buffer.from([0xff, 0xfe, 0x7b, 0x7d])],
]) {
  test(`writer rejects ${label} without changing existing config or logo`, t => {
    const f = fixture(t);
    seed(f, validConfig({ logo: "logo.png" }), sourceLogo(f));
    writeFileSync(path.join(f.brand, "unrelated.txt"), "preserve");
    unchanged(f, () => failure(cli(f, ["--write"], input)));
  });
}

test("invalid writes to a fresh fixture do not create branding or staging files", t => {
  const f = fixture(t);
  unchanged(f, () => failure(cli(f, ["--write"], JSON.stringify({
    config: validConfig({ bankShortName: "" }),
  }))));
});

test("supplying a PNG source requires the config logo reference", t => {
  const f = seed(fixture(t));
  const source = sourceLogo(f);
  unchanged(f, () => failure(cli(f, ["--write"], JSON.stringify({
    config: validConfig(), logoPath: source,
  }))));
});

test("source URLs, UNC/device paths, ADS, traversal and directories are rejected", t => {
  const f = fixture(t);
  seed(f, validConfig({ logo: "logo.png" }), sourceLogo(f));
  const nested = path.join(f.cwd, "nested");
  mkdirSync(nested);
  const paths = [
    "https://example.invalid/logo.png",
    "http://127.0.0.1/logo.png",
    "file:///C:/logo.png",
    "\\\\localhost\\nonexistent-share\\logo.png",
    "\\\\?\\C:\\logo.png",
    "\\\\.\\C:\\logo.png",
    `${path.join(f.cwd, "source logo.png")}:stream`,
    "nested\\..\\source logo.png",
    "nested/../source logo.png",
    path.join(f.cwd, "missing.png"),
    nested,
  ];
  for (const logoPath of paths) {
    unchanged(f, () => failure(cli(f, ["--write"], JSON.stringify({
      config: validConfig({ logo: "logo.png" }), logoPath,
    }))));
  }
});

for (const target of ["public", "brand", "web-ancestor"]) {
  test(`loader and writer reject a junction in ${target} destination ancestry`, t => {
    const f = seed(fixture(t));
    const original = target === "public" ? path.join(f.web, "public")
      : target === "brand" ? f.brand : path.join(f.root, "app");
    const moved = path.join(f.root, `real-${target}`);
    renameSync(original, moved);
    directoryLink(f, moved, original);
    unchanged(f, () => {
      assert.throws(() => loadBankConfig(f.web), Error);
      failure(cli(f, ["--check"]), true);
      failure(cli(f, ["--write"], JSON.stringify({ config: validConfig({ bankName: "Do not write" }) })));
    });
  });
}

test("Windows case-insensitive CLI entrypoints still perform mandatory checks", { skip: !windows }, t => {
  const f = fixture(t);
  const uppercaseScript = f.script.slice(0, -4).toUpperCase() + ".mjs";
  unchanged(f, () => failure(processResult(process.execPath, [uppercaseScript, "--check"], f), true));
  seed(f);
  unchanged(f, () => success(processResult(process.execPath, [uppercaseScript, "--check"], f)));
});

test("writer rejects source junction ancestry without changing its target", t => {
  const f = seed(fixture(t));
  const real = path.join(f.root, "real-source");
  mkdirSync(real);
  writeFileSync(path.join(real, "logo.png"), png());
  const alias = path.join(f.cwd, "source-alias");
  directoryLink(f, real, alias);
  unchanged(f, () => failure(cli(f, ["--write"], JSON.stringify({
    config: validConfig({ logo: "logo.png" }), logoPath: path.join(alias, "logo.png"),
  }))));
});

for (const target of ["config", "logo", "source"]) {
  test(`file symlinks are rejected for ${target} without target mutation`, t => {
    const f = fixture(t);
    const source = sourceLogo(f);
    seed(f, validConfig({ logo: "logo.png" }), source);
    let link;
    let real;
    if (target === "source") {
      real = source;
      link = path.join(f.cwd, "linked-source.png");
    } else {
      link = target === "config" ? f.configPath : f.logo;
      real = path.join(f.root, target === "config" ? "real-config.json" : "real-logo.png");
      renameSync(link, real);
    }
    if (!fileLink(t, f, real, link)) return;
    unchanged(f, () => {
      if (target !== "source") {
        assert.throws(() => loadBankConfig(f.web), Error);
        failure(cli(f, ["--check"]), true);
      }
      failure(cli(f, ["--write"], JSON.stringify({
        config: validConfig({ bankName: "Replacement", logo: "logo.png" }),
        logoPath: target === "source" ? link : source,
      })));
      if (target === "logo") {
        failure(cli(f, ["--write"], JSON.stringify({ config: validConfig() })));
      }
    });
  });
}

for (const executable of ["pwsh.exe", "powershell.exe"]) {
  for (const scenario of [
    {
      label: "reprompts for required name and derives short name",
      bankName: "\u00c9lan O'Brien & Co", bankShortName: "\u00c9lan O'Brien & Co",
      nameRetries: ["", "   "], shortAnswers: [""], derivedShort: true,
    },
    {
      label: "requires explicit short name for a long bank name",
      bankName: "Long Name Capital Markets International Bank", bankShortName: "Markets",
      nameRetries: [], shortAnswers: ["", "   ", "  Markets  "], derivedShort: false,
    },
  ]) {
    test(`${executable}: no-args interactive setup ${scenario.label}`, { skip: !windows }, t => {
      const f = fixture(t);
      const answers = [
        ...scenario.nameRetries, `  ${scenario.bankName}  `, ...scenario.shortAnswers, "", "", "",
      ];
      const result = interactivePowershell(executable, f, answers);
      success(result);
      const report = result.stdout.match(/^BANK_CONFIG_TEST_INTERACTIVE=(.+)\r?$/m);
      assert.ok(report, "wrapper must return to the launcher and report consumed prompts");
      const prompts = JSON.parse(report[1]);
      assert.equal(prompts.length, answers.length, "interactive prompt count changed");
      const expectedPrompts = [
        ...Array(scenario.nameRetries.length + 1).fill(/^Bank name/),
        ...Array(scenario.shortAnswers.length).fill(/^Short bank name/),
        /^Primary color/, /^Accent color/, /^Optional local PNG logo path/,
      ];
      prompts.forEach((prompt, index) => assert.match(prompt, expectedPrompts[index]));
      for (const prompt of prompts.filter(value => value.startsWith("Short bank name"))) {
        assert.equal(prompt.includes(`[${scenario.bankName}]`), scenario.derivedShort);
      }
      discoverConfig(f);
      unchanged(f, () => {
        assert.deepEqual(loadBankConfig(f.web), validConfig({
          bankName: scenario.bankName, bankShortName: scenario.bankShortName,
        }));
        success(cli(f, ["--check"]));
      });
      assert.ok(!existsSync(f.logo), "empty interactive logo answer must omit generated logo");
      assert.deepEqual(readdirSync(f.cwd), [], "interactive setup must not write under caller cwd");
    });
  }

  test(`${executable}: -File creates from script-relative root with defaults and no prompts`, { skip: !windows }, t => {
    const f = fixture(t);
    success(processResult(executable, [
      "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
      "-File", f.wrapper, "-BankName", "Example Bank", "-NonInteractive",
    ], f));
    discoverConfig(f);
    assert.deepEqual(loadBankConfig(f.web), validConfig({ bankShortName: "Example Bank" }));
    unchanged(f, () => {
      success(powershell(executable, f, { Check: true }));
      success(cli(f, ["--check"]));
    });
    assert.deepEqual(readdirSync(f.cwd), [], "wrapper wrote under the caller's directory");
  });

  test(`${executable}: Unicode, apostrophes, quotes, ampersands and code-like names roundtrip`, { skip: !windows }, t => {
    const f = fixture(t);
    const bankName = '\u00c9lan \u4e2d\u56fd O\'Brien "Bank" & Co';
    const bankShortName = "\u00c9lan & \u4e2d\u56fd";
    success(powershell(executable, f, {
      BankName: `  ${bankName}  `, BankShortName: ` ${bankShortName} `,
      PrimaryColor: "#aBcDeF", AccentColor: "#123aBc",
    }));
    discoverConfig(f);
    let config = loadBankConfig(f.web);
    assert.equal(config.bankName, bankName);
    assert.equal(config.bankShortName, bankShortName);
    assert.equal(config.primaryColor.toLowerCase(), "#abcdef");
    assert.equal(config.accentColor.toLowerCase(), "#123abc");
    const inertText = "O'Brien $(throw 'interpolated') & \"Bank\"; ` literal";
    success(powershell(executable, f, {
      BankName: inertText, BankShortName: "Literal", NonInteractive: true,
    }));
    config = loadBankConfig(f.web);
    assert.equal(config.bankName, inertText);
    assert.equal(config.bankShortName, "Literal");
    assert.deepEqual(readdirSync(f.cwd), []);
    success(powershell(executable, f, { Check: true, NonInteractive: true }));
  });

  test(`${executable}: local relative and absolute logos copy, omission removes only generated logo`, { skip: !windows }, t => {
    const f = fixture(t);
    const source = sourceLogo(f);
    for (const logoPath of [path.basename(source), source]) {
      success(powershell(executable, f, {
        BankName: "Example Bank", BankShortName: "Example", LogoPath: logoPath,
      }));
      discoverConfig(f);
      assert.deepEqual(readFileSync(f.logo), png());
      assert.deepEqual(loadBankConfig(f.web), validConfig({ logo: "logo.png" }));
      success(powershell(executable, f, { Check: true }));
    }
    const keep = path.join(f.brand, "do-not-delete.svg");
    writeFileSync(keep, "<svg>unrelated</svg>");
    success(powershell(executable, f, { BankName: "No Logo" }));
    assert.ok(!existsSync(f.logo));
    assert.equal(readFileSync(keep, "utf8"), "<svg>unrelated</svg>");
    assert.deepEqual(readFileSync(source), png());
    assert.equal(loadBankConfig(f.web).logo, undefined);
  });

  test(`${executable}: long names require explicit short names and use Unicode codepoint bounds`, { skip: !windows }, t => {
    const f = seed(fixture(t));
    unchanged(f, () => noPromptFailure(powershell(executable, f, { BankName: "B".repeat(33) })));
    success(powershell(executable, f, { BankName: "B".repeat(120), BankShortName: "B".repeat(32) }));
    assert.equal(loadBankConfig(f.web).bankName.length, 120);
    const unicodeName = "\u{1f3e6}".repeat(32);
    success(powershell(executable, f, { BankName: unicodeName }));
    assert.equal(loadBankConfig(f.web).bankShortName, unicodeName);
  });

  for (const [label, parameters] of [
    ["missing full name", { BankShortName: "Short" }],
    ["color only", { PrimaryColor: "#112233" }],
    ["explicit empty name", { BankName: "" }],
    ["blank name", { BankName: "   " }],
    ["explicit empty short name", { BankName: "Bank", BankShortName: "" }],
    ["explicit blank short name", { BankName: "Bank", BankShortName: "  " }],
    ["explicit empty primary color", { BankName: "Bank", PrimaryColor: "" }],
    ["explicit empty accent color", { BankName: "Bank", AccentColor: "" }],
    ["explicit empty logo path", { BankName: "Bank", LogoPath: "" }],
    ["explicit blank logo path", { BankName: "Bank", LogoPath: "   " }],
    ["invalid primary color", { BankName: "Bank", PrimaryColor: "#xyzxyz" }],
    ["invalid accent color", { BankName: "Bank", AccentColor: "#abc" }],
    ["overlong full name", { BankName: "B".repeat(121), BankShortName: "Bank" }],
    ["overlong short name", { BankName: "Bank", BankShortName: "B".repeat(33) }],
    ["control in name", { BankName: "A\nB" }],
    ["bidi in short name", { BankName: "Bank", BankShortName: "A\u202eB" }],
    ["unknown parameter", { BankName: "Bank", NotAParameter: "value" }],
    ["noninteractive missing names", { NonInteractive: true }],
    ["explicit Check false", { Check: false }],
  ]) {
    test(`${executable}: rejects ${label} without prompting or mutation`, { skip: !windows }, t => {
      const f = fixture(t);
      seed(f, validConfig({ logo: "logo.png" }), sourceLogo(f));
      writeFileSync(path.join(f.brand, "preserve.txt"), "keep");
      unchanged(f, () => noPromptFailure(powershell(executable, f, parameters)));
    });
  }

  test(`${executable}: -Check rejects all explicitly bound creation parameters, even empty`, { skip: !windows }, t => {
    const f = seed(fixture(t));
    for (const [key, value] of [
      ["BankName", "Bank"], ["BankShortName", "Short"],
      ["PrimaryColor", "#123456"], ["AccentColor", "#123456"],
      ["LogoPath", path.join(f.cwd, "not-read.png")],
    ]) {
      for (const boundValue of [value, ""]) {
        unchanged(f, () => noPromptFailure(powershell(executable, f, { Check: true, [key]: boundValue })));
      }
    }
  });

  test(`${executable}: -Check rejects missing or malformed configuration without prompting`, { skip: !windows }, t => {
    const f = fixture(t);
    unchanged(f, () => noPromptFailure(powershell(executable, f, { Check: true }), true));
    seed(f);
    writeFileSync(f.configPath, "{broken");
    unchanged(f, () => noPromptFailure(powershell(executable, f, { Check: true }), true));
  });

  test(`${executable}: no args under a noninteractive host fails boundedly`, { skip: !windows }, t => {
    const f = fixture(t);
    unchanged(f, () => failure(processResult(executable, [
      "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
      "-File", f.wrapper,
    ], f)));
  });

  test(`${executable}: a missing argument value is rejected`, { skip: !windows }, t => {
    const f = seed(fixture(t));
    unchanged(f, () => failure(processResult(executable, [
      "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
      "-File", f.wrapper, "-BankName",
    ], f)));
  });

  test(`${executable}: logo validation errors and source junctions preserve existing branding`, { skip: !windows }, t => {
    const f = fixture(t);
    const source = sourceLogo(f);
    seed(f, validConfig({ logo: "logo.png" }), source);
    const disguised = sourceLogo(f, Buffer.from("<svg/>"), "disguised.png");
    const real = path.join(f.root, "real-logos");
    mkdirSync(real);
    writeFileSync(path.join(real, "logo.png"), png());
    const alias = path.join(f.cwd, "linked-logos");
    directoryLink(f, real, alias);
    for (const logoPath of [
      disguised, path.join(alias, "logo.png"), `${source}:alternate`,
      path.join(f.cwd, "absent.png"), "linked-logos\\..\\source logo.png",
    ]) {
      unchanged(f, () => failure(powershell(executable, f, {
        BankName: "Replacement", BankShortName: "New", LogoPath: logoPath,
      })));
    }
  });

  test(`${executable}: destination junction blocks both setup and check`, { skip: !windows }, t => {
    const f = seed(fixture(t));
    const real = path.join(f.root, "real-brand");
    renameSync(f.brand, real);
    directoryLink(f, real, f.brand);
    unchanged(f, () => {
      failure(powershell(executable, f, { Check: true }));
      failure(powershell(executable, f, { BankName: "Replacement" }));
    });
  });
}
