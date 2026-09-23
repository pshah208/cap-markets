/**
 * BMO Capital Markets - Global Client Intelligence Agent
 * Scenario and capability brief.
 *
 * Every figure is pulled from capital-markets-client-intelligence/data/scenario_facts.py,
 * the single source of truth the whole demo reconciles against.
 *
 *   npm install -g docx
 *   node build_brief.js
 */

const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, LevelFormat, HeadingLevel,
  BorderStyle, WidthType, ShadingType, PageNumber, PageBreak,
  TabStopType, TabStopPosition, VerticalAlign,
} = require("docx");

// ---------------------------------------------------------------- tokens ---
const BRAND = "0051A5";
const BRAND_DEEP = "003D7D";
const INK = "14171C";
const INK2 = "39404A";
const MUTED = "6B7280";
const LINE = "D9DEE5";

const IQ = {
  work:    { name: "Work IQ",    colour: "7C3AED", tint: "F2EDFC" },
  fabric:  { name: "Fabric IQ",  colour: "0F766E", tint: "E6F2F1" },
  foundry: { name: "Foundry IQ", colour: "B45309", tint: "FBF0E2" },
  web:     { name: "Web IQ",     colour: "1D4ED8", tint: "E8EEFC" },
};

const CONTENT_W = 9360;   // US Letter, 1" margins
const thin = { style: BorderStyle.SINGLE, size: 1, color: LINE };
const cellBorders = { top: thin, bottom: thin, left: thin, right: thin };
const noBorders = {
  top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE },
  left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE },
};
const PAD = { top: 100, bottom: 100, left: 140, right: 140 };

// ------------------------------------------------------------- helpers ---
const p = (text, opts = {}) =>
  new Paragraph({
    spacing: { after: opts.after ?? 140, before: opts.before ?? 0, line: 276 },
    alignment: opts.align,
    children: [new TextRun({
      text,
      size: opts.size ?? 21,
      bold: opts.bold,
      italics: opts.italics,
      color: opts.color ?? INK2,
    })],
  });

/** Paragraph from an array of {text, bold, color} fragments. */
const rich = (parts, opts = {}) =>
  new Paragraph({
    spacing: { after: opts.after ?? 140, before: opts.before ?? 0, line: 276 },
    children: parts.map((x) => new TextRun({
      text: x.text,
      bold: x.bold,
      italics: x.italics,
      size: opts.size ?? 21,
      color: x.color ?? opts.color ?? INK2,
    })),
  });

const h1 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(text)] });
const h2 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(text)] });
const h3 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(text)] });

const bullet = (text, opts = {}) =>
  new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { after: 70, line: 264 },
    children: [new TextRun({ text, size: 21, color: INK2, bold: opts.bold })],
  });

/** Bullet whose leading fragment is bold, e.g. "GP-002 - the rest". */
const bulletRich = (parts) =>
  new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { after: 70, line: 264 },
    children: parts.map((x) => new TextRun({
      text: x.text, bold: x.bold, italics: x.italics, size: 21, color: x.color ?? INK2,
    })),
  });

/** A horizontal rule, drawn as a paragraph border (never a table). */
const rule = (colour = LINE) =>
  new Paragraph({
    spacing: { after: 180, before: 60 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: colour, space: 1 } },
    children: [new TextRun({ text: "", size: 2 })],
  });

/** Full-width tinted callout carrying a demo question. */
const questionBox = (label, question, colour, tint) =>
  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [CONTENT_W],
    rows: [new TableRow({
      children: [new TableCell({
        width: { size: CONTENT_W, type: WidthType.DXA },
        borders: {
          top: { style: BorderStyle.NONE },
          bottom: { style: BorderStyle.NONE },
          right: { style: BorderStyle.NONE },
          left: { style: BorderStyle.SINGLE, size: 18, color: colour },
        },
        shading: { fill: tint, type: ShadingType.CLEAR },
        margins: { top: 130, bottom: 130, left: 200, right: 160 },
        children: [
          new Paragraph({
            spacing: { after: 60 },
            children: [new TextRun({
              text: label, bold: true, size: 16, color: colour,
              allCaps: true,
            })],
          }),
          new Paragraph({
            spacing: { after: 0, line: 276 },
            children: [new TextRun({
              text: `\u201C${question}\u201D`,
              size: 22, italics: true, color: INK, bold: true,
            })],
          }),
        ],
      })],
    })],
  });

/** Header row + body rows. widths must sum to CONTENT_W.
 *
 * Cells may be a plain string or {text, bold, color}. Strings MUST be
 * normalised first: `"abc".bold` resolves to the deprecated
 * String.prototype.bold method, which docx then writes into the XML as
 * `w:val="function bold() { [native code] }"` and Word rejects the file.
 */
const table = (headers, rows, widths, accent = BRAND) =>
  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: widths,
    rows: [
      new TableRow({
        tableHeader: true,
        children: headers.map((htext, i) => new TableCell({
          width: { size: widths[i], type: WidthType.DXA },
          borders: cellBorders,
          shading: { fill: accent, type: ShadingType.CLEAR },
          margins: PAD,
          verticalAlign: VerticalAlign.CENTER,
          children: [new Paragraph({
            spacing: { after: 0 },
            children: [new TextRun({ text: htext, bold: true, size: 19, color: "FFFFFF" })],
          })],
        })),
      }),
      ...rows.map((cells, r) => new TableRow({
        children: cells.map((raw, i) => {
          const c = (typeof raw === "string") ? { text: raw } : raw;
          return new TableCell({
            width: { size: widths[i], type: WidthType.DXA },
            borders: cellBorders,
            shading: { fill: r % 2 ? "F5F8FB" : "FFFFFF", type: ShadingType.CLEAR },
            margins: PAD,
            verticalAlign: VerticalAlign.CENTER,
            children: [new Paragraph({
              spacing: { after: 0, line: 260 },
              children: [new TextRun({
                text: String(c.text ?? ""),
                size: 19,
                bold: c.bold === true,
                color: c.color ?? INK2,
              })],
            })],
          });
        }),
      })),
    ],
  });

// ------------------------------------------------------- one IQ section ---
function iqSection(key, tagline, contributes, looksAt, questions) {
  const { name, colour, tint } = IQ[key];
  const out = [
    new Paragraph({
      heading: HeadingLevel.HEADING_2,
      children: [new TextRun({ text: name, color: colour })],
    }),
    rich([{ text: tagline, italics: true, color: colour, bold: true }], { after: 160, size: 22 }),
    p(contributes),
    rich([{ text: "Where it looks", bold: true, color: INK }], { after: 80, before: 60 }),
    ...looksAt.map((x) => bullet(x)),
  ];

  questions.forEach((q, i) => {
    out.push(new Paragraph({ spacing: { after: 0, before: 200 }, children: [] }));
    out.push(questionBox(`Question ${i + 1} of 2`, q.q, colour, tint));
    out.push(rich([{ text: "What a good answer shows", bold: true, color: INK }],
                  { after: 80, before: 160 }));
    q.shows.forEach((s) => out.push(
      typeof s === "string" ? bullet(s) : bulletRich(s)));
    if (q.why) {
      out.push(rich([
        { text: "Why it matters.  ", bold: true, color: colour },
        { text: q.why },
      ], { after: 60, before: 100 }));
    }
  });

  return out;
}

// ---------------------------------------------------------------- build ---
const doc = new Document({
  creator: "BMO Capital Markets demo",
  title: "Global Client Intelligence Agent - scenario and capability brief",
  description: "SYNTHETIC DEMO DATA.",
  styles: {
    default: { document: { run: { font: "Arial", size: 21, color: INK2 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 34, bold: true, font: "Arial", color: BRAND_DEEP },
        paragraph: { spacing: { before: 360, after: 200 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 27, bold: true, font: "Arial", color: BRAND },
        paragraph: { spacing: { before: 300, after: 140 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 22, bold: true, font: "Arial", color: INK },
        paragraph: { spacing: { before: 220, after: 100 }, outlineLevel: 2 } },
    ],
  },
  numbering: {
    config: [{
      reference: "bullets",
      levels: [{
        level: 0, format: LevelFormat.BULLET, text: "\u2022",
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 360, hanging: 220 } } },
      }],
    }],
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
      },
    },
    headers: {
      default: new Header({ children: [new Paragraph({
        spacing: { after: 0 },
        border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: BRAND, space: 6 } },
        tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX }],
        children: [
          new TextRun({ text: "BMO Capital Markets", bold: true, size: 17, color: BRAND }),
          new TextRun({ text: "\tGlobal Client Intelligence Agent", size: 17, color: MUTED }),
        ],
      })] }),
    },
    footers: {
      default: new Footer({ children: [new Paragraph({
        tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX }],
        children: [
          new TextRun({ text: "SYNTHETIC DEMO DATA \u2014 not real client information",
                        size: 15, color: MUTED, italics: true }),
          new TextRun({ text: "\t", size: 15 }),
          new TextRun({ text: "Page ", size: 15, color: MUTED }),
          new TextRun({ children: [PageNumber.CURRENT], size: 15, color: MUTED }),
          new TextRun({ text: " of ", size: 15, color: MUTED }),
          new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 15, color: MUTED }),
        ],
      })] }),
    },
    children: [
      // ---------------------------------------------------------- cover ---
      new Paragraph({
        spacing: { before: 700, after: 60 },
        children: [new TextRun({
          text: "GLOBAL COVERAGE \u00B7 METALS & MINING", bold: true,
          size: 18, color: BRAND, allCaps: true,
        })],
      }),
      new Paragraph({
        spacing: { after: 60 },
        children: [new TextRun({
          text: "Global Client Intelligence Agent",
          bold: true, size: 46, color: BRAND_DEEP,
        })],
      }),
      new Paragraph({
        spacing: { after: 200 },
        children: [new TextRun({
          text: "Preparing for the Gibson Energy Inc. meeting with four layers of grounded intelligence",
          size: 25, color: INK2,
        })],
      }),
      rule(BRAND),

      new Table({
        width: { size: CONTENT_W, type: WidthType.DXA },
        columnWidths: [CONTENT_W],
        rows: [new TableRow({ children: [new TableCell({
          width: { size: CONTENT_W, type: WidthType.DXA },
          borders: {
            top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE },
            right: { style: BorderStyle.NONE },
            left: { style: BorderStyle.SINGLE, size: 18, color: "B45309" },
          },
          shading: { fill: "FBF0E2", type: ShadingType.CLEAR },
          margins: { top: 140, bottom: 140, left: 200, right: 160 },
          children: [
            new Paragraph({ spacing: { after: 60 }, children: [new TextRun({
              text: "Synthetic demonstration data", bold: true, size: 20, color: "8A4008" })] }),
            new Paragraph({ spacing: { after: 0, line: 264 }, children: [new TextRun({
              text: "BMO Capital Markets is used here as a branding label only. Every internal "
                  + "figure in this document \u2014 exposures, limits, revenue, wallet share, ratings, "
                  + "covenants, colleagues, emails and policies \u2014 was generated for a demonstration "
                  + "and reflects no real institution, client relationship or credit position. "
                  + "Gibson Energy Inc., Keyera Corp. and Whitecap Resources Inc. are real, publicly listed "
                  + "companies, named only so that live web grounding returns genuine public news.",
              size: 19, color: "6B3A08" })] }),
          ],
        })] })],
      }),

      // ------------------------------------------------------ scenario ---
      h1("The scenario"),

      rich([
        { text: "It is Monday 17 August 2026. On Thursday, four bankers from three business " },
        { text: "lines fly to Rio de Janeiro to meet the CFO and Group Treasurer of " },
        { text: "Gibson Energy Inc.", bold: true, color: INK },
        { text: " (TSX:GEI), a Tier 1 midstream energy client BMO has banked " },
        { text: "since 2007.", },
      ]),

      p("Each banker has done their homework. Each is bringing a different ask. None of them "
      + "has checked the same thing \u2014 and the constraint that decides the meeting is not on "
      + "any of their slides."),

      h3("Who is in the room"),
      table(
        ["Person", "Role", "What they want from Thursday"],
        [
          [{ text: "Cora Thomas", bold: true, color: INK },
           "MD, Global Coverage \u2014 Metals & Mining",
           { text: "Relationship owner. Must know what we can and cannot say.", color: INK }],
          ["Dakota Sanchez", "Director, Global Investment Banking",
           "A role on a USD 1.5bn multi-currency refinancing of the 2027 maturities"],
          ["Kai Carter", "Director, Corporate Banking",
           "Upsize the revolver \u2014 USD 200m incremental hold"],
          ["Hadar Caspit", "Director, Global Markets",
           "A USD 900m, 24-month BRL/USD and copper hedging overlay"],
        ],
        [2000, 3160, 4200],
      ),

      h3("What the systems say \u2014 and why it misleads"),
      p("Read the governed position the way a banker would on the way to the airport. Every "
      + "headline indicator is comfortable."),

      table(
        ["Indicator", "Position", "Status"],
        [
          ["Total committed", "USD 1,100m across 5 facilities", "\u2014"],
          ["Measured exposure", "USD 722m", "\u2014"],
          ["Single-name limit", "USD 722m of 1,000m \u2014 72.2%",
           { text: "GREEN", bold: true, color: "15803D" }],
          ["Sector \u2014 Metals & Mining", "USD 3,050m of 4,200m \u2014 72.6%",
           { text: "GREEN", bold: true, color: "15803D" }],
          ["Internal risk rating", "IG-5, improved from IG-6 two quarters ago",
           { text: "GREEN", bold: true, color: "15803D" }],
          ["Leverage covenant", "1.98x against a 3.50x maximum",
           { text: "GREEN", bold: true, color: "15803D" }],
        ],
        [2500, 4660, 2200],
      ),

      p("The obvious conclusion is that there is USD 278m of headroom, so another USD 200m "
      + "of lending fits comfortably. That conclusion is wrong, and every number behind it "
      + "is correct.", { before: 140 }),

      new Paragraph({ children: [new PageBreak()] }),

      h2("What actually binds"),
      p("Mining assets sit where the geology is, not where the capital is, so this sector "
      + "concentrates country and transfer risk in a way few others do. The binding "
      + "constraint is not on the client at all \u2014 it is on the country."),

      table(
        ["Energy sector country and transfer risk envelope", "Value"],
        [
          ["Limit", { text: "USD 2,400m", bold: true, color: INK }],
          ["Utilised", { text: "USD 2,196m", bold: true, color: INK }],
          ["Utilisation", { text: "91.5% \u2014 AMBER (trigger 85%)", bold: true, color: "B45309" }],
          ["Headroom", { text: "USD 204m", bold: true, color: INK }],
          ["Pending: Corporate Banking revolver upsize", "USD 200m"],
          ["Pending: Global Markets hedging pre-settlement exposure", "USD 46m"],
          ["Total pending demand", { text: "USD 246m", bold: true, color: INK }],
          ["Headroom after pending demand",
           { text: "\u2212USD 42m \u2014 shortfall", bold: true, color: "B91C1C" }],
        ],
        [6160, 3200],
      ),

      p("Two colleagues, both right, are competing for one resource. Lending and derivatives "
      + "draw on the same country envelope, and together they exceed it by USD 42m. Neither "
      + "banker may resolve it: the decision is reserved to the Country Risk Committee, which "
      + "has acknowledged the combined submission under reference CRC-2026-0412 and deferred "
      + "it to 27 August \u2014 seven days after the client meeting.", { before: 140 }),

      p("There is a second, quieter trap. The revolver carries a springing financial covenant "
      + "that is not tested below 50% utilisation. The facility sits at 40% today, so the "
      + "covenant reads as dormant. On the proposed transaction it goes to 58.5% pro forma "
      + "\u2014 and springs."),

      // --------------------------------------------------- why it's hard ---
      h1("Why this is hard without an agent"),
      p("Answering \u201Ccan we do this?\u201D properly means reconciling four systems that do "
      + "not talk to each other, under time pressure, while the answer that feels right is "
      + "the wrong one."),

      bullet("The exposures and limits live in a governed data platform."),
      bullet("The debate, the commitments and the committee reference live in email, Teams "
           + "and meeting records."),
      bullet("The rules that decide what is permitted live in a policy corpus."),
      bullet("What is happening to the client in the outside world lives on the public web."),

      p("A conventional search tool retrieves from one of these and stops at the first "
      + "authoritative-looking number. The Global Client Intelligence Agent reasons across "
      + "all four \u2014 and, critically, knows when to refuse.", { before: 140 }),

      // ------------------------------------------------------ four IQs ---
      h1("The four IQ layers"),
      p("Microsoft IQ gives the agent one continuously updated understanding of the "
      + "organisation. Each layer answers a different question, and each is queried under "
      + "the signed-in banker\u2019s own permissions \u2014 the agent can never surface "
      + "something the user could not open themselves."),

      table(
        ["Layer", "Answers", "Grounded in"],
        [
          [{ text: "Work IQ", bold: true, color: IQ.work.colour },
           "What has my team already said, decided or committed to?",
           "Outlook, Teams, SharePoint, OneDrive, meeting records"],
          [{ text: "Fabric IQ", bold: true, color: IQ.fabric.colour },
           "What are the governed numbers?",
           "OneLake, semantic model, 38 measures over 14 tables"],
          [{ text: "Foundry IQ", bold: true, color: IQ.foundry.colour },
           "What are we permitted to do, and who approves it?",
           "Azure AI Search over the CP-001\u2013CP-014 policy corpus"],
          [{ text: "Web IQ", bold: true, color: IQ.web.colour },
           "What is happening to this client in the outside world?",
           "Grounding with Bing \u2014 live, cited and dated"],
        ],
        [1560, 4000, 3800],
      ),

      p("The eight questions that follow are the ones used to demonstrate each layer. Two per "
      + "layer: the first shows the layer doing what only it can do, the second shows it "
      + "producing insight a banker would act on.", { before: 160 }),

      new Paragraph({ children: [new PageBreak()] }),

      // ---------------------------------------------------------- Work ---
      ...iqSection("work",
        "Understands how people work.",
        "Work IQ reads the organisation\u2019s own working memory \u2014 the emails, chats, "
        + "documents and meeting records where decisions actually get made. This is the "
        + "context that exists in no database: who committed to what, what a committee "
        + "actually ruled, and which promises are still outstanding.",
        [
          "Exchange \u2014 18 emails across the four bankers, including the committee forward",
          "Teams \u2014 four channels carrying the internal argument between business lines",
          "SharePoint and OneDrive \u2014 the pre-meeting brief, client pack and five meeting records",
        ],
        [
          {
            q: "What is reference CRC-2026-0412, and what did the committee decide?",
            shows: [
              "The Country Risk Committee acknowledgement of 10 August, forwarded by Cora Thomas",
              "Both requests will be assessed together on 27 August \u2014 neither has priority "
              + "by size or by order of submission",
              "The Committee explicitly declined to determine the booking-entity question on "
              + "the material provided",
              "Three confirmations are required before it will \u2014 cash-flow source, guarantee "
              + "position, and written Legal and Tax sign-off",
              "The determination may not be assumed, anticipated or represented to the client",
            ],
            why: "That reference exists nowhere except this tenant\u2019s mail and documents. "
               + "No amount of data or policy retrieval would surface it, and walking into "
               + "Thursday without it risks implying an answer the bank has not given.",
          },
          {
            q: "What has our team already committed to Gibson Energy, and is anything still outstanding?",
            shows: [
              "Commitments traced to the person who made them and the meeting or thread they were made in",
              "Follow-ups from the 28 May coverage call that have not yet been closed",
              "Where two business lines have told the client different things about timing",
              "Who owns each open item, so the room can be briefed before it becomes a surprise",
            ],
            why: "Coverage risk is rarely a data problem. It is the forgotten undertaking made "
               + "by a colleague in a call the relationship owner did not attend.",
          },
        ]),

      new Paragraph({ children: [new PageBreak()] }),

      // -------------------------------------------------------- Fabric ---
      ...iqSection("fabric",
        "Understands how the business runs.",
        "Fabric IQ reasons over governed business entities \u2014 not a spreadsheet someone "
        + "exported last week, but the semantic model with its measures, relationships and "
        + "rules intact. It is the difference between retrieving a number and understanding "
        + "which number applies.",
        [
          "OneLake \u2014 14 Delta tables covering three countries and three business lines",
          "Semantic model \u2014 38 governed measures, so \u201Cexposure\u201D means one thing everywhere",
          "Exposures, limits, country envelopes, covenants, revenue, wallet share and trades",
        ],
        [
          {
            q: "What is the Energy sector country and transfer risk limit, how much is utilised, "
             + "and what is the headroom after pending demand?",
            shows: [
              "Limit USD 2,400m, utilised USD 2,196m, utilisation 91.5% \u2014 AMBER against an 85% trigger",
              "Headroom USD 204m, as at 17 August 2026",
              "Pending demand USD 246m \u2014 USD 200m Corporate Banking plus USD 46m Global Markets",
              "Headroom after pending demand: \u2212USD 42m",
              "Flagged as confidential internal information that may not be disclosed to the client",
            ],
            why: "This is the table nobody opens until it is too late. The agent surfaces it "
               + "because the semantic model knows the country envelope is an applicable "
               + "constraint, not because anyone thought to ask.",
          },
          {
            q: "Where is our wallet share weakest with Gibson Energy, and what is the whitespace worth?",
            shows: [
              "Overall wallet share 14.8%, improved from 12.6%; rank 4, up from 6",
              "Strength in Debt Capital Markets and FX, weakness in advisory",
              "Equity Capital Markets: zero revenue in 19 years of relationship, against an "
              + "estimated USD 12m street wallet",
              "The competitor holding the position we do not, product by product",
            ],
            why: "A governed model can answer \u201Cwhere have we never been mandated?\u201D \u2014 "
               + "a question about absence. That is close to impossible to ask of a document store.",
          },
        ]),

      new Paragraph({ children: [new PageBreak()] }),

      // ------------------------------------------------------- Foundry ---
      ...iqSection("foundry",
        "Understands what we are permitted to do.",
        "Foundry IQ retrieves authoritative institutional knowledge \u2014 credit policy, "
        + "country frameworks, booking rules, approval authorities, suitability standards and "
        + "conduct requirements. It is what turns a number into a decision, and what stops a "
        + "reasonable-sounding idea from reaching the client.",
        [
          "Azure AI Search over CP-001 to CP-014, the global banking policy corpus",
          "Country and transfer risk (GP-002), cross-border booking (GP-003), "
          + "commitment authority (GP-004)",
          "Derivatives and margin (GP-005), springing covenants (GP-006), "
          + "suitability (GP-010), conduct (CP-014)",
        ],
        [
          {
            q: "Could we book part of the exposure through a North American entity instead, "
             + "so Energy sector stops binding?",
            shows: [
              [{ text: "GP-003", bold: true, color: INK },
               { text: " \u2014 a booking-entity change is not a risk transfer" }],
              "Transfer risk follows the cash flows that repay the facility, not the legal "
              + "entity that books it",
              "Four tests must all hold, including no parent guarantee, keepwell or comfort arrangement",
              "The determination is reserved to the Country Risk Committee and must be sought "
              + "before the pitch, not after",
              "The agent should refuse to present this as available, and name who decides",
            ],
            why: "This is the escape route someone always proposes. Policy exists precisely to "
               + "catch it, and an agent that cannot say \u201Cno, and here is why\u201D is worse "
               + "than no agent at all.",
          },
          {
            q: "What approval and evidence do we need before we can propose the hedging overlay?",
            shows: [
              [{ text: "GP-005", bold: true, color: INK },
               { text: " \u2014 derivatives consume the same country envelope as lending, and "
                     + "pre-settlement exposure turns amber at 75%, not 85%" }],
              [{ text: "GP-010", bold: true, color: INK },
               { text: " \u2014 the client\u2019s underlying exposure must be documented before "
                     + "any structure is proposed, with a Tier 2 scenario illustration "
                     + "including the adverse case" }],
              "The pre-settlement line stands at USD 104m of 120m \u2014 86.7%, already amber",
              "Approval tier is set by the resulting total position, not the increment (GP-004)",
            ],
            why: "The suitability and evidence requirements land before the pitch, not before "
               + "the trade. Discovering that in the room is expensive.",
          },
        ]),

      new Paragraph({ children: [new PageBreak()] }),

      // ----------------------------------------------------------- Web ---
      ...iqSection("web",
        "Understands the world outside the bank.",
        "Web IQ brings fresh external intelligence \u2014 rating actions, earnings, regulatory "
        + "developments, commodity conditions and controversies \u2014 with citations and "
        + "retrieval dates. Internal records go stale; the client does not stop moving.",
        [
          "Grounding with Bing \u2014 live retrieval, no cached snapshot",
          "Real listed issuers: Gibson Energy Inc., Keyera Corp., Whitecap Resources Inc.",
          "Every external claim carries a source and a date; if nothing is found, it says so",
        ],
        [
          {
            q: "What is Gibson Energy\u2019s current public credit rating from the major agencies? "
             + "Cite your sources with dates.",
            shows: [
              "Live agency ratings retrieved from public sources, each with a URL and a date",
              "Rating actions distinguished from the current standing, with the date of the action",
              "Public ratings kept strictly separate from the internal IG-5 rating",
              "It must not quote the internal placeholder, which deliberately reads "
              + "\u201Cindicative \u2014 verify via Web IQ\u201D",
            ],
            why: "The internal record stores public ratings as an unusable placeholder by "
               + "design. The agent has to notice, and go and look. Quoting the placeholder "
               + "as a rating is a failure.",
          },
          {
            q: "What has happened to Gibson Energy in the last 30 days that could change Thursday\u2019s "
             + "conversation?",
            shows: [
              "Recent public developments, dated and sourced \u2014 results, guidance, issuance, "
              + "leadership, regulatory and commodity conditions",
              "Relevance made explicit: what each item does to the refinancing, the revolver or the hedge",
              "Comparator context from Keyera and Whitecap where it sharpens the read",
              "No environmental, safety or regulatory incident asserted without a citation",
            ],
            why: "This is the only layer that can tell the coverage team something the bank "
               + "does not already know \u2014 and the one most likely to change the tone of "
               + "a meeting.",
          },
        ]),

      new Paragraph({ children: [new PageBreak()] }),

      // ------------------------------------------------ all four at once ---
      h1("All four layers on one question"),
      p("The layers matter most when they disagree. This is the question a Managing Director "
      + "actually asks on the way to the airport \u2014 and the one where a plausible answer "
      + "and a correct answer look nothing alike."),

      questionBox("The question that decides the meeting",
        "We have a USD 1 billion single-name limit on Gibson Energy and we are only using 722. "
        + "Can we lend them another 200?", BRAND, "E8F0FA"),

      new Paragraph({ spacing: { after: 0, before: 200 }, children: [] }),
      table(
        ["A search tool answers", "A grounded agent answers"],
        [
          [{ text: "\u201CYes \u2014 there is USD 278m of headroom.\u201D", bold: true, color: "B91C1C" },
           { text: "\u201CNo \u2014 not as currently positioned.\u201D", bold: true, color: BRAND_DEEP }],
          ["Finds the single-name limit and stops",
           "Checks every limit that applies, not just the obvious one"],
          ["Answers from the first authoritative-looking number",
           "Names Energy sector at 91.5% as the binding constraint \u2014 204 headroom against 246 demand"],
          ["Misses a covenant that has not sprung yet",
           "Surfaces the springing test: 40% today, 58.5% pro forma \u2014 it springs"],
          ["Picks the larger request as the winner",
           "Refuses to prioritise between two business lines"],
          ["Sounds completely confident",
           "Cites GP-002, GP-004, GP-005 and GP-006, and escalates to the Country Risk Committee"],
        ],
        [4680, 4680],
      ),

      p("Both answers are built from true numbers. Only one of them is safe to act on.",
        { before: 160, bold: true, color: INK }),

      h2("What this demonstrates"),
      bullet("The agent reconciles four systems that disagree, rather than retrieving from one."),
      bullet("It finds a constraint nobody asked it about, because the governed model knows "
           + "the constraint applies."),
      bullet("It grounds every claim in a named layer and cites policy by identifier."),
      bullet("It separates confidential internal positions from what may be said in the room."),
      bulletRich([
        { text: "It declines to make a decision that is not its to make ", bold: true, color: INK },
        { text: "\u2014 and names the committee that owns it." },
      ]),

      p("The value is not that it answered. It is that it refused to answer the part that was "
      + "not its to decide, and said why.", { before: 160, italics: true, color: BRAND_DEEP }),

      rule(BRAND),
      p("All internal figures in this document are synthetic and were generated for "
      + "demonstration purposes. Figures reconcile across all four layers as at 17 August 2026.",
        { size: 17, color: MUTED, italics: true }),
    ],
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync("BMO-Capital-Markets-Client-Intelligence-Brief.docx", buf);
  console.log("written: BMO-Capital-Markets-Client-Intelligence-Brief.docx");
});
