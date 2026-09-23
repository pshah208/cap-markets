"""Create the Azure AI Search index for the Capital Markets policy corpus and
upload the documents. This index is the **Foundry IQ** knowledge source for the
Client Intelligence Agent.

SYNTHETIC DEMO DATA - see ../scenario_facts.py for the full disclaimer. Every
policy, threshold and approval authority in the corpus is invented for a demo.

Usage:
    pip install azure-search-documents==11.5.2 azure-identity

    $env:SEARCH_ENDPOINT = "https://<service>.search.windows.net"
    $env:SEARCH_INDEX    = "cm-client-policies"     # optional, this is the default

    # Auth is either RBAC (preferred) ...
    #   az search service update -g <rg> -n <svc> --auth-options aadOrApiKey
    #   caller needs Search Service Contributor + Search Index Data Contributor
    az login
    python index_cm_policies.py

    # ... or an admin key
    $env:SEARCH_ADMIN_KEY = "<admin-key>"
    python index_cm_policies.py

    python index_cm_policies.py --verify   # run the demo queries against the index

Keyword + semantic ranking, no embedding model required. The corpus is 14 long
policy documents; semantic ranking over full documents is sufficient for the
demo's retrieval quality. Add a vector profile later if you want hybrid.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time

from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchableField,
    SearchFieldDataType,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
)

HERE = pathlib.Path(__file__).parent
CORPUS = HERE / "cm_policies.json"

INDEX_NAME = os.getenv("SEARCH_INDEX", "cm-client-policies")
ENDPOINT = os.environ.get("SEARCH_ENDPOINT")
KEY = os.getenv("SEARCH_ADMIN_KEY")

if not ENDPOINT:
    sys.exit("SEARCH_ENDPOINT is not set. Export it and retry.")

if KEY:
    from azure.core.credentials import AzureKeyCredential

    CRED = AzureKeyCredential(KEY)
    AUTH = "admin key"
else:
    from azure.identity import DefaultAzureCredential

    CRED = DefaultAzureCredential()
    AUTH = "Entra RBAC (DefaultAzureCredential)"


def build_index(recreate: bool = False) -> None:
    client = SearchIndexClient(ENDPOINT, CRED)

    # Field *types* are immutable on an existing index. If the schema drifts, the
    # only way forward is to drop and rebuild - the corpus is small and is
    # re-uploaded on every run anyway.
    if recreate:
        try:
            client.delete_index(INDEX_NAME)
            print(f"  deleted existing index '{INDEX_NAME}'")
            time.sleep(3)
        except Exception:
            pass

    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SearchableField(name="title", type=SearchFieldDataType.String),
        SearchableField(
            name="category", type=SearchFieldDataType.String,
            filterable=True, facetable=True,
        ),
        SimpleField(
            name="effective_date", type=SearchFieldDataType.String,
            filterable=True, sortable=True,
        ),
        SearchableField(name="owner", type=SearchFieldDataType.String, filterable=True),
        # NOTE: SearchableField needs collection=True to emit Collection(Edm.String).
        # Passing only type=Collection(...) is silently downgraded to Edm.String,
        # and the failure surfaces much later as "An unexpected 'StartArray' node
        # was found" on upload rather than at index-creation time.
        SearchableField(
            name="applies_to", type=SearchFieldDataType.String, collection=True,
            filterable=True, facetable=True,
        ),
        SearchableField(name="regulatory_anchor", type=SearchFieldDataType.String),
        SearchableField(name="content", type=SearchFieldDataType.String),
    ]
    semantic = SemanticSearch(
        configurations=[
            SemanticConfiguration(
                name="default",
                prioritized_fields=SemanticPrioritizedFields(
                    title_field=SemanticField(field_name="title"),
                    keywords_fields=[
                        SemanticField(field_name="category"),
                        SemanticField(field_name="regulatory_anchor"),
                    ],
                    content_fields=[SemanticField(field_name="content")],
                ),
            )
        ]
    )
    SearchIndexClient(ENDPOINT, CRED).create_or_update_index(
        SearchIndex(name=INDEX_NAME, fields=fields, semantic_search=semantic)
    )
    print(f"  index '{INDEX_NAME}' created/updated")

def upload_docs() -> int:
    payload = json.loads(CORPUS.read_text(encoding="utf-8"))
    docs = payload["documents"]
    result = SearchClient(ENDPOINT, INDEX_NAME, CRED).upload_documents(documents=docs)
    ok = sum(1 for r in result if r.succeeded)
    print(f"  uploaded {ok}/{len(docs)} policy documents")

    by_cat: dict[str, int] = {}
    for d in docs:
        by_cat[d["category"]] = by_cat.get(d["category"], 0) + 1
    for cat, n in sorted(by_cat.items()):
        print(f"    {cat:<24} {n}")
    return ok


# The retrieval the agent actually depends on. If these come back empty the demo
# fails on stage, so they are worth asserting at load time.
VERIFY_QUERIES = [
    ("what approval is required for a CAD 210m loan commitment", "CP-003"),
    ("leverage covenant headroom pro-forma test before pitch", "CP-005"),
    ("wall crossing restricted list research publication", "CP-008"),
    ("KYC periodic refresh overdue consequences", "CP-006"),
    ("derivative pre-settlement line potential future exposure", "CP-004"),
    ("sector concentration limit amber distribution plan", "CP-002"),
    ("Gibson Energy account plan wallet share objectives", "CP-012"),
    ("what must a pre-meeting brief contain", "CP-014"),
]


def verify() -> int:
    client = SearchClient(ENDPOINT, INDEX_NAME, CRED)
    print(f"\nVerifying retrieval against '{INDEX_NAME}'")
    failures = 0
    for query, expected in VERIFY_QUERIES:
        results = list(client.search(
            search_text=query,
            query_type="semantic",
            semantic_configuration_name="default",
            select=["id", "title", "category"],
            top=3,
        ))
        ids = [r["id"] for r in results]
        hit = expected in ids
        if not hit:
            failures += 1
        flag = "OK  " if hit else "FAIL"
        print(f"  {flag} {query[:55]:<55} -> {ids} (want {expected})")
    print(f"\n  {len(VERIFY_QUERIES) - failures}/{len(VERIFY_QUERIES)} retrieval checks passed")
    return failures


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verify", action="store_true", help="only run the retrieval checks")
    ap.add_argument("--recreate", action="store_true",
                    help="drop and rebuild the index (needed when field types change)")
    args = ap.parse_args()

    print("Foundry IQ - Capital Markets policy corpus")
    print(f"  endpoint {ENDPOINT}")
    print(f"  auth     {AUTH}\n")

    if not args.verify:
        build_index(recreate=args.recreate)
        n = upload_docs()
        if n == 0:
            return 1
        # The index is eventually consistent; give it a moment before querying.
        print("\n  waiting for the index to settle...")
        time.sleep(8)

    return 1 if verify() else 0


if __name__ == "__main__":
    raise SystemExit(main())
