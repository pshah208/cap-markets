import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { build, createServer, resolveConfig } from "vite";

const webRoot = path.dirname(fileURLToPath(import.meta.url));
const read = file => readFileSync(path.join(webRoot, file), "utf8");
const bank = {
  schemaVersion: 1,
  bankName: 'Custom "Partners" & Trust',
  bankShortName: "Custom $&",
  primaryColor: "#ffffff",
  accentColor: "#ffff00",
};

function fixture(t) {
  const root = path.join(webRoot, `.bank-build-test-${randomUUID()}`);
  mkdirSync(root);
  t.after(() => rmSync(root, { recursive: true, force: true }));
  for (const file of ["src", "scripts", "package.json", "tsconfig.json", "vite.config.ts", "index.html"]) {
    cpSync(path.join(webRoot, file), path.join(root, file), { recursive: true });
  }
  const brandRoot = path.join(root, "public", "brand");
  mkdirSync(brandRoot, { recursive: true });
  return { root, config: path.join(brandRoot, "bank.json") };
}

test("source clone: npm build/dev/preview and direct Vite fail with setup guidance", async t => {
  const f = fixture(t);
  for (const invalid of [undefined, "{bad json", JSON.stringify({ ...bank, primaryColor: "red" })]) {
    if (invalid === undefined) rmSync(f.config, { force: true });
    else writeFileSync(f.config, invalid);
    for (const command of ["build", "dev", "preview"]) {
      const result = spawnSync(process.platform === "win32" ? "npm.cmd" : "npm", ["run", command], {
        cwd: f.root, encoding: "utf8", timeout: 30_000,
        shell: process.platform === "win32",
        env: { ...process.env, NO_COLOR: "1" },
      });
      assert.ifError(result.error);
      assert.notEqual(result.status, 0);
      assert.match(result.stdout + result.stderr, /setup-bank\.ps1/);
      assert.equal(existsSync(path.join(f.root, "dist")), false);
      assert.equal(existsSync(path.join(f.root, "tsconfig.tsbuildinfo")), false);
    }
    await assert.rejects(resolveConfig({ root: f.root, logLevel: "silent" }, "serve"), /setup-bank\.ps1/);
  }
});

test("custom no-logo setup produces a working dev server and production build without build-info writes", async t => {
  const f = fixture(t);
  writeFileSync(f.config, JSON.stringify(bank));
  const protectedPath = path.join(webRoot, "tsconfig.tsbuildinfo");
  const original = existsSync(protectedPath) ? readFileSync(protectedPath) : undefined;
  const fixtureInfo = path.join(f.root, "tsconfig.tsbuildinfo");
  const sentinel = Buffer.from("deployer-owned build information\r\n");
  writeFileSync(fixtureInfo, sentinel);
  const checked = spawnSync(process.execPath, [path.join(webRoot, "node_modules", "typescript", "bin", "tsc"), "--noEmit"], {
    cwd: f.root, encoding: "utf8", timeout: 60_000,
  });
  assert.ifError(checked.error);
  assert.equal(checked.status, 0, checked.stdout + checked.stderr);

  const server = await createServer({
    root: f.root, logLevel: "silent", server: { host: "127.0.0.1", port: 0 },
  });
  try {
    await server.listen();
    const port = server.httpServer.address().port;
    const home = await fetch(`http://127.0.0.1:${port}/`);
    assert.equal(home.status, 200);
    assert.match(await home.text(), /Capital Markets Client Intelligence/);
    const module = await server.transformRequest("virtual:bank-config");
    assert.ok(module.code.includes(JSON.stringify(bank.bankName)));
    assert.ok(module.code.includes(JSON.stringify(bank.bankShortName)));
    assert.doesNotMatch(module.code, /logo\.png/);
  } finally {
    await server.close();
  }

  await build({ root: f.root, logLevel: "silent" });
  const dist = path.join(f.root, "dist");
  assert.deepEqual(JSON.parse(readFileSync(path.join(dist, "brand", "bank.json"), "utf8")), bank);
  assert.equal(existsSync(path.join(dist, "brand", "logo.png")), false);
  const assets = readdirSync(path.join(dist, "assets")).filter(file => file.endsWith(".js"))
    .map(file => readFileSync(path.join(dist, "assets", file), "utf8")).join("\n");
  assert.ok(assets.includes(bank.bankName), "custom name is baked into the bundle");
  assert.ok(assets.includes(bank.bankShortName), "replacement syntax remains literal");
  assert.doesNotMatch(assets, /\b(?:BMO|RBC|Scotiabank)\b/);
  assert.deepEqual(readFileSync(fixtureInfo), sentinel);
  if (original === undefined) assert.equal(existsSync(protectedPath), false);
  else assert.deepEqual(readFileSync(protectedPath), original);
});

test("Docker gates installation and build on the same validator and includes local branding", () => {
  const docker = read("Dockerfile");
  const check = docker.indexOf("RUN node scripts/bank-config.mjs --check");
  assert.ok(check > docker.indexOf("COPY . ."));
  assert.ok(check < docker.indexOf("RUN npm ci"));
  assert.ok(check < docker.indexOf("RUN npm run build"));
  const ignored = read(".dockerignore").split(/\r?\n/).filter(line => line && !line.startsWith("#"));
  assert.ok(!ignored.some(line => /^(?:public|brand|.*bank\.json)/.test(line)));
  assert.match(read(".gitignore"), /^\/public\/brand\/$/m);
  const pkg = JSON.parse(read("package.json"));
  assert.equal(pkg.scripts.build, "tsc --noEmit && vite build");
});
