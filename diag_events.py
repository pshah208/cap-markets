"""Dump every distinct SSE event Foundry emits so I can see what the BFF misses.

Prints each event type once with its raw JSON so I can identify the fields
that carry item ids and server labels.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import time

import httpx


def token() -> str:
    out = subprocess.run(
        ["az", "account", "get-access-token", "--resource",
         "https://ai.azure.com", "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=True)
    return out.stdout.strip()


def main() -> None:
    tok = token()
    url = ("https://cmintel-foundry.services.ai.azure.com"
           "/api/projects/proj-client-intelligence"
           "/openai/responses?api-version=2025-05-15-preview")
    body = {
        "agent_reference": {"type": "agent_reference",
                             "name": "Agent-cap-market"},
        "input": "What is Gibson Energy's Total Net Debt to Adjusted EBITDA covenant position?",
        "stream": True,
    }
    seen: dict[str, str] = {}
    start = time.time()

    with httpx.Client(timeout=httpx.Timeout(300.0, connect=30.0)) as c:
        with c.stream("POST", url,
                      headers={"Authorization": f"Bearer {tok}"},
                      json=body) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    evt = json.loads(data)
                except json.JSONDecodeError:
                    continue
                etype = evt.get("type", "?")
                # Distinguish by (event type, item type) so we see both
                # "response.output_item.added:mcp_list_tools" and
                # "response.output_item.added:mcp_call".
                item = evt.get("item") or {}
                key = f"{etype}:{item.get('type','')}"
                if key in seen:
                    continue
                seen[key] = data[:400]
                elapsed = time.time() - start
                print(f"\n  {elapsed:6.1f}s  {key}")
                # Highlight fields we care about
                relevant = {k: v for k, v in evt.items()
                            if k in ("type", "output_index", "item_id",
                                     "item", "delta", "response")
                            and k != "response"}
                if "item" in relevant and isinstance(relevant["item"], dict):
                    relevant["item"] = {
                        k: v for k, v in relevant["item"].items()
                        if k in ("id", "type", "status", "server_label",
                                 "name", "arguments")
                    }
                print(f"           {json.dumps(relevant)[:250]}")
                if etype.endswith("response.completed") or etype.endswith("response.failed"):
                    break

    print(f"\n{len(seen)} distinct (event, item_type) combinations")


if __name__ == "__main__":
    main()
