/**
 * Minimal, dependency-free markdown renderer.
 *
 * Deliberately hand-rolled rather than pulled from a library, for one reason:
 * the Foundry playground corrupts numbers by splicing citation markers in by
 * character offset — `92.9%` renders as `[14]2.9%`, `CP-005` as `CP-[12]0[12]`.
 * Here the answer text and its citations are kept strictly separate: text is
 * rendered as-is, citations are listed underneath. Numbers cannot be mangled
 * because nothing is ever substituted into the string.
 *
 * That rule survives the visual upgrade. Tables become sortable and chartable
 * and figures get pulled into KPI tiles, but every string printed to screen is
 * still the agent's original token — parsed values drive geometry and ordering
 * only, never the label.
 *
 * Parsing is two-pass: source is scanned into a block list first, then each
 * block renders itself. The single-pass version could not support constructs
 * that need lookahead (a table's caption is the paragraph above it) or nesting.
 */

import { DataTable, parseNumber, type Align, type TableModel } from "./DataTable";
import type { Citation } from "../types";

/* ------------------------------------------------------------- inline --- */

/** Bold, italic, code and links. Order matters: links are matched first. */
function inline(text: string, keyPrefix: string): (JSX.Element | string)[] {
  const parts = text.split(
    /(\[[^\]]+\]\([^)]+\)|\*\*[^*]+\*\*|__[^_]+__|\*[^*\n]+\*|`[^`]+`)/g,
  );
  return parts.filter(Boolean).map((part, i) => {
    const key = `${keyPrefix}-${i}`;

    const link = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
    if (link) {
      return (
        <a key={key} href={link[2]} target="_blank" rel="noreferrer">
          {link[1]}
        </a>
      );
    }
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4)
      return <strong key={key}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("__") && part.endsWith("__") && part.length > 4)
      return <strong key={key}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2)
      return <em key={key}>{part.slice(1, -1)}</em>;
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2)
      return <code key={key}>{part.slice(1, -1)}</code>;
    return part;
  });
}

function splitRow(row: string): string[] {
  return row
    .replace(/^\s*\|/, "")
    .replace(/\|\s*$/, "")
    .split("|")
    .map((c) => c.trim());
}

function alignFrom(sep: string): Align[] {
  return splitRow(sep).map((c) => {
    const left = c.startsWith(":");
    const right = c.endsWith(":");
    if (left && right) return "center";
    if (right) return "right";
    return "left";
  });
}

const isTableSep = (l: string | undefined) =>
  Boolean(l && /^\s*\|?[\s:|-]+\|[\s:|-]*$/.test(l) && l.includes("-"));

/* -------------------------------------------------------------- blocks --- */

type Block =
  | { kind: "heading"; level: number; text: string }
  | { kind: "para"; text: string }
  | { kind: "list"; ordered: boolean; items: { text: string; depth: number }[] }
  | { kind: "table"; model: TableModel }
  | { kind: "quote"; text: string; tone: string }
  | { kind: "code"; text: string }
  | { kind: "rule" };

const BULLET = /^(\s*)[-*•]\s+(.*)$/;
const NUMBERED = /^(\s*)\d+[.)]\s+(.*)$/;
/** A bare `**Label:** value` line — a figure stated without a bullet marker. */
const DEFN = /^\s*\*\*[^*]+\*\*\s*[:—–-]?\s*\S/;

function parseBlocks(src: string): Block[] {
  const lines = src.split("\n");
  const out: Block[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (!line.trim()) { i += 1; continue; }

    /* fenced code */
    if (/^\s*```/.test(line)) {
      const body: string[] = [];
      i += 1;
      while (i < lines.length && !/^\s*```/.test(lines[i])) {
        body.push(lines[i]);
        i += 1;
      }
      i += 1;
      out.push({ kind: "code", text: body.join("\n") });
      continue;
    }

    /* horizontal rule */
    if (/^\s*([-*_])\s*\1\s*\1[\s\-*_]*$/.test(line)) {
      out.push({ kind: "rule" });
      i += 1;
      continue;
    }

    /* table — header row followed by a separator row */
    if (line.includes("|") && isTableSep(lines[i + 1])) {
      const header = splitRow(line);
      const align = alignFrom(lines[i + 1]);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) {
        rows.push(splitRow(lines[i]));
        i += 1;
      }
      // The paragraph directly above a table is its caption; consume it so the
      // same sentence is not printed twice.
      let caption: string | undefined;
      const prev = out[out.length - 1];
      if (prev?.kind === "para" && prev.text.length < 120 && prev.text.endsWith(":")) {
        caption = prev.text.replace(/:$/, "");
        out.pop();
      }
      out.push({ kind: "table", model: { header, rows, align, caption } });
      continue;
    }

    /* heading */
    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      out.push({ kind: "heading", level: heading[1].length, text: heading[2] });
      i += 1;
      continue;
    }

    /* blockquote → callout */
    if (/^\s*>\s?/.test(line)) {
      const body: string[] = [];
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
        body.push(lines[i].replace(/^\s*>\s?/, ""));
        i += 1;
      }
      const text = body.join(" ").trim();
      // Tone is inferred from the language the agent actually uses on this book:
      // a restriction or a breach is a warning, a policy citation is a note.
      const tone =
        /warn|caution|risk|breach|exceed|restrict|wall-cross|amber|prohibit|may not/i.test(text)
          ? "warn"
          : /note|remember|policy|approval|committee|CP-\d/i.test(text)
            ? "info"
            : "plain";
      out.push({ kind: "quote", text, tone });
      continue;
    }

    /* lists — bullets and numbers, with indent depth preserved */
    if (BULLET.test(line) || NUMBERED.test(line)) {
      const ordered = !BULLET.test(line);
      const items: { text: string; depth: number }[] = [];
      while (i < lines.length) {
        const m = lines[i].match(BULLET) ?? lines[i].match(NUMBERED);
        if (!m) {
          // A wrapped continuation line belongs to the previous item.
          if (items.length && lines[i].trim() && /^\s{2,}\S/.test(lines[i])) {
            items[items.length - 1].text += ` ${lines[i].trim()}`;
            i += 1;
            continue;
          }
          break;
        }
        items.push({
          text: m[2],
          depth: Math.min(2, Math.floor(m[1].replace(/\t/g, "  ").length / 2)),
        });
        i += 1;
      }
      out.push({ kind: "list", ordered, items });
      continue;
    }

    /*
     * Definition run — three or more consecutive `**Label:** value` lines with
     * no bullet marker. The model emits headline figures this way about half the
     * time (using two trailing spaces as a hard break) and the other half as
     * bullets. Collapsing these into one paragraph would run every figure
     * together, so they are captured as a list and become KPI tiles downstream.
     */
    if (DEFN.test(line) && DEFN.test(lines[i + 1] ?? "") && DEFN.test(lines[i + 2] ?? "")) {
      const items: { text: string; depth: number }[] = [];
      while (i < lines.length && DEFN.test(lines[i])) {
        items.push({ text: lines[i].trim(), depth: 0 });
        i += 1;
      }
      out.push({ kind: "list", ordered: false, items });
      continue;
    }

    /* paragraph */
    const para: string[] = [];
    while (
      i < lines.length && lines[i].trim() &&
      !lines[i].includes("|") &&
      !/^\s*(>|#{1,4}\s|```)/.test(lines[i]) &&
      !BULLET.test(lines[i]) && !NUMBERED.test(lines[i])
    ) {
      para.push(lines[i].trim());
      i += 1;
    }
    if (para.length) out.push({ kind: "para", text: para.join(" ") });
    else i += 1;
  }

  return out;
}

/* ----------------------------------------------------------- KPI tiles --- */

interface Kpi { label: string; value: string; tone?: string; }

/**
 * Colour a headline figure by what it says about itself.
 *
 * On this book the difference between "68.3% green" and "92.9% amber" is the
 * whole answer, so a tile that quietly carries its own band is worth far more
 * than one more grey number.
 */
function kpiTone(label: string, value: string): string | undefined {
  const blob = `${label} ${value}`.toLowerCase();
  if (/breach|exceed|prohibit|restricted|red\b/.test(blob)) return "bad";
  if (/amber|tight|monitor|watch|caution/.test(blob)) return "warn";
  if (/green|comfortable|clear|unused/.test(blob)) return "ok";
  return undefined;
}

/**
 * Promote a leading run of `**Label:** value` figures into stat tiles.
 *
 * Tolerant by design: a real answer often mixes clean figures with one wordy
 * entry. Aborting on that one item would cost the whole row of tiles, so
 * non-qualifying entries are left behind as an ordinary list instead.
 */
function extractKpis(blocks: Block[]): { kpis: Kpi[]; rest: Block[] } {
  // The run is preceded by a disclosure line and a scope line often enough that
  // it is worth looking a few blocks in, but not into the body of the answer.
  const first = blocks.findIndex((b, i) => i <= 3 && b.kind === "list");
  if (first === -1) return { kpis: [], rest: blocks };

  const list = blocks[first] as Extract<Block, { kind: "list" }>;
  if (list.items.length < 3 || list.items.length > 8) return { kpis: [], rest: blocks };

  const kpis: Kpi[] = [];
  const leftovers: { text: string; depth: number }[] = [];

  for (const it of list.items) {
    // The separator may sit inside the bold (`**Label:** 50`) or outside it
    // (`**Label** — 50`); both shapes appear in real answers.
    const m = it.text.match(/^\s*\*\*(.+?)\*\*\s*[:—–-]?\s*(.+)$/);
    const label = m ? m[1].trim().replace(/[:—–-]\s*$/, "") : "";
    const value = m ? m[2].trim() : "";
    // A tile is only worth it for a short, figure-like value.
    if (m && label && value.length <= 34 && parseNumber(value) !== null) {
      kpis.push({ label, value, tone: kpiTone(label, value) });
    } else {
      leftovers.push(it);
    }
  }

  if (kpis.length < 3) return { kpis: [], rest: blocks };

  const rest = blocks.flatMap((b, i) => {
    if (i !== first) return [b];
    return leftovers.length
      ? [{ kind: "list", ordered: false, items: leftovers } as Block]
      : [];
  });

  return { kpis, rest };
}

function KpiRow({ items }: { items: Kpi[] }) {
  return (
    <div className="kpi-row">
      {items.map((k, i) => (
        <div className={`kpi${k.tone ? ` tone-${k.tone}` : ""}`} key={i}>
          <div className="kpi-value">{k.value}</div>
          <div className="kpi-label">{k.label}</div>
        </div>
      ))}
    </div>
  );
}

/* -------------------------------------------------------------- render --- */

function NestedList({ block, idx }: {
  block: Extract<Block, { kind: "list" }>; idx: number;
}) {
  const out: JSX.Element[] = [];
  let i = 0;

  while (i < block.items.length) {
    const item = block.items[i];
    const children: { text: string; depth: number }[] = [];
    let j = i + 1;
    while (j < block.items.length && block.items[j].depth > item.depth) {
      children.push(block.items[j]);
      j += 1;
    }
    out.push(
      <li key={`${idx}-${i}`}>
        {inline(item.text, `li-${idx}-${i}`)}
        {children.length > 0 && (
          <ul className="md-sublist">
            {children.map((c, ci) => (
              <li key={ci}>{inline(c.text, `sli-${idx}-${i}-${ci}`)}</li>
            ))}
          </ul>
        )}
      </li>,
    );
    i = j;
  }

  return block.ordered
    ? <ol className="md-list">{out}</ol>
    : <ul className="md-list">{out}</ul>;
}

export function Markdown({ text }: { text: string }) {
  const blocks = parseBlocks(text);
  const { kpis, rest } = extractKpis(blocks);

  return (
    <div className="md">
      {kpis.length > 0 && <KpiRow items={kpis} />}
      {rest.map((b, i) => {
        switch (b.kind) {
          case "heading": {
            const Tag = `h${Math.min(b.level + 2, 6)}` as keyof JSX.IntrinsicElements;
            return <Tag key={i}>{inline(b.text, `h-${i}`)}</Tag>;
          }
          case "table":
            return <DataTable key={i} model={b.model} />;
          case "list":
            return <NestedList key={i} block={b} idx={i} />;
          case "quote":
            return (
              <div className={`md-callout tone-${b.tone}`} key={i}>
                {inline(b.text, `q-${i}`)}
              </div>
            );
          case "code":
            return <pre className="md-code" key={i}><code>{b.text}</code></pre>;
          case "rule":
            return <hr className="md-rule" key={i} />;
          default:
            return <p key={i}>{inline(b.text, `p-${i}`)}</p>;
        }
      })}
    </div>
  );
}

export function Citations({ items }: { items: Citation[] }) {
  if (!items.length) return null;
  return (
    <details className="citations">
      <summary className="citations-head">
        Sources <span className="citations-count">{items.length}</span>
      </summary>
      <ol>
        {items.map((c, i) => (
          <li key={i}>
            <span className={`cite-kind cite-${c.kind ?? "file"}`} aria-hidden>
              {c.kind === "url" ? "↗" : "▤"}
            </span>
            {c.url ? (
              <a href={c.url} target="_blank" rel="noreferrer">
                {c.title || c.url}
              </a>
            ) : (
              <span>{c.title || c.text || c.fileId || "source"}</span>
            )}
          </li>
        ))}
      </ol>
    </details>
  );
}
