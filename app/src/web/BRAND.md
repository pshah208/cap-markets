# Deployment-local bank branding

Each deployment represents **one bank, chosen by its deployer**. There are no
shipped bank names, presets, logos, browser overrides or runtime bank selector.
Bank setup is mandatory before development, building or deployment.

## Setup

From the standalone repository root, with Node.js 22+ and PowerShell 7 available:

```powershell
# Interactive: name, short name, colors and optional local PNG.
.\setup-bank.ps1

# Noninteractive: replace these illustrative names with your deployment's name.
.\setup-bank.ps1 -NonInteractive -BankName 'Your Bank Capital Markets' -BankShortName 'Your Bank' -PrimaryColor '#334155' -AccentColor '#64748b'

# Optional user-supplied artwork; no download or remote URL is supported.
.\setup-bank.ps1 -BankName 'Your Bank Capital Markets' -BankShortName 'Your Bank' -LogoPath 'C:\branding\logo.png'

# Read-only, noninteractive, local validation; no cloud access or npm install.
.\setup-bank.ps1 -Check
```

Any parameterized setup is noninteractive. `-BankName` is required; there is no
default name. When omitted, the short name is the full name if it fits within
32 Unicode code points; otherwise `-BankShortName` is required. Colors default
to neutral `#334155` and `#64748b`. Omit `-LogoPath` for a textual initials mark.
`-Check` cannot be combined with creation options and exits nonzero on failure.
Paths to supplied artwork are relative to the caller's working directory or
absolute local filesystem paths. Do not use `..`, URLs, UNC/mapped network
drives, symlinks, junctions, device paths or alternate data streams.

## Shared configuration contract

Setup writes UTF-8 JSON to **`app\src\web\public\brand\bank.json`**, and copies
optional artwork to **`app\src\web\public\brand\logo.png`**. Both are
deployment-local, gitignored by the web subtree, and must not be committed.
The schema is closed: unknown fields are rejected.

| Field | Type and validation |
|---|---|
| `schemaVersion` | Required number, exactly `1` |
| `bankName` | Required trimmed string, 1–120 Unicode code points |
| `bankShortName` | Required trimmed string, 1–32 Unicode code points |
| `primaryColor` | Required string, exactly `#RRGGBB` (hex, case-insensitive) |
| `accentColor` | Required string, exactly `#RRGGBB` (hex, case-insensitive) |
| `logo` | Optional string, exactly `"logo.png"`; omit rather than use `null` |

Names may contain Unicode, quotes, apostrophes and ampersands. Control/format
characters, line/paragraph separators and unpaired surrogates are rejected.
JSON is serialized rather than interpolated. The config is limited to 16 KiB.
Artwork must be a structurally valid PNG, no larger than 2 MiB and 4096 × 4096
pixels, with checked chunks, CRCs and decoded scanlines. SVG and other formats
are not accepted, including files renamed to `.png`. Invalid input is rejected
before existing configuration is replaced. Re-running without a logo removes
the previously configured generated logo. Setup never fetches remote content.

```json
{
  "schemaVersion": 1,
  "bankName": "Your Bank Capital Markets",
  "bankShortName": "Your Bank",
  "primaryColor": "#334155",
  "accentColor": "#64748b"
}
```

This example is documentation only, not a shipped configuration or a default.
The configuration and logo are publicly served assets: never put secrets in
them. Custom names and colors are baked into the frontend bundle; after a
change, restart the development server or rebuild and redeploy the image.

## Validation and build integration

`scripts\bank-config.mjs` is the single schema/file validator used by setup,
`-Check`, npm lifecycle hooks, Vite and Docker. It exports synchronous
`validateBankConfig(value)` and `loadBankConfig(webRoot?)`, returning the
validated object or throwing an error. `loadBankConfig` also checks local
file paths and PNG contents. It requires only Node's built-in modules (and
built-in Windows PowerShell for reparse-point checks on Windows).

From this web directory:

```powershell
node scripts\bank-config.mjs --check
npm ci
npm test
npm run build
npm run dev
```

Build/dev/preview fail with setup guidance when config is missing or invalid.
Direct Vite startup is also guarded. `tsc --noEmit` avoids writing the tracked
`tsconfig.tsbuildinfo` artifact. The Docker build validates before `npm ci`;
its context must include this directory and the local `public\brand` files.
Do not exclude those local files from Docker context just because Git ignores
them. A clean source checkout intentionally fails validation until configured.

**Deployment entrypoint contract (outside this subtree):** invoke
`& (Join-Path $PSScriptRoot 'setup-bank.ps1') -Check` before cloud, build or push
operations and stop on nonzero `$LASTEXITCODE`. Do not choose a name silently.
Linux build pipelines can call the equivalent Node `--check` command; use
PowerShell for setup. Supply local artifacts to the web Docker build context.

## UI and content boundaries

The validated identity arrives through Vite's `virtual:bank-config` module.
`src\brand.ts` sets colors, legible foreground/tint variants, document title and
the optional local PNG favicon. `BankMark` renders the local PNG or accessible
text initials; logo load failure also falls back to initials. All existing
Guided, Explore, Dashboard and Scenarios views remain.

Backend/data authors should use **`the Bank` / `The Bank`** in authored story and
configuration display copy and **`bank_`** field names (for example
`bank_current_hold_m`). The frontend substitutes those narrative placeholders
with `bankShortName`; the app bank label uses `bankName`, and a placeholder
persona organization uses `bankName`. Known external names such as
`The Bank of Canada` are left alone. Identifiers, URLs, citation objects and
unknown fields are not traversed. No replacement is applied to arbitrary
query responses, chat streams, live Web IQ content or citations.

The demo's external issuers remain real public companies to support public
news grounding. Internal exposures, covenants, policies and correspondence are
synthetic, not records provided by the deployer's bank.
