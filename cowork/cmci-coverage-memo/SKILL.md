---
name: cmci-coverage-memo
description: Turns a client call in the Capital Markets Client Intelligence demo into two DRAFTS - an internal coverage memo (Word) and a client follow-up email (Outlook draft). Use after a coverage call, when the banker asks to "write up the call", "draft the coverage memo", or "send the follow-up". Refers to the firm only as "the Bank". Never sends anything.
---

# CMCI Coverage Memo (Microsoft 365 Copilot Cowork skill)

The last step of the coverage workflow. The CMCI web app does the same thing in its
**Wrap-up** step (memo .docx + "Save email to Outlook drafts"); this skill lets a banker
with **Cowork** access do it from Microsoft 365 Copilot instead. The app's wrap-up
screen generates the exact prompt to paste.

For initial setup, choose your selected bank first. From the project root, run:

```powershell
.\setup-bank.ps1 -BankName 'Example Bank' -BankShortName 'Example' -PrimaryColor '#164E63' -AccentColor '#B45309'
```

Follow the project-root [README.md](../../README.md) for full deployment and
Microsoft 365 connection configuration; use the demo identities configured there.

**Synthetic demo data.** Real public companies are used as issuer labels, but
internal figures, relationships, correspondence and policies are invented for the
demo and do not describe a real institution's clients or credit positions.

## Inputs (from the banker's prompt)

- Client name and the contact's **role** (CFO or Treasurer) - never invent a name.
- The market context (the scenario headline) and the client-specific impact
  (covenant before -> after against the threshold).
- The agreed next steps.
- Optional banker notes.

## Grounding

Before drafting, retrieve - do not assume:

1. **Work IQ** - the client's recent email and meeting threads, and any Control Room
   restriction (e.g. `CR-2026-0184` for Gibson Energy).
2. **Foundry IQ** - CP-015 (Credit & Markets Committee house view: approved framing,
   disclaimers, approvals, never-say list), CP-014 (confidentiality), CP-008
   (information barriers), CP-003 (no hold size before approval).

## Output 1 - Coverage memo (Word, saved as a draft)

Title: `Coverage memo - <Client> - <date>`. Sections:

1. **Context** - the market move, in one or two sentences.
2. **Position (internal - CP-014)** - covenant headroom, limit utilisation, rating trend,
   KYC date. Internal only.
3. **Shock impact** - covenant before -> after vs threshold; EBITDA cushion; for a live deal,
   the re-cut largest clearing increase.
4. **Call summary** - participant roles, channel, and whether the source records
   show that approved framing was used; never infer an approval.
5. **Agreed next steps** - as a checklist with owners.
6. **Guardrails applied** - what was deliberately not said.

Mark the document **DRAFT - not approved**.

## Output 2 - Client follow-up email (Outlook draft)

- Subject: `Following up on today's call - <Client>`.
- Thank the client; restate the committee's read using **CP-015 approved framing only**.
- List the agreed next steps that are client-facing (omit internal items such as
  Control Room or credit-process steps).
- Include the disclaimers: any market view is forward-looking and not advice; any change
  to facility size or terms is subject to internal approval.
- Sign off using the relationship owner's role, such as Coverage Lead.
- **Leave the recipient empty** and save as a draft. Never send.

## Hard rules

- Refer to the firm as **"the Bank"** - never by name.
- Refer to demo colleagues by role: Coverage Lead, Corporate Banking Lead, Research
  Analyst, Markets Lead, Credit Risk Lead or Control Room Officer; client contacts
  are CFO or Treasurer.
- Never include internal ratings, limits or utilisation, sector capacity, wallet share or
  competitor rankings in the email (CP-014).
- Never mention a restricted subject or that a wall-crossing exists; never name crossed
  individuals (CP-008).
- Never state a hold size, price or structure as firm (CP-003).
- Everything is a draft for human review. Nothing is sent.
