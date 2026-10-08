"""Deploy the Capital Markets Client Intelligence dataset into Microsoft Fabric.

Creates, end to end and idempotently:

  1. workspace   ws-capital-markets-client-intel  (bound to a named capacity)
  2. lakehouse   lh_client_intel
  3. OneLake     Files/client-intel/*.csv         (the ten synthetic CSVs)
  4. notebook    nb_load_client_intel             (10 Delta tables + curated views)
  5. semantic    sm_client_intel                  Direct Lake model with the
     model                                        relationships and measures the
                                                  agent's Fabric IQ tool queries

SYNTHETIC DEMO DATA. The Bank is a branding label only. Gibson Energy
Inc. is a real public company used only so the Web IQ layer's live grounding
returns genuine public news; every exposure, limit, revenue, rating and covenant
loaded here is invented for a demo.

Auth uses an existing Azure CLI session, explicitly bound to AZURE_TENANT_ID.
The signed-in user must
be a Fabric workspace creator and an admin/contributor on the target capacity.

    python deploy_fabric.py --capacity <capacity-name>
    python deploy_fabric.py --only semantic-model
    python deploy_fabric.py --status

Required env: AZURE_TENANT_ID, FABRIC_WORKSPACE_NAME, FABRIC_LAKEHOUSE_NAME.
Workspace creation/binding also requires FABRIC_CAPACITY_NAME or --capacity.
The notebook step requires FABRIC_LOAD_NOTEBOOK_NAME. The semantic-model step
requires FABRIC_SEMANTIC_NOTEBOOK_NAME and FABRIC_SEMANTIC_MODEL_NAME.
No environment is read and no credentials are constructed until main().
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

HERE = Path(__file__).parent

FABRIC_API = "https://api.fabric.microsoft.com/v1"
ONELAKE_DFS = "https://onelake.dfs.fabric.microsoft.com"

WORKSPACE_DESC = (
    "SYNTHETIC DEMO DATA - Capital Markets Client Intelligence. The Bank "
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
    "scenario_sensitivity.csv",
    "market_scenarios.csv",
    "line_positions.csv",
]


# --------------------------------------------------------------------------- #
# auth
# --------------------------------------------------------------------------- #
class ConfigurationError(ValueError):
    """Invalid deployment settings; no authentication or writes have occurred."""


def required(environ, name: str) -> str:
    value = environ.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{name} is required and must not be blank.")
    value = value.strip()
    if len(value) > 256 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ConfigurationError(f"{name} must be 1–256 characters without controls.")
    return value


class DeploymentConfig:
    def __init__(self, args, environ):
        self.tenant_id = required(environ, "AZURE_TENANT_ID")
        if not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", self.tenant_id) or not uuid.UUID(self.tenant_id).int:
            raise ConfigurationError("AZURE_TENANT_ID must be a nonzero tenant GUID.")
        self.workspace = required(environ, "FABRIC_WORKSPACE_NAME")
        self.lakehouse = required(environ, "FABRIC_LAKEHOUSE_NAME")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.lakehouse):
            raise ConfigurationError("FABRIC_LAKEHOUSE_NAME must be a Spark identifier (letters, digits, underscores).")
        self.steps = [] if args.status else ([args.only] if args.only else [
            "workspace", "lakehouse", "upload", "notebook", "semantic-model",
        ])
        self.capacity = None
        if "workspace" in self.steps:
            self.capacity = required(
                {"FABRIC_CAPACITY_NAME": args.capacity} if args.capacity is not None else environ,
                "FABRIC_CAPACITY_NAME",
            )
        notebook_step = any(step in self.steps for step in ("notebook", "semantic-model"))
        self.notebook = required(environ, "FABRIC_LOAD_NOTEBOOK_NAME") if (
            "notebook" in self.steps or (notebook_step and "FABRIC_LOAD_NOTEBOOK_NAME" in environ)
        ) else None
        self.semantic_notebook = required(environ, "FABRIC_SEMANTIC_NOTEBOOK_NAME") if (
            "semantic-model" in self.steps or (notebook_step and "FABRIC_SEMANTIC_NOTEBOOK_NAME" in environ)
        ) else None
        self.semantic_model = required(environ, "FABRIC_SEMANTIC_MODEL_NAME") if "semantic-model" in self.steps else None
        if self.notebook and self.semantic_notebook and self.notebook.casefold() == self.semantic_notebook.casefold():
            raise ConfigurationError("FABRIC_LOAD_NOTEBOOK_NAME and FABRIC_SEMANTIC_NOTEBOOK_NAME must be distinct.")

    def validate_inputs(self) -> None:
        needed = list(CSVS) if "upload" in self.steps else []
        if "notebook" in self.steps:
            needed.append("load_client_intel_fabric.py")
        if "semantic-model" in self.steps:
            needed.append("create_semantic_model_fabric.py")
        missing = [name for name in needed if not (HERE / name).is_file()]
        if missing:
            raise ConfigurationError(f"Missing deployment inputs in {HERE}: {', '.join(missing)}")


class Api:
    def __init__(self, resource: str, base: str, credential, requests):
        self._resource, self.base = resource, base
        self.credential, self.requests = credential, requests
        self._tok, self._at = "", 0.0

    def h(self, extra: dict | None = None) -> dict:
        if not self._tok or time.time() - self._at > 1800:
            self._tok = self.credential.get_token(f"{self._resource}/.default").token
            if not isinstance(self._tok, str) or not self._tok.strip():
                raise RuntimeError(f"Empty token returned for {self._resource}.")
            self._at = time.time()
        head = {"Authorization": f"Bearer {self._tok}"}
        head.update(extra or {})
        return head

    def call(self, method: str, path: str, *, json_body: Any = None,
             data: bytes | None = None, headers: dict | None = None,
             params: dict | None = None, ok: tuple[int, ...] = (200, 201, 202)) -> Any:
        url = self.url(path)
        r = self.requests.request(method, url, headers=self.h(headers),
                                  json=json_body, data=data, params=params, timeout=180,
                                  allow_redirects=False)
        if r.status_code == 202 and "Location" in r.headers:
            return self._poll(r)
        if r.status_code not in ok:
            raise RuntimeError(f"{method} {url} -> {r.status_code}: {r.text[:900]}")
        return r.json() if r.content and "json" in r.headers.get("Content-Type", "") else None

    def _poll(self, resp) -> Any:
        loc = self.url(resp.headers["Location"])
        for _ in range(120):
            time.sleep(int(resp.headers.get("Retry-After", 5)))
            p = self.requests.get(loc, headers=self.h(), timeout=120, allow_redirects=False)
            if p.status_code in (200, 201):
                body = p.json() if p.content else {}
                state = body.get("status")
                if state in (None, "Succeeded"):
                    if body.get("status") == "Succeeded":
                        res = self.requests.get(f"{loc}/result", headers=self.h(), timeout=120, allow_redirects=False)
                        if res.status_code != 200:
                            raise RuntimeError(f"LRO result -> {res.status_code}: {res.text[:900]}")
                        return res.json() if res.content else body
                    return body
                if state in ("Failed", "Undefined"):
                    raise RuntimeError(f"LRO failed: {json.dumps(body)[:900]}")
            elif p.status_code != 202:
                raise RuntimeError(f"LRO poll -> {p.status_code}: {p.text[:900]}")
            resp = p
        raise RuntimeError("LRO timed out")

    def url(self, path: str) -> str:
        url = f"{self.base}{path}" if path.startswith("/") and not path.startswith("//") else path
        parsed, base = urlsplit(url), urlsplit(self.base)
        if (
            parsed.scheme != "https" or parsed.netloc != base.netloc
            or not parsed.path.startswith(base.path + "/")
            or parsed.username or parsed.password or parsed.fragment
            or "\\" in url or any(c.isspace() for c in url)
        ):
            raise ValueError("Refusing to send credentials outside the configured Microsoft API.")
        return url

    def collection(self, path: str, **kwargs) -> list[dict]:
        values, seen = [], set()
        while path:
            if path in seen:
                raise RuntimeError("Fabric returned a repeated continuation URI.")
            seen.add(path)
            body = self.call("GET", path, **kwargs)
            values.extend(body["value"])
            path = body.get("continuationUri")
            if not path and body.get("continuationToken"):
                raise RuntimeError("Fabric returned a continuation token without its URI.")
            kwargs = {}
        return values


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def find(items: list[dict], name: str, key: str = "displayName") -> dict | None:
    matches = [i for i in items if i.get(key) == name]
    if len(matches) > 1:
        raise RuntimeError(f"Ambiguous {key} {name!r}; configure a unique resource name.")
    return matches[0] if matches else None


class FabricDeployment:
    def __init__(self, config: DeploymentConfig, credential, requests):
        self.config, self.requests = config, requests
        self.fab = Api("https://api.fabric.microsoft.com", FABRIC_API, credential, requests)
        self.lake = Api("https://storage.azure.com", ONELAKE_DFS, credential, requests)

    def get_workspace(self) -> dict | None:
        return find(self.fab.collection("/workspaces"), self.config.workspace)


    def get_item(self, ws_id: str, name: str, item_type: str) -> dict | None:
        items = self.fab.collection(f"/workspaces/{ws_id}/items", params={"type": item_type})
        return find(items, name)


    # --------------------------------------------------------------------------- #
    # 1. workspace
    # --------------------------------------------------------------------------- #
    def ensure_workspace(self, capacity_name: str) -> str:
        caps = self.fab.collection("/capacities")
        cap = find(caps, capacity_name)
        if not cap:
            raise RuntimeError(f"Configured capacity {capacity_name!r} was not found.")
        if cap.get("state") != "Active":
            raise RuntimeError(f"Capacity {capacity_name!r} is {cap.get('state')}; activate it before deployment.")
        ws = self.get_workspace()
        if ws:
            print(f"= workspace {self.config.workspace} ({ws['id']})")
            ws_id = ws["id"]
        else:
            ws = self.fab.call("POST", "/workspaces",
                          json_body={"displayName": self.config.workspace, "description": WORKSPACE_DESC})
            ws_id = ws["id"]
            print(f"+ workspace {self.config.workspace} ({ws_id})")

        current = self.fab.call("GET", f"/workspaces/{ws_id}").get("capacityId")
        if (current or "").lower() != cap["id"].lower():
            self.fab.call("POST", f"/workspaces/{ws_id}/assignToCapacity",
                     json_body={"capacityId": cap["id"]}, ok=(200, 202))
            print(f"  assigned to capacity {capacity_name} ({cap['sku']}, {cap['region']})")
        else:
            print(f"  already on capacity {capacity_name} ({cap['sku']})")
        return ws_id


    # --------------------------------------------------------------------------- #
    # 2. lakehouse
    # --------------------------------------------------------------------------- #
    def ensure_lakehouse(self, ws_id: str) -> dict:
        lh = self.get_item(ws_id, self.config.lakehouse, "Lakehouse")
        if not lh:
            self.fab.call("POST", f"/workspaces/{ws_id}/lakehouses",
                     json_body={"displayName": self.config.lakehouse,
                                "description": "SYNTHETIC DEMO DATA - Capital Markets client intelligence dataset."})
            for _ in range(30):
                time.sleep(4)
                lh = self.get_item(ws_id, self.config.lakehouse, "Lakehouse")
                if lh:
                    break
            if not lh:
                raise RuntimeError(f"Lakehouse {self.config.lakehouse!r} was not visible after creation.")
            print(f"+ lakehouse {self.config.lakehouse} ({lh['id']})")
        else:
            print(f"= lakehouse {self.config.lakehouse} ({lh['id']})")

        detail = self.fab.call("GET", f"/workspaces/{ws_id}/lakehouses/{lh['id']}")
        return detail or lh


    # --------------------------------------------------------------------------- #
    # 3. OneLake upload
    # --------------------------------------------------------------------------- #
    def upload_csvs(self, ws_id: str, lh_id: str) -> None:
        print("  uploading CSVs to Files/client-intel/")
        for name in CSVS:
            content = (HERE / name).read_bytes()
            path = f"/{ws_id}/{lh_id}/Files/client-intel/{name}"
            self.lake.call("PUT", f"{ONELAKE_DFS}{path}", params={"resource": "file"},
                      ok=(201, 202))
            self.lake.call("PATCH", f"{ONELAKE_DFS}{path}",
                      params={"action": "append", "position": "0"},
                      data=content,
                      headers={"Content-Type": "application/octet-stream"},
                      ok=(202,))
            self.lake.call("PATCH", f"{ONELAKE_DFS}{path}",
                      params={"action": "flush", "position": str(len(content))},
                      ok=(200,))
            print(f"    {name:<26} {len(content):>7,} bytes")


    # --------------------------------------------------------------------------- #
    # 4. notebook
    # --------------------------------------------------------------------------- #
    def notebook_payload(self, ws_id: str, lh_id: str, source: str) -> str:
        settings = {
            "FABRIC_WORKSPACE_ID": ws_id,
            "FABRIC_LAKEHOUSE_ID": lh_id,
            "FABRIC_LAKEHOUSE_NAME": self.config.lakehouse,
        }
        if source == "create_semantic_model_fabric.py":
            settings["FABRIC_SEMANTIC_MODEL_NAME"] = required(
                {"FABRIC_SEMANTIC_MODEL_NAME": self.config.semantic_model}, "FABRIC_SEMANTIC_MODEL_NAME"
            )
        elif source != "load_client_intel_fabric.py":
            raise ValueError("Only the two validated Fabric notebook sources can be deployed.")
        code = (HERE / source).read_text(encoding="utf-8")
        # Pass only non-secret, explicit settings; notebook jobs do not inherit
        # the deployment process's environment. Literal quoting prevents code injection.
        cells = [
            {"cell_type": "code",
             "source": ["import os\n", f"os.environ.update({settings!r})\n"],
             "execution_count": None, "outputs": [], "metadata": {}},
            {"cell_type": "code", "source": code.splitlines(keepends=True),
             "execution_count": None, "outputs": [], "metadata": {}},
        ]

        nb = {
            "nbformat": 4,
            "nbformat_minor": 5,
            "cells": cells,
            "metadata": {
                "language_info": {"name": "python"},
                "dependencies": {
                    "lakehouse": {
                        "default_lakehouse": lh_id,
                        "default_lakehouse_name": self.config.lakehouse,
                        "default_lakehouse_workspace_id": ws_id,
                    }
                },
            },
        }
        return base64.b64encode(json.dumps(nb).encode()).decode()


    def ensure_notebook(self, ws_id: str, lh_id: str, name: str, source: str,
                        description: str) -> str:
        payload = self.notebook_payload(ws_id, lh_id, source)
        definition = {"format": "ipynb",
                      "parts": [{"path": "notebook-content.ipynb",
                                 "payload": payload, "payloadType": "InlineBase64"}]}
        nb = self.get_item(ws_id, name, "Notebook")
        if nb:
            self.fab.call("POST", f"/workspaces/{ws_id}/notebooks/{nb['id']}/updateDefinition",
                     json_body={"definition": definition}, ok=(200, 202))
            print(f"= notebook {name} ({nb['id']}) definition updated")
            return nb["id"]
        created = self.fab.call("POST", f"/workspaces/{ws_id}/notebooks",
                           json_body={"displayName": name, "description": description,
                                      "definition": definition})
        nb_id = (created or {}).get("id")
        if not nb_id:
            for _ in range(30):
                time.sleep(4)
                nb = self.get_item(ws_id, name, "Notebook")
                if nb:
                    nb_id = nb["id"]
                    break
        if not nb_id:
            raise RuntimeError(f"Notebook {name!r} was not visible after creation.")
        print(f"+ notebook {name} ({nb_id})")
        return nb_id


    def run_notebook(self, ws_id: str, nb_id: str) -> None:
        print("  running notebook (Spark session start can take 2-4 minutes)…")
        r = self.requests.post(
            f"{FABRIC_API}/workspaces/{ws_id}/items/{nb_id}/jobs/instances",
            headers=self.fab.h({"Content-Type": "application/json"}),
            params={"jobType": "RunNotebook"}, json={}, timeout=120, allow_redirects=False,
        )
        if r.status_code not in (200, 201, 202):
            raise RuntimeError(f"job start -> {r.status_code}: {r.text[:900]}")
        loc = r.headers.get("Location")
        if not loc:
            raise RuntimeError("Notebook job returned no Location; completion cannot be verified.")
        loc = self.fab.url(loc)
        for i in range(160):
            time.sleep(15)
            s = self.requests.get(loc, headers=self.fab.h(), timeout=60, allow_redirects=False)
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
    def read_log(self, ws_id: str, lh_id: str,
                 path: str = "Files/_deploy/semantic_model_log.txt") -> None:
        """Notebook job failures are opaque from the REST API - the notebooks write a
        full traceback into OneLake, so print it here."""
        url = f"{ONELAKE_DFS}/{ws_id}/{lh_id}/{path}"
        r = self.requests.get(url, headers=self.lake.h(), timeout=60, allow_redirects=False)
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


    def ensure_semantic_model(self, ws_id: str, lh_id: str, skip_run: bool = False) -> None:
        """Build the Direct Lake model by running a notebook that uses semantic-link-labs.

        Writing TMDL by hand over the REST API is brittle across Fabric releases; the
        in-notebook path uses the supported library and runs with the workspace's own
        identity and context.
        """
        nb_id = self.ensure_notebook(
            ws_id, lh_id, self.config.semantic_notebook, "create_semantic_model_fabric.py",
            "Builds the Direct Lake semantic model and its business measures.",
        )
        if skip_run:
            return
        try:
            self.run_notebook(ws_id, nb_id)
        finally:
            self.read_log(ws_id, lh_id)
        sm = self.get_item(ws_id, self.config.semantic_model, "SemanticModel")
        if not sm:
            raise RuntimeError(f"Semantic model {self.config.semantic_model!r} was not found after notebook completion.")
        print(f"  semantic model {self.config.semantic_model}: created {sm['id']}")


    # --------------------------------------------------------------------------- #
    def sql_endpoint(self, lh: dict) -> tuple[str, str]:
        props = lh.get("properties", {}).get("sqlEndpointProperties", {})
        return props.get("connectionString", ""), props.get("id", "")


    def status(self) -> None:
        ws = self.get_workspace()
        if not ws:
            print(f"workspace {self.config.workspace}: NOT CREATED")
            return
        print(f"workspace  {self.config.workspace}  {ws['id']}")
        items = self.fab.collection(f"/workspaces/{ws['id']}/items")
        for i in sorted(items, key=lambda x: (x["type"], x["displayName"])):
            print(f"  {i['type']:<16} {i['displayName']}")
        lh = self.get_item(ws["id"], self.config.lakehouse, "Lakehouse")
        if lh:
            detail = self.fab.call("GET", f"/workspaces/{ws['id']}/lakehouses/{lh['id']}")
            server, db = self.sql_endpoint(detail)
            print(f"\nFABRIC_SQL_ENDPOINT = {server}")
            print(f"FABRIC_DATABASE     = {self.config.lakehouse}")
            print(f"sql endpoint id     = {db}")


def main(argv=None, environ=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--capacity", help="Explicit capacity name; otherwise FABRIC_CAPACITY_NAME is required.")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--only", choices=["workspace", "lakehouse", "upload",
                                         "notebook", "semantic-model"])
    mode.add_argument("--status", action="store_true")
    ap.add_argument("--skip-run", action="store_true",
                    help="create the notebook but do not execute it")
    args = ap.parse_args(argv)
    if args.status and (args.skip_run or args.capacity is not None):
        ap.error("--status cannot be combined with --capacity or --skip-run.")
    try:
        config = DeploymentConfig(args, os.environ if environ is None else environ)
        config.validate_inputs()
    except ConfigurationError as exc:
        ap.error(str(exc))
    from azure.identity import AzureCliCredential
    import requests

    deployment = FabricDeployment(config, AzureCliCredential(tenant_id=config.tenant_id), requests)

    if args.status:
        deployment.status()
        return

    steps = config.steps

    ws_id = deployment.ensure_workspace(config.capacity) if "workspace" in steps else \
        (deployment.get_workspace() or sys.exit("workspace not found - run --only workspace"))["id"]

    lh = None
    if any(s in steps for s in ("lakehouse", "upload", "notebook", "semantic-model")):
        lh = deployment.ensure_lakehouse(ws_id)

    if "upload" in steps:
        deployment.upload_csvs(ws_id, lh["id"])

    if "notebook" in steps:
        nb_id = deployment.ensure_notebook(
            ws_id, lh["id"], config.notebook, "load_client_intel_fabric.py",
            "Loads the client intelligence CSVs into Delta tables.")
        if not args.skip_run:
            deployment.run_notebook(ws_id, nb_id)

    if "semantic-model" in steps:
        deployment.ensure_semantic_model(ws_id, lh["id"], skip_run=args.skip_run)

    print()
    deployment.status()


if __name__ == "__main__":
    main()
