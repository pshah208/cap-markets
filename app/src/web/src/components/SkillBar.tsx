/**
 * Chat skills - actions offered under an agent answer.
 *
 * The Scotia demo puts a "Flyer" button on a customer row, because there the
 * artifact is per-customer and the table is the natural place for it. This book
 * is one relationship at a time, so the skills hang off the ANSWER instead: the
 * agent finishes, and the bar offers the two or three things a banker would
 * actually reach for next.
 *
 * Which skills appear is derived from what the answer talks about, so the bar
 * is a response to the content rather than a fixed toolbar. An answer that
 * never mentions the covenant does not offer to test it.
 */

import { useEffect, useState } from "react";
import { apiGet, apiPost } from "../api";
import type { SkillCatalogue, ProFormaResult } from "../types";
import { ProFormaSkill } from "./skills/ProFormaSkill";
import { RoomCardSkill } from "./skills/RoomCardSkill";
import { RadarSkill } from "./skills/RadarSkill";

export type SkillId = "proforma" | "roomcard" | "radar";

interface SkillDef {
  id: SkillId;
  label: string;
  hint: string;
  glyph: string;
  /** Offered when the answer matches - or always, for the meeting brief. */
  match: RegExp | null;
}

const SKILLS: SkillDef[] = [
  {
    id: "proforma",
    label: "Run the pro-forma test",
    hint: "CP-005 covenant test, fully drawn",
    glyph: "\u25EB",
    match: /covenant|leverage|ebitda|pro-?forma|upsize|hold|headroom|CP-005/i,
  },
  {
    id: "roomcard",
    label: "Build the room card",
    hint: "What we can and cannot say on Thursday",
    glyph: "\u25A4",
    match: null,
  },
  {
    id: "radar",
    label: "Scan the book",
    hint: "Who else is close to a covenant",
    glyph: "\u25C9",
    match: /covenant|portfolio|book|limit|leverage|sector|breach|amber/i,
  },
];

/** Cached across messages - the catalogue is the same for the whole session. */
let cached: SkillCatalogue | null = null;

export function useSkillCatalogue(): SkillCatalogue | null {
  const [data, setData] = useState<SkillCatalogue | null>(cached);
  useEffect(() => {
    if (cached) return;
    let alive = true;
    apiGet<SkillCatalogue>("/api/skills")
      .then((d) => {
        cached = d;
        if (alive) setData(d);
      })
      .catch(() => { /* skills are additive - never break the answer */ });
    return () => { alive = false; };
  }, []);
  return data;
}

export function SkillBar({ answer }: { answer: string }) {
  const catalogue = useSkillCatalogue();
  const [open, setOpen] = useState<SkillId | null>(null);
  const [pf, setPf] = useState<ProFormaResult | null>(null);

  if (!catalogue) return null;

  const offered = SKILLS.filter((s) => !s.match || s.match.test(answer));
  if (!offered.length) return null;

  async function runProForma(incrementalM: number) {
    const r = await apiPost<ProFormaResult>(
      "/api/skills/proforma", { incrementalM },
    );
    setPf(r);
    return r;
  }

  return (
    <>
      <div className="skillbar">
        <span className="skillbar-label">Next</span>
        {offered.map((s) => (
          <button
            key={s.id}
            className="skill-btn"
            onClick={() => setOpen(s.id)}
            title={s.hint}
          >
            <span className="skill-glyph" aria-hidden>{s.glyph}</span>
            <span className="skill-text">
              <span className="skill-label">{s.label}</span>
              <span className="skill-hint">{s.hint}</span>
            </span>
          </button>
        ))}
      </div>

      {open === "proforma" && (
        <SkillModal title="CP-005 pro-forma covenant test" onClose={() => setOpen(null)}>
          <ProFormaSkill catalogue={catalogue} result={pf} onRun={runProForma} />
        </SkillModal>
      )}
      {open === "roomcard" && (
        <SkillModal title="Meeting room card" onClose={() => setOpen(null)} wide>
          <RoomCardSkill card={catalogue.roomcard} />
        </SkillModal>
      )}
      {open === "radar" && (
        <SkillModal title="Portfolio covenant radar" onClose={() => setOpen(null)} wide>
          <RadarSkill radar={catalogue.radar} />
        </SkillModal>
      )}
    </>
  );
}

export function SkillModal({ title, children, onClose, wide }: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="skill-modal-backdrop" onClick={onClose} role="presentation">
      <div
        className={`skill-modal${wide ? " wide" : ""}`}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <header className="skill-modal-head">
          <h3>{title}</h3>
          <div className="skill-modal-actions">
            <button className="skill-modal-print" onClick={() => window.print()}>
              Print
            </button>
            <button className="skill-modal-close" onClick={onClose} aria-label="Close">
              ✕
            </button>
          </div>
        </header>
        <div className="skill-modal-body">{children}</div>
      </div>
    </div>
  );
}
