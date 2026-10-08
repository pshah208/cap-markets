import config from "virtual:bank-config";
import type { AppConfig, Chapter, LayerTable, PlainEnglish, RolePersona, Story } from "./types";

export type BankConfig = typeof config;
export const brand: BankConfig = config;
export const logoSrc = brand.logo === "logo.png" ? "/brand/logo.png" : undefined;

export function bankInitials(shortName: string): string {
  const words = shortName.match(/[\p{L}\p{N}]+/gu);
  if (!words) return Array.from(shortName.trim()).slice(0, 2).join("");
  return (words.length === 1
    ? Array.from(words[0]).slice(0, 2).join("")
    : words.slice(0, 2).map(word => Array.from(word)[0]).join("")).toUpperCase();
}

type RGB = [number, number, number];
const rgb = (hex: string): RGB => [
  parseInt(hex.slice(1, 3), 16),
  parseInt(hex.slice(3, 5), 16),
  parseInt(hex.slice(5, 7), 16),
];
const hex = (value: RGB): string =>
  `#${value.map(channel => Math.round(channel).toString(16).padStart(2, "0")).join("")}`;
const mix = (color: string, target: string, weight: number): string =>
  hex(rgb(color).map((channel, i) => channel * (1 - weight) + rgb(target)[i] * weight) as RGB);

function luminance(color: string): number {
  const channels = rgb(color).map(channel => {
    const value = channel / 255;
    return value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4;
  });
  return channels[0] * .2126 + channels[1] * .7152 + channels[2] * .0722;
}

function contrast(a: string, b: string): number {
  const [lighter, darker] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (lighter + .05) / (darker + .05);
}

function foreground(color: string): string {
  return contrast(color, "#ffffff") >= contrast(color, "#000000") ? "#ffffff" : "#000000";
}

function legibleInk(color: string, background: string, target: string): string {
  for (let step = 0; step <= 100; step++) {
    const candidate = mix(color, target, step / 100);
    if (contrast(candidate, background) >= 7) return candidate;
  }
  return target;
}

/** Apply only the build-validated deployment identity; no browser override. */
export function applyBrand(): void {
  const primary = brand.primaryColor;
  const accent = brand.accentColor;
  const primaryFg = foreground(primary);
  const tint = mix(primary, "#ffffff", .92);
  const ink = legibleInk(primary, tint, "#000000");
  const variables: Record<string, string> = {
    "--brand": primary,
    "--brand-rgb": rgb(primary).join(" "),
    "--brand-fg": primaryFg,
    "--brand-hover": mix(primary, primaryFg === "#ffffff" ? "#000000" : "#ffffff", .12),
    "--brand-deep": ink,
    "--brand-tint": tint,
    "--brand-line": mix(primary, "#ffffff", .75),
    "--brand-ink": ink,
    "--brand-on-dark": legibleInk(primary, "#17171a", "#ffffff"),
    "--accent": accent,
    "--accent-ink": legibleInk(accent, mix(accent, "#ffffff", .86), "#000000"),
    "--accent-fg": foreground(accent),
  };
  for (const [name, value] of Object.entries(variables)) {
    document.documentElement.style.setProperty(name, value);
  }
  document.title = `${brand.bankName} | Capital Markets Client Intelligence`;
  let icon = document.querySelector<HTMLLinkElement>("link[rel='icon']");
  if (logoSrc) {
    if (!icon) {
      icon = document.createElement("link");
      icon.rel = "icon";
      document.head.appendChild(icon);
    }
    icon.type = "image/png";
    icon.href = logoSrc;
  } else {
    icon?.remove();
  }
}

/** Authored narrative only. "The Bank of Canada" is a name, not a placeholder. */
export function replaceBankPlaceholder(text: string): string {
  return text.replace(/\b(?:the Bank|The Bank)\b(?!\s+[Oo][Ff]\b)/g, () => brand.bankShortName);
}

const text = replaceBankPlaceholder;
const optionalText = (value: string | undefined) => value === undefined ? value : text(value);
const lines = (value: string[]) => value.map(text);

function rolePersona(value: RolePersona): RolePersona {
  return { ...value, goal: text(value.goal), objectives: lines(value.objectives), points: lines(value.points) };
}

function plainEnglish(value: PlainEnglish): PlainEnglish {
  return {
    ...value,
    heading: text(value.heading),
    lead: optionalText(value.lead),
    punch: optionalText(value.punch),
    cards: value.cards?.map(card => ({
      ...card, title: text(card.title), sub: optionalText(card.sub), body: text(card.body),
    })),
    gauges: value.gauges?.map(gauge => ({
      ...gauge, label: text(gauge.label), sub: optionalText(gauge.sub),
      value: text(gauge.value), caption: text(gauge.caption),
    })),
  };
}

function chapter(value: Chapter): Chapter {
  return {
    ...value,
    title: text(value.title),
    kicker: text(value.kicker),
    body: text(value.body),
    points: value.points?.map(text),
    columns: value.columns?.map(column => ({
      ...column, title: text(column.title), tag: text(column.tag),
      items: column.items.map(item => ({ ...item, name: text(item.name), detail: text(item.detail) })),
    })),
    metrics: value.metrics?.map(metric => ({
      ...metric, label: text(metric.label), value: text(metric.value), sub: optionalText(metric.sub),
    })),
    wrong: value.wrong && { ...value.wrong, head: text(value.wrong.head), lines: lines(value.wrong.lines) },
    right: value.right && { ...value.right, head: text(value.right.head), lines: lines(value.right.lines) },
    assurances: value.assurances?.map(text),
    note: optionalText(value.note),
    prompt: value.prompt === null ? null : text(value.prompt),
    expect: value.expect?.map(text),
    layerTable: value.layerTable && {
      ...value.layerTable,
      headers: value.layerTable.headers.map(text) as LayerTable["headers"],
      rows: value.layerTable.rows.map(row => ({
        ...row, holds: text(row.holds), tells: text(row.tells), cannot: text(row.cannot),
      })),
    },
    pathSteps: value.pathSteps?.map(step => ({
      ...step, constraint: text(step.constraint), clears: text(step.clears), owner: text(step.owner),
    })),
    plain: value.plain && plainEnglish(value.plain),
  };
}

/** Keep identifiers, URLs, citations and unrecognised fields byte-for-byte. */
export function brandStory(value: Story): Story {
  return {
    ...value,
    persona: {
      ...value.persona,
      org: value.persona.org.replace(/\b(?:the Bank|The Bank)\b(?!\s+[Oo][Ff]\b)/g, () => brand.bankName),
      title: text(value.persona.title),
      goal: text(value.persona.goal),
      objectives: lines(value.persona.objectives),
      points: value.persona.points?.map(text),
    },
    personaByRole: value.personaByRole && Object.fromEntries(
      Object.entries(value.personaByRole).map(([key, persona]) => [key, rolePersona(persona)]),
    ),
    chapters: value.chapters.map(chapter),
    suggestions: lines(value.suggestions),
  };
}

export function brandAppConfig(value: AppConfig): AppConfig {
  return {
    ...value,
    bank: brand.bankName,
    agentName: text(value.agentName),
    disclaimer: text(value.disclaimer),
  };
}
