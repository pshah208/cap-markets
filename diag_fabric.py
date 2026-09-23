"""Query the Fabric semantic model directly, bypassing Foundry.

When Fabric IQ fails, the Foundry error ("Power BI couldn't process that request
right now") does not say whether the problem is the model, the capacity, or the
MCP layer in between. This talks to the Power BI XMLA/REST endpoint directly, so
a success here proves the model and capacity are fine and isolates the fault to
the Fabric IQ tool.

    python diag_fabric.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import time

import requests

WS = "d9d24578-dc14-485f-a29a-5011f9b46b3e"
DS = "8062de98-306f-4b70-8230-872b74d45059"
API = "https://api.powerbi.com/v1.0/myorg"

QUERIES = [
    ("smoke", "EVALUATE ROW(\"ok\", 1)"),
    # The covenant row is what the demo turns on, so proving it is queryable
    # proves the layer that matters, not just that the model answers at all.
    ("covenant",
     "EVALUATE SELECTCOLUMNS(FILTER(covenants, "
     "covenants[client_id] = \"CLI-1001\" && "
     "covenants[covenant] = \"Total Net Debt to Adjusted EBITDA\"), "
     "\"covenant\", covenants[covenant], "
     "\"threshold\", covenants[threshold], "
     "\"actual\", covenants[actual], "
     "\"prior\", covenants[prior_quarter_actual], "
     "\"headroom\", covenants[headroom], "
     "\"status\", covenants[status])"),
    ("limits",
     "EVALUATE SELECTCOLUMNS(FILTER(limits_utilization, "
     "limits_utilization[client_id] = \"CLI-1001\"), "
     "\"limit\", limits_utilization[limit_type], "
     "\"cap\", limits_utilization[limit_cad_m], "
     "\"used\", limits_utilization[utilised_cad_m], "
     "\"pct\", limits_utilization[utilisation_pct], "
     "\"status\", limits_utilization[status])"),
]


def token() -> str:
    out = subprocess.run(
        ["az", "account", "get-access-token", "--resource",
         "https://analysis.windows.net/powerbi/api",
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=True)
    if out.returncode != 0:
        sys.exit(f"token failed: {out.stderr[:300]}")
    return out.stdout.strip()


def main() -> int:
    h = {"Authorization": "Bearer " + token(),
         "Content-Type": "application/json"}

    r = requests.get(f"{API}/groups/{WS}/datasets/{DS}", headers=h, timeout=90)
    if r.status_code == 200:
        d = r.json()
        print(f"dataset  : {d.get('name')}")
        print(f"  storage: {d.get('targetStorageMode')}")
        print(f"  refresh: {d.get('isRefreshable')}")
    else:
        print(f"dataset lookup -> {r.status_code}: {r.text[:300]}")

    r = requests.get(f"{API}/groups/{WS}/datasets/{DS}/refreshes?$top=3",
                     headers=h, timeout=90)
    if r.status_code == 200:
        for x in r.json().get("value", []):
            print(f"  refresh {x.get('status')} {x.get('endTime','')} "
                  f"{(x.get('serviceExceptionJson') or '')[:200]}")

    failures = 0
    for label, dax in QUERIES:
        body = {"queries": [{"query": dax}],
                "serializerSettings": {"includeNulls": True}}
        for attempt in range(3):
            r = requests.post(
                f"{API}/groups/{WS}/datasets/{DS}/executeQueries",
                headers=h, json=body, timeout=180)
            if r.status_code == 200:
                rows = r.json()["results"][0]["tables"][0]["rows"]
                print(f"\n[{label}] OK  {len(rows)} row(s)")
                print("  " + json.dumps(rows[:5])[:400])
                break
            if r.status_code in (429, 503):
                wait = 5 * (attempt + 1)
                print(f"\n[{label}] {r.status_code} throttled, retry in {wait}s")
                time.sleep(wait)
                continue
            print(f"\n[{label}] FAIL {r.status_code}")
            print("  " + r.text[:500])
            failures += 1
            break
        else:
            print(f"\n[{label}] still throttled after retries")
            failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
