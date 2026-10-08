"""Create the Azure AI Search index for the Capital Markets policy corpus and
upload the documents. This index is the **Foundry IQ** knowledge source for the
Client Intelligence Agent.

SYNTHETIC DEMO DATA - see ../scenario_facts.py for the full disclaimer. Every
policy, threshold and approval authority in the corpus is invented for a demo.

Required environment: SEARCH_ENDPOINT, SEARCH_INDEX,
SEARCH_SEMANTIC_CONFIGURATION, AZURE_AUTH_MODE.
Authentication selects exactly one credential:
    azure_cli: AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID
    service_principal: AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET
    managed_identity: AZURE_CLIENT_ID (user-assigned managed identity)
    admin_key: SEARCH_ADMIN_KEY
RBAC callers need Search Service Contributor and Search Index Data Contributor.
There is no implicit credential chain or index-name fallback.

Usage:
    python index_cm_policies.py
    python index_cm_policies.py --verify   # retrieval checks only, no index writes
    python index_cm_policies.py --recreate # explicitly delete and rebuild

Keyword + semantic ranking, no embedding model required. The corpus is 14 long
policy documents; semantic ranking over full documents is sufficient for the
demo's retrieval quality. Add a vector profile later if you want hybrid.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import time
from urllib.parse import urlsplit

HERE = pathlib.Path(__file__).parent
CORPUS = HERE / "cm_policies.json"

AUTH_FIELDS = {
    "azure_cli": ("AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID"),
    "service_principal": ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET"),
    "managed_identity": ("AZURE_CLIENT_ID",),
    "admin_key": ("SEARCH_ADMIN_KEY",),
}
REQUIRED_ENV = (
    "SEARCH_ENDPOINT", "SEARCH_INDEX", "SEARCH_SEMANTIC_CONFIGURATION", "AZURE_AUTH_MODE",
)


class ConfigurationError(ValueError):
    """Local configuration must be corrected before external actions."""


def load_config(environ=None) -> dict[str, str]:
    environ = os.environ if environ is None else environ
    names = (*REQUIRED_ENV, *AUTH_FIELDS.get(environ.get("AZURE_AUTH_MODE", "").strip(), ()))
    config = {name: environ.get(name, "").strip() for name in names}
    missing = [name for name, value in config.items() if not value]
    if missing:
        raise ConfigurationError("Missing required environment variables: " + ", ".join(missing))
    if config["AZURE_AUTH_MODE"] not in AUTH_FIELDS:
        raise ConfigurationError("AZURE_AUTH_MODE must be one of: " + ", ".join(AUTH_FIELDS))
    endpoint = config["SEARCH_ENDPOINT"]
    try:
        parts = urlsplit(endpoint)
        valid = (
            parts.scheme == "https" and parts.hostname and not parts.username
            and not parts.password and parts.path in ("", "/")
            and not parts.query and not parts.fragment
            and not any(c.isspace() or c in "<>\\?#" for c in endpoint)
        )
        parts.port
    except ValueError:
        valid = False
    if not valid:
        raise ConfigurationError(
            "SEARCH_ENDPOINT must be an HTTPS service URL without credentials, path, query or fragment")
    config["SEARCH_ENDPOINT"] = endpoint.rstrip("/")
    if (not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,126}[a-z0-9]", config["SEARCH_INDEX"])
            or "--" in config["SEARCH_INDEX"]):
        raise ConfigurationError(
            "SEARCH_INDEX must be 2-128 lowercase letters, digits or single hyphens, "
            "starting and ending with a letter or digit")
    semantic = config["SEARCH_SEMANTIC_CONFIGURATION"]
    if len(semantic) > 128 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", semantic):
        raise ConfigurationError(
            "SEARCH_SEMANTIC_CONFIGURATION must be 1-128 letters, digits, underscores or hyphens, "
            "starting with a letter or digit")
    return config


def build_credential(config):
    mode = config["AZURE_AUTH_MODE"]
    if mode == "admin_key":
        from azure.core.credentials import AzureKeyCredential
        return AzureKeyCredential(config["SEARCH_ADMIN_KEY"])
    if mode == "azure_cli":
        from azure.identity import AzureCliCredential
        return AzureCliCredential(
            tenant_id=config["AZURE_TENANT_ID"], subscription=config["AZURE_SUBSCRIPTION_ID"])
    if mode == "service_principal":
        from azure.identity import ClientSecretCredential
        return ClientSecretCredential(
            tenant_id=config["AZURE_TENANT_ID"], client_id=config["AZURE_CLIENT_ID"],
            client_secret=config["AZURE_CLIENT_SECRET"])
    if mode == "managed_identity":
        from azure.identity import ManagedIdentityCredential
        return ManagedIdentityCredential(client_id=config["AZURE_CLIENT_ID"])
    raise ConfigurationError("Unsupported AZURE_AUTH_MODE")


def load_documents(path: pathlib.Path) -> list[dict]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigurationError(f"Cannot read policy corpus {path}: {exc}") from exc
    docs = payload.get("documents") if isinstance(payload, dict) else None
    if not isinstance(docs, list) or not docs:
        raise ConfigurationError("Policy corpus must contain a nonempty documents array")
    text_fields = {"id", "title", "category", "effective_date", "owner", "regulatory_anchor", "content"}
    expected_fields = text_fields | {"applies_to"}
    seen = set()
    for position, doc in enumerate(docs, 1):
        if not isinstance(doc, dict) or set(doc) != expected_fields:
            raise ConfigurationError(
                f"Policy document {position} must have exactly these fields: "
                + ", ".join(sorted(expected_fields)))
        if any(not isinstance(doc[name], str) or not doc[name].strip() for name in text_fields):
            raise ConfigurationError(f"Policy document {position} has a blank or non-string text field")
        if (not isinstance(doc["applies_to"], list)
                or any(not isinstance(value, str) or not value.strip() for value in doc["applies_to"])):
            raise ConfigurationError(f"Policy document {position} applies_to must be an array of strings")
        if not re.fullmatch(r"[A-Za-z0-9_\-=]{1,1024}", doc["id"]) or doc["id"] in seen:
            raise ConfigurationError(f"Policy document {position} has an invalid or duplicate id")
        seen.add(doc["id"])
    return docs


def build_index(config, credential, recreate: bool = False) -> None:
    from azure.core.exceptions import ResourceNotFoundError
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

    # Field *types* are immutable on an existing index. If the schema drifts, the
    # only way forward is to drop and rebuild - the corpus is small and is
    # re-uploaded on every run anyway.
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
                name=config["SEARCH_SEMANTIC_CONFIGURATION"],
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
    with SearchIndexClient(config["SEARCH_ENDPOINT"], credential) as client:
        if recreate:
            try:
                client.delete_index(config["SEARCH_INDEX"])
                print(f"  deleted existing index '{config['SEARCH_INDEX']}'")
                time.sleep(3)
            except ResourceNotFoundError:
                pass
        client.create_or_update_index(
            SearchIndex(name=config["SEARCH_INDEX"], fields=fields, semantic_search=semantic)
        )
    print(f"  index '{config['SEARCH_INDEX']}' created/updated")


def upload_docs(config, credential, docs) -> int:
    from azure.search.documents import SearchClient

    with SearchClient(config["SEARCH_ENDPOINT"], config["SEARCH_INDEX"], credential) as client:
        result = client.upload_documents(documents=docs)
    ok = sum(1 for r in result if r.succeeded)
    print(f"  uploaded {ok}/{len(docs)} policy documents")
    if ok != len(docs):
        failed_keys = [str(r.key) for r in result if not r.succeeded]
        raise RuntimeError(f"Policy upload incomplete ({ok}/{len(docs)}); failed keys: {failed_keys}")

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


def verify(config, credential) -> int:
    from azure.search.documents import SearchClient

    print(f"\nVerifying retrieval against '{config['SEARCH_INDEX']}'")
    failures = 0
    with SearchClient(config["SEARCH_ENDPOINT"], config["SEARCH_INDEX"], credential) as client:
        for query, expected in VERIFY_QUERIES:
            results = list(client.search(
                search_text=query,
                query_type="semantic",
                semantic_configuration_name=config["SEARCH_SEMANTIC_CONFIGURATION"],
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


def main(argv=None, *, environ=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    actions = ap.add_mutually_exclusive_group()
    actions.add_argument("--verify", action="store_true", help="only run the retrieval checks")
    actions.add_argument("--recreate", action="store_true",
                         help="drop and rebuild the index (needed when field types change)")
    args = ap.parse_args(argv)
    try:
        config = load_config(environ)
        docs = None if args.verify else load_documents(CORPUS)
    except ConfigurationError as exc:
        ap.error(str(exc))

    print("Foundry IQ - Capital Markets policy corpus")
    print(f"  endpoint {config['SEARCH_ENDPOINT']}")
    print(f"  auth     {config['AZURE_AUTH_MODE']}\n")

    credential = None
    try:
        credential = build_credential(config)
        if not args.verify:
            build_index(config, credential, recreate=args.recreate)
            upload_docs(config, credential, docs)
            # The index is eventually consistent; allow it to settle before queries.
            print("\n  waiting for the index to settle...")
            time.sleep(8)
        return 1 if verify(config, credential) else 0
    except (ImportError, RuntimeError) as exc:
        print(f"Indexer failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if credential is not None and callable(getattr(credential, "close", None)):
            credential.close()


if __name__ == "__main__":
    raise SystemExit(main())
