"""Capital Markets Client Intelligence — bank-neutral BFF.

Endpoints
    GET  /health          liveness + configuration summary
    GET  /api/config      what the SPA needs to bootstrap (no secrets)
    GET  /api/me          the signed-in user, as the BFF sees them
    GET  /api/iqs         the IQ catalogue
    GET  /api/story       the guided demo chapters
    GET  /api/metrics/agent   Foundry-measured token, cost and run telemetry
    GET  /api/web-pulse   live, cached Web IQ headlines for the story
    GET  /api/fabric-capacity          Fabric capacity state (top-bar control)
    POST /api/fabric-capacity/{action} suspend | resume the capacity
    POST /api/chat        SSE: iq_active / status / message / error / done
    GET  /api/diag        auth + OBO + agent reachability, for troubleshooting
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from .agent_client import run_agent
from .auth import User, current_user, exchange_obo
from .config import settings
from .iq import iq_catalogue
from .papers import build as build_papers
from .papers import to_docx as papers_docx
from .skills import catalogue as skill_catalogue
from .skills import proforma as run_proforma
from .skills import proforma_verdict
from .telemetry import snapshot as telemetry_snapshot
from .web_pulse import pulse as web_pulse
from . import client_skills, cm_missions, coverage, fabric_capacity, scenarios, world_scenarios

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("bff")

app = FastAPI(title="Capital Markets Client Intelligence BFF", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STORY_FILE = Path(__file__).with_name("story.json")


class ChatRequest(BaseModel):
    question: str
    threadId: str | None = None


class ProFormaRequest(BaseModel):
    """Incremental COMMITTED capacity at the client level, in CAD millions.

    Not the firm's own hold: the covenant tests the borrower's total net debt,
    so the syndicate-level number is the one that moves it.
    """

    incrementalM: float = 0.0
    ebitdaShockPct: float = 0.0


class OutreachItem(BaseModel):
    id: str
    channel: str | None = None
    slot: str | None = None


class OutreachApproval(BaseModel):
    items: list[OutreachItem]


class WrapupRequest(BaseModel):
    agreed: list[str] | None = None
    notes: str = ""


class PapersRequest(BaseModel):
    """Inputs for the approval-paper drafts. Hold sizes default to pro-rata."""

    incrementalM: float = 150.0
    holdM: float | None = None
    finalHoldM: float | None = None


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "mockMode": settings.mock_mode,
        "authConfigured": settings.configured(),
        "agentConfigured": settings.agent_configured(),
        "agent": settings.agent_name,
    }


@app.get("/api/config")
async def config() -> dict:
    """Bootstrap values for the SPA. Deliberately contains no secrets."""
    return {
        "tenantId": settings.tenant_id,
        "apiScope": settings.api_scope,
        "agentName": settings.agent_name,
        "mockMode": settings.mock_mode,
        "bank": "The Bank",
        "disclaimer": (
            "SYNTHETIC DEMO DATA. The Bank is a fictional institution. "
            "No client relationship, exposure, limit, revenue or policy shown here "
            "reflects any real bank's information. Gibson Energy Inc., Keyera Corp. and "
            "the other TSX-listed issuers named here are real public companies, "
            "named only so that live web grounding returns genuine public news; "
            "every internal figure is invented."
        ),
    }


@app.get("/api/me")
async def me(user: User = Depends(current_user)) -> dict:
    """The signed-in user, enriched from Microsoft Graph.

    The token carries name and roles but not jobTitle or department, so those are
    fetched from Graph on the user's behalf. The four demo personas already have
    those fields set in Entra, which is what lets the persona card show the real
    person rather than a hardcoded one.
    """
    roles = user.claims.get("roles") or []
    if isinstance(roles, str):
        roles = [roles]

    profile = {
        "name": user.name,
        "upn": user.upn,
        "oid": user.oid,
        "roles": roles,
        "role": roles[0] if roles else "",
        "jobTitle": "",
        "department": "",
    }

    if settings.mock_mode:
        profile.update({"jobTitle": "Coverage Banker (mock)",
                         "department": "Capital Markets"})
        return profile

    # Graph enrichment is best-effort: a failure here must not block the app.
    try:
        import httpx

        token = await exchange_obo(user, "https://graph.microsoft.com/.default")
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(
                "https://graph.microsoft.com/v1.0/me"
                "?$select=displayName,jobTitle,department,mail",
                headers={"Authorization": f"Bearer {token}"},
            )
        if r.status_code == 200:
            g = r.json()
            profile["jobTitle"] = g.get("jobTitle") or ""
            profile["department"] = g.get("department") or ""
            if g.get("displayName"):
                profile["name"] = g["displayName"]
        else:
            logger.info("graph /me returned %s", r.status_code)
    except Exception as exc:  # noqa: BLE001
        logger.info("graph enrichment skipped: %s", str(exc)[:200])

    return profile


@app.get("/api/iqs")
async def iqs() -> list[dict]:
    return iq_catalogue()


@app.get("/api/story")
async def story() -> dict:
    if not STORY_FILE.exists():
        return {"chapters": []}
    return json.loads(STORY_FILE.read_text(encoding="utf-8"))


@app.get("/api/metrics/agent")
async def agent_metrics(user: User = Depends(current_user)) -> dict:
    """Token consumption, latency and cost for chapter 12.

    Read from the Foundry project's own gen-AI traces in Application Insights,
    not from anything this process counted. Authenticated for the same reason
    /api/skills is: the layer breakdown says which grounded sources questions
    reached. It carries no question text.
    """
    return await telemetry_snapshot()


@app.get("/api/skills")
async def skills_catalogue(user: User = Depends(current_user)) -> dict:
    """Everything the chat skill bar needs to render its artifacts.

    Authenticated deliberately. The room card carries limit, covenant and
    restricted-list information, which CP-014 makes confidential and CP-008
    makes access-controlled - so it is not served to an anonymous caller even
    though the underlying figures are synthetic.
    """
    return skill_catalogue()


@app.post("/api/skills/proforma")
async def skills_proforma(
    req: ProFormaRequest, user: User = Depends(current_user),
) -> dict:
    """Run the CP-005 pro-forma covenant test.

    Deliberately a server-side calculation the UI cannot override: CP-005 makes
    this a control that must be able to return "no", and coverage "may not
    perform it, waive it, or pre-empt it".
    """
    result = run_proforma(req.incrementalM, req.ebitdaShockPct)
    return {**result, "verdict": proforma_verdict(result)}


@app.post("/api/skills/papers")
async def skills_papers(req: PapersRequest, user: User = Depends(current_user)) -> dict:
    """Draft Credit Committee, Portfolio Management and Control Room papers."""
    return build_papers(req.incrementalM, req.holdM, req.finalHoldM)


@app.post("/api/skills/papers/docx")
async def skills_papers_docx(req: PapersRequest, which: str = "all",
                             user: User = Depends(current_user)) -> Response:
    if which not in ("all", "cc", "pm", "cr"):
        raise HTTPException(status_code=400, detail="which must be all, cc, pm or cr")
    bundle = build_papers(req.incrementalM, req.holdM, req.finalHoldM)
    name = {"all": "approval-papers", "cc": "credit-committee-submission",
            "pm": "portfolio-management-plan", "cr": "control-room-request"}[which]
    return Response(
        content=papers_docx(bundle, which),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition":
                 f'attachment; filename="DRAFT-{name}-{bundle["as_of"]}.docx"'},
    )


@app.get("/api/web-pulse")
async def web_pulse_endpoint(refresh: bool = False,
                             user: User = Depends(current_user)) -> dict:
    """Live Web IQ headlines for the four-layer slide, cached server-side."""
    return await web_pulse(user, refresh=refresh)


@app.get("/api/fabric-capacity")
async def fabric_capacity_status(user: User = Depends(current_user)) -> dict:
    """State of the Fabric capacity behind Fabric IQ (Active / Paused / ...)."""
    return await fabric_capacity.status(user.upn)


@app.post("/api/fabric-capacity/{action}")
async def fabric_capacity_change(action: str, user: User = Depends(current_user)) -> dict:
    """Pause (suspend) or resume the capacity. Logged with the caller's UPN."""
    try:
        return await fabric_capacity.change(action, user.upn)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/skills/client/{client_id}/stress")
async def client_stress(client_id: str, user: User = Depends(current_user)) -> dict:
    """EBITDA stress across a company's EBITDA-linked covenants."""
    try:
        return client_skills.stress(client_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/skills/client/{client_id}/papers")
async def client_papers(client_id: str, user: User = Depends(current_user)) -> dict:
    """Draft credit papers for a company (Gibson: the deal papers)."""
    try:
        return client_skills.papers(client_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/skills/client/{client_id}/papers/docx")
async def client_papers_docx(client_id: str, which: str = "all",
                             user: User = Depends(current_user)) -> Response:
    if which not in ("all", "cc", "pm", "cr"):
        raise HTTPException(status_code=400, detail="which must be all, cc, pm or cr")
    try:
        bundle = client_skills.papers(client_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=papers_docx(bundle, which),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition":
                 f'attachment; filename="DRAFT-{client_id}-{which}-{bundle["as_of"]}.docx"'},
    )


# --------------------------------------------------------------------------- #
# Coverage workflow: overview -> triage -> outreach -> workspace -> guardrails
# -> call assist -> wrap-up. Deterministic from governed figures; see coverage.py.
# --------------------------------------------------------------------------- #

def _client_or_404(fn, *args):
    try:
        return fn(*args)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown client {exc}") from exc


@app.get("/api/coverage/overview")
async def coverage_overview(user: User = Depends(current_user)) -> dict:
    return coverage.overview()


@app.get("/api/coverage/triage")
async def coverage_triage(user: User = Depends(current_user)) -> dict:
    return coverage.triage()


@app.get("/api/coverage/outreach")
async def coverage_outreach(user: User = Depends(current_user)) -> dict:
    return coverage.outreach()


@app.post("/api/coverage/outreach/approve")
async def coverage_outreach_approve(req: OutreachApproval, user: User = Depends(current_user)) -> dict:
    return coverage.approve_outreach([i.model_dump() for i in req.items], user.upn)


@app.get("/api/coverage/client/{client_id}")
async def coverage_workspace(client_id: str, user: User = Depends(current_user)) -> dict:
    return _client_or_404(coverage.workspace, client_id)


@app.get("/api/coverage/client/{client_id}/guardrails")
async def coverage_guardrails(client_id: str, user: User = Depends(current_user)) -> dict:
    return _client_or_404(coverage.guardrails, client_id)


@app.post("/api/coverage/client/{client_id}/guardrails/approve")
async def coverage_guardrails_approve(client_id: str, user: User = Depends(current_user)) -> dict:
    return _client_or_404(coverage.approve_guardrails, client_id, user.upn)


@app.get("/api/coverage/client/{client_id}/call")
async def coverage_call(client_id: str, user: User = Depends(current_user)) -> dict:
    return _client_or_404(coverage.call_script, client_id)


@app.post("/api/coverage/client/{client_id}/wrapup")
async def coverage_wrapup(client_id: str, req: WrapupRequest, user: User = Depends(current_user)) -> dict:
    return _client_or_404(coverage.wrapup, client_id, req.agreed, req.notes, user.upn)


@app.post("/api/coverage/client/{client_id}/wrapup/docx")
async def coverage_wrapup_docx(client_id: str, req: WrapupRequest,
                               user: User = Depends(current_user)) -> Response:
    bundle = _client_or_404(coverage.wrapup, client_id, req.agreed, req.notes, user.upn)
    return Response(
        content=coverage.memo_docx(bundle),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition":
                 f'attachment; filename="DRAFT-coverage-memo-{client_id}.docx"'},
    )


@app.post("/api/coverage/client/{client_id}/wrapup/outlook-draft")
async def coverage_outlook_draft(client_id: str, req: WrapupRequest,
                                 user: User = Depends(current_user)) -> dict:
    """Save the follow-up email as a DRAFT in the signed-in user's own Outlook.

    Delegated Mail.ReadWrite On-Behalf-Of the user. No recipient is set and nothing
    is sent: the banker adds the client contact and sends from Outlook.
    """
    import html

    import httpx

    bundle = _client_or_404(coverage.wrapup, client_id, req.agreed, req.notes, user.upn)
    email = bundle["email"]
    body = "".join(f"<p>{html.escape(p).replace(chr(10), '<br/>')}</p>"
                   for p in email["body"].split("\n\n"))
    try:
        token = await exchange_obo(user, "https://graph.microsoft.com/.default")
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://graph.microsoft.com/v1.0/me/messages",
                headers={"Authorization": f"Bearer {token}"},
                json={"subject": email["subject"], "isDraft": True,
                      "body": {"contentType": "HTML", "content": body},
                      "toRecipients": []},
            )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Graph call failed: {str(exc)[:200]}") from exc
    if r.status_code not in (200, 201):
        logger.warning("outlook draft %s: %s", r.status_code, r.text[:300])
        raise HTTPException(status_code=502, detail=f"Graph {r.status_code}: {r.text[:200]}")
    d = r.json()
    logger.info("AUDIT outlook draft created by %s for %s", user.upn, client_id)
    return {"saved": True, "subject": d.get("subject"), "webLink": d.get("webLink", ""),
            "note": "Saved to your Outlook Drafts - no recipient set, nothing sent."}


@app.get("/api/scenarios/library")
async def scenarios_library(user: User = Depends(current_user)) -> dict:
    """Factors (with ranges), presets and the valuation assumptions."""
    return scenarios.library()


class ScenarioRequest(BaseModel):
    factors: dict[str, float] = {}
    name: str = "Custom"
    worldId: str | None = None


@app.get("/api/scenarios/world")
async def scenarios_world(refresh: bool = False, cached: bool = False,
                          user: User = Depends(current_user)) -> dict:
    """World-event presets scaled by today's Web IQ severity (cached; ?refresh=true re-queries)."""
    return world_scenarios.cached() if cached else await world_scenarios.world(user, refresh=refresh)


@app.post("/api/scenarios/run")
async def scenarios_run(req: ScenarioRequest, user: User = Depends(current_user)) -> dict:
    """Deterministic scenario run: covenants, ratings and relationship value per client."""
    return scenarios.run(req.factors, req.name[:60])


def _world_context(world_id: str | None) -> str:
    """Public Web IQ context for a world-event run, from the shared cache only."""
    if not world_id:
        return ""
    w = world_scenarios.cached()
    if world_id.startswith("emerging:"):
        e = next((x for x in w.get("emerging") or [] if f"emerging:{x['title']}" == world_id), None)
        if not e:
            return ""
        return (f"Emerging risk (live Web IQ, public web, {e['date'] or 'recent'}, {e['source'] or 'web'}): {e['title']} - "
                f"{e['headline']} This is NOT a governed scenario: it is approximated with the governed "
                f"'{e['closest_name']}' shock at '{e['severity']}' severity. Say so plainly in the brief and recommend "
                f"whether the Credit & Markets Committee should add it to the governed scenario library.")
    t = next((x for x in w["themes"] if x["id"] == world_id), None)
    if not t:
        return ""
    if not t["live"]:
        return f"World-event theme: {t['name']} at governed baseline severity (live Web IQ not available)."
    return (f"World-event theme: {t['name']}. Live Web IQ (public web, {t['date'] or 'recent'}, {t['source'] or 'web'}): "
            f"{t['headline']} Assessed severity '{t['severity']}', so the governed preset shock is scaled x{t['intensity']}. "
            f"Transmission: {t['channels']}")


@app.post("/api/scenarios/narrate")
async def scenarios_narrate(req: ScenarioRequest, user: User = Depends(current_user)) -> StreamingResponse:
    """Stream the Scenario Analyst agent's committee brief for one run.

    The engine figures are computed here and handed to the agent as given; the agent
    verifies the positions in Fabric IQ and grounds the policy angle in Foundry IQ.
    """
    result = scenarios.run(req.factors, req.name[:60])
    logger.info("AUDIT scenario narrate by %s: %s %s", user.upn, result["name"], result["factors"])
    return StreamingResponse(
        run_agent(user, scenarios.narrative_prompt(result, _world_context(req.worldId)), None,
                  settings.scenario_agent_name),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# --------------------------------------------------------------------------- #
# Agent missions - Dashboard actions that need an agent, run through a visible harness
# --------------------------------------------------------------------------- #
class MissionRun(BaseModel):
    clientId: str


class MissionDecision(BaseModel):
    runId: str
    clientId: str
    decision: str
    note: str = ""
    guardrails: str = ""
    review: str = ""
    rulesFlag: str = ""
    rulesReason: str = ""


def _mission_args(kind: str, client_id: str) -> None:
    if kind not in cm_missions.KINDS:
        raise HTTPException(status_code=404, detail=f"Unknown mission {kind}")
    if client_id not in cm_missions.CLIENTS:
        raise HTTPException(status_code=404, detail=f"Unknown client {client_id}")


@app.get("/api/missions/board")
async def missions_board(user: User = Depends(current_user)) -> dict:
    """Each business line's stance per client, and whether the lines disagree (Fabric IQ line_positions)."""
    return cm_missions.board()


@app.get("/api/missions/stats")
async def missions_stats(user: User = Depends(current_user)) -> dict:
    return await cm_missions.stats()


@app.get("/api/missions/evidence/{client_id}")
async def missions_evidence(client_id: str, user: User = Depends(current_user)) -> dict:
    """The latest live retrieval for this client, by IQ layer (from the last mission run on this replica)."""
    if client_id not in cm_missions.CLIENTS:
        raise HTTPException(status_code=404, detail=f"Unknown client {client_id}")
    return cm_missions.evidence(client_id) or {"clientId": client_id, "layers": None}


@app.get("/api/missions/{kind}/{client_id}")
async def missions_get(kind: str, client_id: str, user: User = Depends(current_user)) -> dict:
    _mission_args(kind, client_id)
    return cm_missions.mission(kind, client_id)


@app.post("/api/missions/{kind}/run")
async def missions_run(kind: str, req: MissionRun, user: User = Depends(current_user)) -> StreamingResponse:
    _mission_args(kind, req.clientId)
    return StreamingResponse(cm_missions.run(user, kind, req.clientId), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})


@app.post("/api/missions/{kind}/decision")
async def missions_decide(kind: str, req: MissionDecision, user: User = Depends(current_user)) -> dict:
    _mission_args(kind, req.clientId)
    if req.decision not in ("approve", "send_back", "escalate"):
        raise HTTPException(status_code=400, detail="decision must be approve, send_back or escalate")
    try:
        return cm_missions.decide(user, kind, req.clientId, req.runId, req.decision, req.note, req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/chat")
async def chat(req: ChatRequest, user: User = Depends(current_user)) -> StreamingResponse:
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question must not be empty.")
    logger.info("chat from %s: %s", user.upn, req.question[:120])
    return StreamingResponse(
        run_agent(user, req.question, req.threadId),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # stop nginx buffering the stream
        },
    )


@app.get("/api/diag")
async def diag(user: User = Depends(current_user)) -> dict:
    """Walk the chain end to end and report exactly where it breaks.

    Ordered so the first failure is the actionable one: token -> OBO -> agent.
    """
    out: dict = {
        "user": {"name": user.name, "upn": user.upn},
        "settings": {
            "tenantConfigured": bool(settings.tenant_id),
            "secretConfigured": bool(settings.client_secret),
            "projectEndpoint": (settings.project_endpoint if not settings.project_config_error()
                                else "(invalid)" if settings.project_endpoint else "(unset)"),
            "projectConfigured": not settings.project_config_error(),
            "agentName": settings.agent_name,
            "mockMode": settings.mock_mode,
        },
        "checks": [],
    }

    def add(name: str, ok: bool, detail: str = "") -> None:
        out["checks"].append({"check": name, "ok": ok, "detail": detail})

    add("token validated", True, f"scopes: {user.claims.get('scp', '')}")

    if settings.mock_mode:
        add("mock mode", True, "Azure calls are bypassed.")
        return out

    error = settings.agent_config_error()
    if error:
        add("agent configuration", False, error)
        return out

    try:
        token = await exchange_obo(user)
        add("on-behalf-of exchange", True, f"scope {settings.foundry_scope}")
    except Exception as exc:  # noqa: BLE001
        add("on-behalf-of exchange", False, str(getattr(exc, "detail", exc))[:500])
        return out

    # Confirm the agent exists on the v2 (prompt agent) surface. The older
    # assistants API does not list portal-created agents at all.
    try:
        import httpx

        base = settings.project_endpoint.rstrip("/")
        async with httpx.AsyncClient(timeout=45) as client:
            r = await client.get(
                f"{base}/agents/{quote(settings.agent_name, safe='')}?api-version=v1",
                headers={"Authorization": f"Bearer {token}"},
            )
        if r.status_code == 200:
            body = r.json()
            ver = body.get("versions", {}).get("latest", {})
            tools = [t.get("type") for t in ver.get("definition", {}).get("tools", [])]
            add("agent found", True,
                f"version {ver.get('version', '?')} · model "
                f"{ver.get('definition', {}).get('model', '?')} · tools: "
                f"{', '.join(t for t in tools if t) or 'none listed'}")
        else:
            add("agent found", False, f"{r.status_code}: {r.text[:400]}")
    except Exception as exc:  # noqa: BLE001
        add("agent found", False, str(exc)[:400])

    return out


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):  # noqa: ANN201
    logger.exception("unhandled error on %s", request.url.path)
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=500, content={"detail": str(exc)[:500]})
