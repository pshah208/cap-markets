import {
  closeSync, constants, existsSync, fstatSync, fsyncSync, lstatSync, mkdirSync,
  openSync, readSync, realpathSync, renameSync, unlinkSync, writeFileSync,
} from "node:fs";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { validatePng } from "./png-validation.mjs";

export const SETUP_GUIDANCE = "Run setup-bank.ps1 from capital-markets-client-intelligence "
  + "(interactively), or supply -BankName and optionally -BankShortName, "
  + "-PrimaryColor, -AccentColor and -LogoPath. Use -Check to validate local setup.";

const DEFAULT_WEB_ROOT = fileURLToPath(new URL("../", import.meta.url));
const MAX_CONFIG_BYTES = 16 * 1024;
const MAX_LOGO_BYTES = 2 * 1024 * 1024;
const MAX_INPUT_BYTES = 32 * 1024;
const REQUIRED_KEYS = ["schemaVersion", "bankName", "bankShortName", "primaryColor", "accentColor"];
const ALLOWED_KEYS = new Set([...REQUIRED_KEYS, "logo"]);
const UNSAFE_NAME = /[\p{Cc}\p{Cf}\p{Cs}\p{Zl}\p{Zp}]/u;

function objectOnly(value, label) {
  if (value === null || typeof value !== "object" || Array.isArray(value)
      || ![Object.prototype, null].includes(Object.getPrototypeOf(value))) {
    throw new Error(`${label} must be a JSON object.`);
  }
}

export function validateBankConfig(value) {
  objectOnly(value, "Bank configuration");
  for (const key of Reflect.ownKeys(value)) {
    if (!ALLOWED_KEYS.has(key)) throw new Error(`Unknown bank configuration key: ${String(key)}.`);
  }
  for (const key of REQUIRED_KEYS) {
    if (!Object.hasOwn(value, key)) throw new Error(`Bank configuration requires ${key}.`);
  }
  if (value.schemaVersion !== 1) throw new Error("schemaVersion must be 1.");
  for (const [key, limit] of [["bankName", 120], ["bankShortName", 32]]) {
    const name = value[key];
    if (typeof name !== "string" || name !== name.trim() || !name.length
        || Array.from(name).length > limit || UNSAFE_NAME.test(name)) {
      throw new Error(`${key} must contain 1..${limit} trimmed characters without control characters.`);
    }
  }
  for (const key of ["primaryColor", "accentColor"]) {
    if (typeof value[key] !== "string" || !/^#[0-9a-fA-F]{6}$/.test(value[key])) {
      throw new Error(`${key} must be a six-digit hex color (#RRGGBB).`);
    }
  }
  if (Object.hasOwn(value, "logo") && value.logo !== "logo.png") {
    throw new Error('logo, when present, must be exactly "logo.png".');
  }
  return { ...value };
}

function localPath(value, label) {
  if (typeof value !== "string" || !value || /[\p{Cc}\p{Cf}]/u.test(value)) {
    throw new Error(`${label} must be a nonempty safe local path.`);
  }
  if (/^[\\/]{2}/.test(value) || (/^[a-zA-Z][\w+.-]*:/.test(value) && !/^[a-zA-Z]:[\\/]/.test(value))) {
    throw new Error(`${label} must be local; URLs, network paths and device paths are not allowed.`);
  }
  const withoutDrive = value.replace(/^[a-zA-Z]:[\\/]/, "");
  if (withoutDrive.includes(":")) throw new Error(`${label} must not use a URI or alternate data stream.`);
  for (const component of withoutDrive.split(/[\\/]/)) {
    if (component === ".." || (component !== "." && /[. ]$/.test(component))) {
      throw new Error(`${label} must not contain traversal or ambiguous path components.`);
    }
    if (/^(?:con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\.|$)/i.test(component)) {
      throw new Error(`${label} must not use a device name.`);
    }
  }
  return path.resolve(value);
}

function pathAncestors(absolute) {
  const root = path.parse(absolute).root;
  let current = root;
  return [root, ...absolute.slice(root.length).split(path.sep).filter(Boolean)
    .map(component => (current = path.join(current, component)))];
}

function rejectWindowsReparsePoints(filenames) {
  if (process.platform !== "win32") return;
  // Node identifies symlinks/junctions, but not every Windows reparse tag.
  // Query attributes from root to leaf before reading, without traversing a reparse point.
  const script = `
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
try {
    $request = ConvertFrom-Json -InputObject ([Console]::In.ReadToEnd())
    $seen = @{}
    foreach ($chain in $request.chains) {
        $drive = New-Object System.IO.DriveInfo([System.IO.Path]::GetPathRoot($chain[0]))
        if ($drive.DriveType -eq [System.IO.DriveType]::Network) {
            throw 'Mapped network drives are not allowed.'
        }
        foreach ($name in $chain) {
            if ($seen.ContainsKey($name)) { continue }
            try {
                $attributes = [System.IO.File]::GetAttributes($name)
            } catch [System.IO.FileNotFoundException] {
                break
            } catch [System.IO.DirectoryNotFoundException] {
                break
            }
            if (($attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'Symlink, junction or Windows reparse point is not allowed.'
            }
            $seen[$name] = $true
        }
    }
    exit 0
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}`;
  if (!process.env.SystemRoot) throw new Error("Cannot verify local Windows reparse-point safety: SystemRoot is missing.");
  const executable = path.join(process.env.SystemRoot, "System32", "WindowsPowerShell", "v1.0", "powershell.exe");
  const result = spawnSync(executable, [
    "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", Buffer.from(script, "utf16le").toString("base64"),
  ], {
    input: JSON.stringify({ chains: filenames.map(filename => pathAncestors(localPath(filename, "File path"))) }),
    encoding: "utf8", windowsHide: true, timeout: 60_000, maxBuffer: 64 * 1024,
  });
  if (result.error || result.status !== 0) {
    throw new Error(`Cannot verify local Windows path safety: ${result.error?.message || result.stderr.trim() || "attribute check failed"}`);
  }
}

function safeStat(filename, { missing = false, directory = false } = {}) {
  const absolute = localPath(filename, "File path");
  const names = pathAncestors(absolute);
  let result;
  for (let index = 0; index < names.length; index++) {
    try {
      result = lstatSync(names[index]);
    } catch (error) {
      if (error.code === "ENOENT" && missing) return null;
      throw error;
    }
    if (result.isSymbolicLink()) throw new Error(`Symlink or reparse/junction path is not allowed: ${names[index]}`);
    if (index < names.length - 1 || directory) {
      if (!result.isDirectory()) throw new Error(`Expected a regular directory: ${names[index]}`);
    } else if (!result.isFile()) {
      throw new Error(`Expected a regular file: ${names[index]}`);
    }
  }
  return result;
}

function readLocalFile(filename, maxBytes) {
  const before = safeStat(filename);
  if (before.size > maxBytes) throw new Error(`File is too large (maximum ${maxBytes} bytes): ${filename}`);
  const fd = openSync(filename, constants.O_RDONLY | (constants.O_NOFOLLOW ?? 0));
  try {
    const opened = fstatSync(fd);
    if (!opened.isFile() || opened.dev !== before.dev || opened.ino !== before.ino) {
      throw new Error(`File changed or is not a regular local file: ${filename}`);
    }
    // Read one extra byte to detect a file growing after the initial size check.
    const buffer = Buffer.alloc(maxBytes + 1);
    let length = 0;
    while (length < buffer.length) {
      const count = readSync(fd, buffer, length, buffer.length - length, null);
      if (!count) break;
      length += count;
    }
    if (length > maxBytes) throw new Error(`File is too large (maximum ${maxBytes} bytes): ${filename}`);
    safeStat(filename);
    return buffer.subarray(0, length);
  } finally {
    closeSync(fd);
  }
}

function parseJson(bytes, label) {
  let text;
  try {
    text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    return JSON.parse(text);
  } catch {
    throw new Error(`${label} must contain valid UTF-8 JSON.`);
  }
}

export function loadBankConfig(webRoot = DEFAULT_WEB_ROOT) {
  try {
    const root = localPath(webRoot, "Web root");
    const configPath = path.join(root, "public", "brand", "bank.json");
    rejectWindowsReparsePoints([configPath, path.join(root, "public", "brand", "logo.png")]);
    const config = validateBankConfig(parseJson(readLocalFile(configPath, MAX_CONFIG_BYTES), "bank.json"));
    if (config.logo) {
      validatePng(readLocalFile(path.join(root, "public", "brand", "logo.png"), MAX_LOGO_BYTES));
    }
    return config;
  } catch (error) {
    throw new Error(`Bank setup is missing or invalid: ${error.message}\n${SETUP_GUIDANCE}`, { cause: error });
  }
}

function ensureDirectory(directory) {
  if (safeStat(directory, { missing: true, directory: true })) return;
  ensureDirectory(path.dirname(directory));
  mkdirSync(directory);
  safeStat(directory, { directory: true });
}

function stageFile(directory, bytes) {
  safeStat(directory, { directory: true });
  const filename = path.join(directory, `.bank-setup-${randomUUID()}.stage`);
  const fd = openSync(filename, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL, 0o600);
  try {
    writeFileSync(fd, bytes);
    fsyncSync(fd);
  } catch (error) {
    closeSync(fd);
    unlinkSync(filename);
    throw error;
  }
  closeSync(fd);
  return filename;
}

function writeBankConfig(input) {
  objectOnly(input, "Setup input");
  for (const key of Object.keys(input)) {
    if (key !== "config" && key !== "logoPath") throw new Error(`Unknown setup input key: ${key}.`);
  }
  const config = validateBankConfig(input.config);
  const hasSource = Object.hasOwn(input, "logoPath");
  if (Boolean(config.logo) !== hasSource) {
    throw new Error('Supply a local PNG logoPath exactly when config.logo is "logo.png".');
  }
  const directory = path.join(DEFAULT_WEB_ROOT, "public", "brand");
  const configPath = path.join(directory, "bank.json");
  const logoPath = path.join(directory, "logo.png");
  let source;
  if (hasSource) {
    source = localPath(input.logoPath, "LogoPath");
    if (path.extname(source).toLowerCase() !== ".png") throw new Error("LogoPath must name a local .png file.");
  }
  rejectWindowsReparsePoints([configPath, logoPath, ...(hasSource ? [source] : [])]);
  let logo;
  if (hasSource) {
    logo = readLocalFile(source, MAX_LOGO_BYTES);
    validatePng(logo);
  }
  const bytes = Buffer.from(`${JSON.stringify(config, null, 2)}\n`, "utf8");
  if (bytes.length > MAX_CONFIG_BYTES) throw new Error("bank.json exceeds the maximum configuration size.");
  safeStat(directory, { missing: true, directory: true });
  safeStat(configPath, { missing: true });
  safeStat(logoPath, { missing: true });

  // Only a previous valid configuration can establish ownership of logo.png.
  let ownedLogo = false;
  if (!logo && existsSync(configPath)) {
    try {
      ownedLogo = validateBankConfig(parseJson(readLocalFile(configPath, MAX_CONFIG_BYTES), "bank.json")).logo === "logo.png";
    } catch {
      ownedLogo = false;
    }
  }
  const oldLogo = safeStat(logoPath, { missing: true })
    ? readLocalFile(logoPath, MAX_LOGO_BYTES) : null;
  ensureDirectory(directory);
  const staged = new Set();
  let replacedLogo = false;
  let committed = false;
  try {
    const configStage = stageFile(directory, bytes);
    staged.add(configStage);
    if (logo) {
      const logoStage = stageFile(directory, logo);
      staged.add(logoStage);
      safeStat(logoPath, { missing: true });
      renameSync(logoStage, logoPath);
      staged.delete(logoStage);
      replacedLogo = true;
    }
    safeStat(configPath, { missing: true });
    renameSync(configStage, configPath);
    staged.delete(configStage);
    committed = true;
    if (!logo && ownedLogo && oldLogo) {
      safeStat(logoPath);
      unlinkSync(logoPath);
    }
  } catch (error) {
    if (replacedLogo && !committed) {
      safeStat(logoPath);
      if (oldLogo) {
        const restore = stageFile(directory, oldLogo);
        staged.add(restore);
        renameSync(restore, logoPath);
        staged.delete(restore);
      } else {
        unlinkSync(logoPath);
      }
    }
    throw error;
  } finally {
    for (const filename of staged) {
      safeStat(filename);
      unlinkSync(filename);
    }
  }
  return validateBankConfig(parseJson(readLocalFile(configPath, MAX_CONFIG_BYTES), "bank.json"));
}

async function readInput() {
  const chunks = [];
  let size = 0;
  for await (const chunk of process.stdin) {
    size += chunk.length;
    if (size > MAX_INPUT_BYTES) throw new Error("Setup input exceeds 32 KiB.");
    chunks.push(chunk);
  }
  return parseJson(Buffer.concat(chunks), "Setup input");
}

async function main() {
  try {
    const args = process.argv.slice(2);
    if (args.length !== 1 || !["--check", "--write"].includes(args[0])) {
      throw new Error("Usage: node scripts/bank-config.mjs --check (or --write with JSON on stdin).");
    }
    safeStat(localPath(process.argv[1], "Validator script"));
    if (args[0] === "--check") {
      loadBankConfig();
      console.log("Bank setup is valid.");
    } else {
      writeBankConfig(await readInput());
      console.log("Bank setup saved and validated.");
    }
  } catch (error) {
    console.error(error.message);
    if (!error.message.includes(SETUP_GUIDANCE)) console.error(SETUP_GUIDANCE);
    process.exitCode = 1;
  }
}

function isEntrypoint() {
  if (!process.argv[1]) return false;
  try {
    const entry = realpathSync(process.argv[1]);
    const modulePath = realpathSync(fileURLToPath(import.meta.url));
    return process.platform === "win32"
      ? entry.toLowerCase() === modulePath.toLowerCase() : entry === modulePath;
  } catch {
    return false;
  }
}

if (isEntrypoint()) {
  await main();
}
