"""Deploy the Capital Markets Client Intelligence dataset into Microsoft Fabric.

Creates, end to end and idempotently:

  1. workspace   ws-capital-markets-client-intel  (bound to a named capacity)
  2. lakehouse   lh_client_intel
  3. OneLake     Files/client-intel/*.csv         (the ten synthetic CSVs)
  4. notebook    nb_load_client_intel             (10 Delta tables + curated views)
  5. semantic    sm_client_intel                  Direct Lake model with the
     model                                        relationships and measures the
                                                  agent's Fabric IQ tool queries

SYNTHETIC DEMO DATA. BMO Capital Markets is a branding label only. Gibson Energy
Inc. is a real public company used only so the Web IQ layer's live grounding
returns genuine public news; every exposure, limit, revenue, rating and covenant
loaded here is invented for a demo.

Auth uses the Azure CLI login (`az login`) - no secrets. The signed-in user must
be a Fabric workspace creator and an admin/contributor on the target capacity.

    python deploy_fabric.py --capacity fabcap26
    python deploy_fabric.py --capacity fabcap26 --only semantic-model
    python deploy_fabric.py --status
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests

HERE = Path(__file__).parent

FABRIC_API = "https://api.fabric.microsoft.com/v1"
ONELAKE_DFS = "https://onelake.dfs.fabric.microsoft.com"

WORKSPACE = "ws-capital-markets-client-intel"
LAKEHOUSE = "lh_client_intel"
NOTEBOOK = "nb_load_client_intel"
SEMANTIC_NOTEBOOK = "nb_create_semantic_model"
SEMANTIC_MODEL = "sm_client_intel"

WORKSPACE_DESC = (
    "SYNTHETIC DEMO DATA - Capital Markets Client Intelligence. BMO Capital Markets "
    "is used only as a branding label. Gibson Energy Inc. and the other issuers are "
    "real public companies, referenced only so live web grounding returns real public "
    "news; every exposure, limit, revenue, wallet share, rating, covenant and policy "
    "here is invented for a demo. Do not use for any operational or reporting purpose."
)

CSVS = [
    "clients.csv",
    "coverage_team.csv",
    "credit_facilities.csv",
    "exposures.csv",
    "limits_utilization.csv",
    "revenue_by_product.csv",
    "wallet_share.csv",
    "trades.csv",
    "covenants.csv",
    "risk_ratings.csv",
]


# --------------------------------------------------------------------------- #
# auth
# --------------------------------------------------------------------------- #
def token(resource: str) -> str:
    out = subprocess.run(
        ["az", "account", "get-access-token", "--resource", resource,
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=True,
    )
    if out.returncode != 0:
        sys.exit(f"az token failed for {resource}: {out.stderr}")
    return out.stdout.strip()


class Api:
    def __init__(self, resource: str, base: str):
        self._resource, self.base = resource, base
        self._tok, self._at = "", 0.0

    def h(self, extra: dict | None = None) -> dict:
        if time.time() - self._at > 1800:
            self._tok, self._at = token(self._resource), time.time()
        head = {"Authorization": f"Bearer {self._tok}"}
        head.update(extra or {})
        return head

    def call(self, method: str, path: str, *, json_body: Any = None,
             data: bytes | None = None, headers: dict | None = None,
             params: dict | None = None, ok: tuple[int, ...] = (200, 201, 202)) -> Any:
        url = path if path.startswith("http") else f"{self.base}{path}"
        r = requests.request(method, url, headers=self.h(headers),
                             json=json_body, data=data, params=params, timeout=180)
        if r.status_code == 202 and "Location" in r.headers:
            return self._poll(r)
        if r.status_code not in ok:
            raise RuntimeError(f"{method} {url} -> {r.status_code}: {r.text[:900]}")
        return r.json() if r.content and "json" in r.headers.get("Content-Type", "") else None

    def _poll(self, resp) -> Any:
        loc = resp.headers["Location"]
        for _ in range(120):
            time.sleep(int(resp.headers.get("Retry-After", 5)))
            p = requests.get(loc, headers=self.h(), timeout=120)
            if p.status_code in (200, 201):
                body = p.json() if p.content else {}
                state = body.get("status")
                if state in (None, "Succeeded"):
                    if body.get("status") == "Succeeded":
                        res = requests.get(f"{loc}/result", headers=self.h(), timeout=120)
                        return res.json() if res.status_code == 200 and res.content else body
                    return body
                if state in ("Failed", "Undefined"):
                    raise RuntimeError(f"LRO failed: {json.dumps(body)[:900]}")
            resp.headers["Retry-After"] = "5"
        raise RuntimeError("LRO timed out")


fab = Api("https://api.fabric.microsoft.com", FABRIC_API)
lake = Api("https://storage.azure.com", ONELAKE_DFS)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def find(items: list[dict], name: str, key: str = "displayName") -> dict | None:
    return next((i for i in items if i.get(key) == name), None)


def get_workspace() -> dict | None:
    return find(fab.call("GET", "/workspaces")["value"], WORKSPACE)


def get_item(ws_id: str, name: str, item_type: str) -> dict | None:
    items = fab.call("GET", f"/workspaces/{ws_id}/items",
                     params={"type": item_type})["value"]
    return find(items, name)


# --------------------------------------------------------------------------- #
# 1. workspace
# --------------------------------------------------------------------------- #
def ensure_workspace(capacity_name: str) -> str:
    ws = get_workspace()
    if ws:
        print(f"= workspace {WORKSPACE} ({ws['id']})")
        ws_id = ws["id"]
    else:
        ws = fab.call("POST", "/workspaces",
                      json_body={"displayName": WORKSPACE, "description": WORKSPACE_DESC})
        ws_id = ws["id"]
        print(f"+ workspace {WORKSPACE} ({ws_id})")

    caps = fab.call("GET", "/capacities")["value"]
    cap = find(caps, capacity_name)
    if not cap:
        sys.exit(f"capacity '{capacity_name}' not found. Available: "
                 + ", ".join(c["displayName"] for c in caps))
    if cap.get("state") != "Active":
        sys.exit(f"capacity '{capacity_name}' is {cap.get('state')} - resume it first")

    current = fab.call("GET", f"/workspaces/{ws_id}").get("capacityId")
    if (current or "").lower() != cap["id"].lower():
        fab.call("POST", f"/workspaces/{ws_id}/assignToCapacity",
                 json_body={"capacityId": cap["id"]}, ok=(200, 202))
        print(f"  assigned to capacity {capacity_name} ({cap['sku']}, {cap['region']})")
    else:
        print(f"  already on capacity {capacity_name} ({cap['sku']})")
    return ws_id


# --------------------------------------------------------------------------- #
# 2. lakehouse
# --------------------------------------------------------------------------- #
def ensure_lakehouse(ws_id: str) -> dict:
    lh = get_item(ws_id, LAKEHOUSE, "Lakehouse")
    if not lh:
        fab.call("POST", f"/workspaces/{ws_id}/lakehouses",
                 json_body={"displayName": LAKEHOUSE,
                            "description": "SYNTHETIC DEMO DATA - Capital Markets client intelligence dataset."})
        for _ in range(30):
            time.sleep(4)
            lh = get_item(ws_id, LAKEHOUSE, "Lakehouse")
            if lh:
                break
        print(f"+ lakehouse {LAKEHOUSE} ({lh['id']})")
    else:
        print(f"= lakehouse {LAKEHOUSE} ({lh['id']})")

    detail = fab.call("GET", f"/workspaces/{ws_id}/lakehouses/{lh['id']}")
    return detail or lh


# --------------------------------------------------------------------------- #
# 3. OneLake upload
# --------------------------------------------------------------------------- #
def upload_csvs(ws_id: str, lh_id: str) -> None:
    print("  uploading CSVs to Files/client-intel/")
    for name in CSVS:
        content = (HERE / name).read_bytes()
        path = f"/{ws_id}/{lh_id}/Files/client-intel/{name}"
        lake.call("PUT", f"{ONELAKE_DFS}{path}", params={"resource": "file"},
                  ok=(201, 202))
        lake.call("PATCH", f"{ONELAKE_DFS}{path}",
                  params={"action": "append", "position": "0"},
                  data=content,
                  headers={"Content-Type": "application/octet-stream"},
                  ok=(202,))
        lake.call("PATCH", f"{ONELAKE_DFS}{path}",
                  params={"action": "flush", "position": str(len(content))},
                  ok=(200,))
        print(f"    {name:<26} {len(content):>7,} bytes")


# --------------------------------------------------------------------------- #
# 4. notebook
# --------------------------------------------------------------------------- #
def notebook_payload(ws_id: str, lh_id: str, source: str) -> str:
    code = (HERE / source).read_text(encoding="utf-8")
    # %pip magics must sit in their own cell and run first
    lines = code.splitlines(keepends=True)
    magic, body, cells = [], [], []
    for ln in lines:
        if ln.startswith("# MAGIC %"):
            magic.append(ln.replace("# MAGIC ", "", 1))
        else:
            body.append(ln)
    if magic:
        cells.append({"cell_type": "code", "source": magic,
                      "execution_count": None, "outputs": [], "metadata": {}})
    cells.append({"cell_type": "code", "source": body,
                  "execution_count": None, "outputs": [], "metadata": {}})

    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "cells": cells,
        "metadata": {
            "language_info": {"name": "python"},
            "dependencies": {
                "lakehouse": {
                    "default_lakehouse": lh_id,
                    "default_lakehouse_name": LAKEHOUSE,
                    "default_lakehouse_workspace_id": ws_id,
                }
            },
        },
    }
    return base64.b64encode(json.dumps(nb).encode()).decode()


def ensure_notebook(ws_id: str, lh_id: str, name: str, source: str,
                    description: str) -> str:
    payload = notebook_payload(ws_id, lh_id, source)
    definition = {"format": "ipynb",
                  "parts": [{"path": "notebook-content.ipynb",
                             "payload": payload, "payloadType": "InlineBase64"}]}
    nb = get_item(ws_id, name, "Notebook")
    if nb:
        fab.call("POST", f"/workspaces/{ws_id}/notebooks/{nb['id']}/updateDefinition",
                 json_body={"definition": definition}, ok=(200, 202))
        print(f"= notebook {name} ({nb['id']}) definition updated")
        return nb["id"]
    created = fab.call("POST", f"/workspaces/{ws_id}/notebooks",
                       json_body={"displayName": name, "description": description,
                                  "definition": definition})
    nb_id = (created or {}).get("id")
    if not nb_id:
        for _ in range(30):
            time.sleep(4)
            nb = get_item(ws_id, name, "Notebook")
            if nb:
                nb_id = nb["id"]
                break
    print(f"+ notebook {name} ({nb_id})")
    return nb_id


def run_notebook(ws_id: str, nb_id: str) -> None:
    print("  running notebook (Spark session start can take 2-4 minutes)…")
    r = requests.post(
        f"{FABRIC_API}/workspaces/{ws_id}/items/{nb_id}/jobs/instances",
        headers=fab.h({"Content-Type": "application/json"}),
        params={"jobType": "RunNotebook"}, json={}, timeout=120,
    )
    if r.status_code not in (200, 201, 202):
        raise RuntimeError(f"job start -> {r.status_code}: {r.text[:900]}")
    loc = r.headers.get("Location")
    if not loc:
        print("  (no job location returned; check the notebook run in the portal)")
        return
    for i in range(160):
        time.sleep(15)
        s = requests.get(loc, headers=fab.h(), timeout=60)
        if s.status_code != 200:
            continue
        st = s.json().get("status")
        if i % 4 == 0:
            print(f"    [{i*15:>4}s] {st}")
        if st in ("Completed", "Succeeded"):
            print("  notebook completed")
            return
        if st in ("Failed", "Cancelled", "Deduped"):
            raise RuntimeError(f"notebook run {st}: {json.dumps(s.json())[:900]}")
    raise RuntimeError("notebook run timed out")


# --------------------------------------------------------------------------- #
# 5. semantic model (Direct Lake)
# --------------------------------------------------------------------------- #
def read_log(ws_id: str, lh_id: str,
             path: str = "Files/_deploy/semantic_model_log.txt") -> None:
    """Notebook job failures are opaque from the REST API - the notebooks write a
    full traceback into OneLake, so print it here."""
    url = f"{ONELAKE_DFS}/{ws_id}/{lh_id}/{path}"
    r = requests.get(url, headers=lake.h(), timeout=60)
    if r.status_code != 200:
        print(f"  (no log at {path}: {r.status_code})")
        return
    print("---- notebook log " + "-" * 58)
    text = r.content.decode("utf-8", errors="replace")
    # strip pip's ANSI/box-drawing progress art and anything the console codec
    # cannot render (Windows consoles default to cp1252)
    text = re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", text)
    enc = sys.stdout.encoding or "utf-8"
    print(text.encode(enc, errors="replace").decode(enc))
    print("-" * 76)


def ensure_semantic_model(ws_id: str, lh_id: str) -> None:
    """Build the Direct Lake model by running a notebook that uses semantic-link-labs.

    Writing TMDL by hand over the REST API is brittle across Fabric releases; the
    in-notebook path uses the supported library and runs with the workspace's own
    identity and context.
    """
    nb_id = ensure_notebook(
        ws_id, lh_id, SEMANTIC_NOTEBOOK, "create_semantic_model_fabric.py",
        "Builds the Direct Lake semantic model and its business measures.",
    )
    try:
        run_notebook(ws_id, nb_id)
    finally:
        read_log(ws_id, lh_id)
    sm = get_item(ws_id, SEMANTIC_MODEL, "SemanticModel")
    print(f"  semantic model {SEMANTIC_MODEL}: {'created ' + sm['id'] if sm else 'NOT FOUND'}")


# --------------------------------------------------------------------------- #
def sql_endpoint(lh: dict) -> tuple[str, str]:
    props = lh.get("properties", {}).get("sqlEndpointProperties", {})
    return props.get("connectionString", ""), props.get("id", "")


def status() -> None:
    ws = get_workspace()
    if not ws:
        print(f"workspace {WORKSPACE}: NOT CREATED")
        return
    print(f"workspace  {WORKSPACE}  {ws['id']}")
    items = fab.call("GET", f"/workspaces/{ws['id']}/items")["value"]
    for i in sorted(items, key=lambda x: (x["type"], x["displayName"])):
        print(f"  {i['type']:<16} {i['displayName']}")
    lh = get_item(ws["id"], LAKEHOUSE, "Lakehouse")
    if lh:
        detail = fab.call("GET", f"/workspaces/{ws['id']}/lakehouses/{lh['id']}")
        server, db = sql_endpoint(detail)
        print(f"\nFABRIC_SQL_ENDPOINT = {server}")
        print(f"FABRIC_DATABASE     = {LAKEHOUSE}")
        print(f"sql endpoint id     = {db}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capacity", default="fabcap26")
    ap.add_argument("--only", choices=["workspace", "lakehouse", "upload",
                                       "notebook", "semantic-model"])
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--skip-run", action="store_true",
                    help="create the notebook but do not execute it")
    args = ap.parse_args()

    if args.status:
        status()
        return

    steps = [args.only] if args.only else ["workspace", "lakehouse", "upload",
                                           "notebook", "semantic-model"]

    ws_id = ensure_workspace(args.capacity) if "workspace" in steps else \
        (get_workspace() or sys.exit("workspace not found - run --only workspace"))["id"]

    lh = None
    if any(s in steps for s in ("lakehouse", "upload", "notebook", "semantic-model")):
        lh = ensure_lakehouse(ws_id)

    if "upload" in steps:
        upload_csvs(ws_id, lh["id"])

    if "notebook" in steps:
        nb_id = ensure_notebook(ws_id, lh["id"], NOTEBOOK, "load_client_intel_fabric.py",
                                "Loads the client intelligence CSVs into Delta tables.")
        if not args.skip_run:
            run_notebook(ws_id, nb_id)

    if "semantic-model" in steps:
        ensure_semantic_model(ws_id, lh["id"])

    print()
    status()


if __name__ == "__main__":
    main()
