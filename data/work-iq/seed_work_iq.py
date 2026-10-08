"""Seed the Work IQ layer for the Capital Markets Client Intelligence Agent into Microsoft 365.

Loads three things into a demo/dev tenant:

  mail    the 22 hero-client (CLI-1001) coverage emails, imported into each
          recipient's Inbox with the original sender and timestamp preserved.
          emails.json also carries emails for other portfolio clients, which
          exist only for the offline dashboard cache and are never seeded.
  teams   the "Capital Markets - Gibson Energy Coverage" team, 4 channels, 14 conversations
  files   the 5 meeting records and 2 client documents uploaded to the team's SharePoint document library
          (and optionally a user's OneDrive)

--------------------------------------------------------------------------------
PREREQUISITES
--------------------------------------------------------------------------------
1. A **non-production / demo tenant**. This script writes into user mailboxes and
   renames directory accounts.

2. **Licensed accounts for the 14 personas.** Do NOT create new users unless you
   have spare licences - a user without Exchange Online has no mailbox (mail
   import fails), and without a Microsoft 365 Copilot licence Work IQ cannot
   ground on their content. Instead, map the personas onto existing licensed
   users in an explicitly configured private mapping JSON, then:

       python seed_work_iq.py --auth cli --check-users
       python seed_work_iq.py --auth cli --map-users --dry-run
       python seed_work_iq.py --auth cli --map-users      # snapshots originals
       python seed_work_iq.py --auth cli --restore-users  # undo

   `--map-users` sets displayName / jobTitle / department (mail renders
   displayName, which is what makes the narrative read correctly) and writes the
   originals to WORKIQ_RESTORE_FILE. UPNs and licences are untouched.

3. An Entra ID app registration with a client secret, and these **application**
   permissions granted with admin consent:

     User.Read.All            resolve aliases -> user ids
     User.ReadWrite.All       --map-users (or run that step with --auth cli)
     Mail.ReadWrite           import messages into mailboxes
     Group.ReadWrite.All      create the team's group
     Team.Create              create the team
     Channel.Create           create channels
     ChannelMessage.Send      post channel messages   *see note below*
     Files.ReadWrite.All      upload meeting notes
     Sites.ReadWrite.All      upload to the team's SharePoint library

   NOTE on ChannelMessage.Send with *application* permissions: this is a
   Microsoft "protected API" and requires a separate request to Microsoft
   (https://aka.ms/teamsgraph/requestaccess). If you do not have that approval,
   run the teams step with delegated auth instead:

       python seed_work_iq.py --only teams --auth device

   Delegated device-code auth posts every message as the signed-in user; the
   script prefixes each post with the original author so the narrative survives.

4. **The demo driver.** Work IQ grounds only on content the signed-in user can
   access, so the explicitly configured `driver_alias` in the mapping JSON is
   cc'd on every email the persona is not already party to.

--------------------------------------------------------------------------------
CONFIGURE
--------------------------------------------------------------------------------
    $env:WORKIQ_TENANT_ID     = "<tenant-guid>"
    $env:WORKIQ_CLIENT_ID     = "<app-registration-client-id>"
    $env:WORKIQ_CLIENT_SECRET = "<client-secret>"     # app auth only
    $env:WORKIQ_USER_MAPPING_FILE = "<private-mapping-json-path>"
    # required for --map-users / --restore-users only:
    $env:WORKIQ_RESTORE_FILE = "<private-restore-json-path>"

    pip install azure-identity requests

--------------------------------------------------------------------------------
RUN
--------------------------------------------------------------------------------
    python seed_work_iq.py --auth cli --check-users
    python seed_work_iq.py --only mail
    python seed_work_iq.py --only teams --auth device
    python seed_work_iq.py --only teams --migrate --recreate   # app-only, backdated
    python seed_work_iq.py --only files
    python seed_work_iq.py --all --dry-run        # print what would happen
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from workiq_config import ConfigurationError, SeederConfig, load_config

GRAPH = "https://graph.microsoft.com/v1.0"
GRAPH_BETA = "https://graph.microsoft.com/beta"
HERE = Path(__file__).parent

HERO_CLIENT_ID = "CLI-1001"
LIBRARY_FOLDER = "Gibson Energy Coverage"


# --------------------------------------------------------------------------- #
# auth + http
# --------------------------------------------------------------------------- #
class Graph:
    def __init__(self, mode: str, dry_run: bool = False, *,
                 config: SeederConfig | None = None):
        self.config = config or load_config(
            mode, actions=("mail", "teams", "files"), source_dir=HERE,
        )
        if mode not in ("app", "device", "cli"):
            raise ConfigurationError("auth must be app, device, or cli")
        missing = []
        if not self.config.tenant_id:
            missing.append("WORKIQ_TENANT_ID")
        if mode != "cli" and not self.config.client_id:
            missing.append("WORKIQ_CLIENT_ID")
        if mode == "app" and not self.config.client_secret:
            missing.append("WORKIQ_CLIENT_SECRET")
        if missing:
            raise ConfigurationError("Required environment variables: " + ", ".join(missing))
        from azure.identity import (
            AzureCliCredential, ClientSecretCredential, DeviceCodeCredential,
            TokenCachePersistenceOptions,
        )

        self.dry_run = dry_run
        if mode == "app":
            self._cred = ClientSecretCredential(
                self.config.tenant_id, self.config.client_id, self.config.client_secret,
            )
            self._scopes = ["https://graph.microsoft.com/.default"]
        elif mode == "cli":
            # Uses `az login`. Enough for --check-users / --map-users / --restore-users,
            # which only read and patch directory objects as an admin.
            self._cred = AzureCliCredential(tenant_id=self.config.tenant_id)
            self._scopes = ["https://graph.microsoft.com/.default"]
        else:
            # The default 60-second device-code window is too short when a human
            # has to switch to a browser and sign in; 600s is a realistic budget.
            # The token is cached so re-runs and follow-up steps do not re-prompt.
            self._cred = DeviceCodeCredential(
                client_id=self.config.client_id,
                tenant_id=self.config.tenant_id,
                timeout=600,
                cache_persistence_options=TokenCachePersistenceOptions(
                    name=f"workiq-{self.config.tenant_id}-{self.config.client_id}",
                ),
            )
            self._scopes = [
                "https://graph.microsoft.com/ChannelMessage.Send",
                "https://graph.microsoft.com/Group.ReadWrite.All",
                "https://graph.microsoft.com/Files.ReadWrite.All",
                "https://graph.microsoft.com/User.Read.All",
            ]
        self.mode = mode
        self._token: str | None = None
        self._expires = 0.0

    def _headers(self) -> dict[str, str]:
        if not self._token or time.time() > self._expires - 120:
            tok = self._cred.get_token(*self._scopes)
            self._token, self._expires = tok.token, tok.expires_on
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    def call(self, method: str, url: str, *, json_body: Any = None,
             raw: bytes | None = None, content_type: str | None = None,
             ok_404: bool = False) -> Any:
        if not url.startswith("http"):
            url = f"{GRAPH}{url}"
        from urllib.parse import urlsplit

        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.netloc != "graph.microsoft.com"
                or not parsed.path.startswith(("/v1.0/", "/beta/")) or parsed.fragment):
            raise ValueError("Graph requests must stay on https://graph.microsoft.com/v1.0/ or /beta/")
        if self.dry_run and method.upper() != "GET":
            print(f"    [dry-run] {method.upper()} {url}")
            return {"id": "dry-run-id"}

        import requests

        for attempt in range(6):
            headers = self._headers()
            if content_type:
                headers["Content-Type"] = content_type
            resp = requests.request(
                method, url, headers=headers,
                json=json_body if raw is None else None,
                data=raw, timeout=60, allow_redirects=False,
            )
            if 300 <= resp.status_code < 400:
                raise RuntimeError("Graph HTTP redirects are refused to protect the bearer token")
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = int(resp.headers.get("Retry-After", 2 ** attempt))
                print(f"    throttled ({resp.status_code}), retrying in {wait}s")
                time.sleep(wait)
                continue
            if resp.status_code == 404 and ok_404:
                return None
            if resp.status_code >= 400:
                raise RuntimeError(f"{method} {url} -> {resp.status_code}: {resp.text[:600]}")
            if not resp.content:
                return None
            return resp.json()
        raise RuntimeError(f"{method} {url} failed after retries")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def upn(alias: str, config: SeederConfig) -> str:
    return config.upn(alias)


def map_users(g: Graph) -> None:
    """Rename the mapped accounts to the persona identities, snapshotting first.

    Mail renders displayName, so this is what makes the narrative read correctly
    without creating new (unlicensable) users. Reversible via --restore-users.
    """
    entries = g.config.accounts
    restore_file = g.config.restore_file
    if restore_file is None:
        raise ConfigurationError("WORKIQ_RESTORE_FILE is required for --map-users")
    snapshot = dict(g.config.snapshot)
    updates = []

    for alias, e in entries.items():
        current = g.call("GET", f"/users/{e['upn']}"
                                "?$select=id,displayName,jobTitle,department,mail",
                         ok_404=True)
        if not current:
            print(f"  !! not found: {e['upn']}")
            continue
        if e["upn"] not in snapshot:
            snapshot[e["upn"]] = {
                "displayName": current.get("displayName"),
                "jobTitle": current.get("jobTitle"),
                "department": current.get("department"),
            }
        updates.append((current, e))

    # Persist originals before the first directory mutation, including on partial
    # failure. Existing originals are never replaced by already-renamed values.
    if not g.dry_run and updates:
        restore_file.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        print(f"\noriginals snapshotted to {restore_file.name} - keep this file")
    for current, e in updates:
        g.call("PATCH", f"/users/{e['upn']}", json_body={
            "displayName": e["displayName"],
            "jobTitle": e["jobTitle"],
            "department": e["department"],
        })
        print(f"  {current.get('displayName','?'):<20} -> {e['displayName']:<20} "
              f"({e['upn'].split('@')[0]})")

def restore_users(g: Graph) -> None:
    if g.config.restore_file is None or not g.config.snapshot:
        raise ConfigurationError("WORKIQ_RESTORE_FILE must be validated before --restore-users")
    snapshot = g.config.snapshot
    for target, original in snapshot.items():
        g.call("PATCH", f"/users/{target}",
               json_body={k: v for k, v in original.items()})
        print(f"  restored {target.split('@')[0]:<12} -> {original['displayName']}")
    print(f"\n{len(snapshot)} account(s) restored.")


def load(name: str) -> dict:
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def html_body(text: str) -> str:
    paras = "".join(
        f"<p>{p.replace(chr(10), '<br/>')}</p>" for p in text.split("\n\n") if p.strip()
    )
    return f"<html><body style=\"font-family:Segoe UI,Arial,sans-serif;font-size:11pt\">{paras}</body></html>"


def resolve_users(g: Graph, aliases: list[str]) -> dict[str, str]:
    ids: dict[str, str] = {}
    for a in aliases:
        u = g.call("GET", f"/users/{upn(a, g.config)}?$select=id,displayName", ok_404=True)
        if u:
            ids[a] = u["id"]
        else:
            print(f"    !! user not found: {upn(a, g.config)}")
    return ids


# --------------------------------------------------------------------------- #
# 1. mail
# --------------------------------------------------------------------------- #
def seed_mail(g: Graph, purge: bool = False, *, source: str = "emails.json",
              all_clients: bool = False) -> None:
    data = load(source)
    # Only the hero client's correspondence is seeded into the tenant. Emails
    # attributed to other portfolio clients back the offline dashboard evidence
    # cache and must not be written to Microsoft 365.
    if not all_clients:
        data = dict(data, emails=[e for e in data["emails"]
                                  if e.get("client_id", HERO_CLIENT_ID) == HERO_CLIENT_ID])
    people = {p["alias"]: p for p in data["people"]}
    driver_alias = g.config.driver_alias
    if not driver_alias:
        raise ConfigurationError("WORKIQ_USER_MAPPING_FILE requires driver_alias for mail")
    if driver_alias not in people:
        people[driver_alias] = g.config.accounts[driver_alias]
    for alias in people:
        upn(alias, g.config)
    print(f"\n== MAIL == {len(data['emails'])} messages")

    if purge:
        purge_mail(g, data)

    def recipient(alias: str) -> dict:
        return {"emailAddress": {"address": upn(alias, g.config),
                                 "name": people[alias]["displayName"]}}

    for em in data["emails"]:
        sender = recipient(em["from"])
        cc_aliases = list(em.get("cc", []))
        # Work IQ only grounds on what the signed-in user can see, so the demo
        # driver is cc'd on anything they are not already party to.
        if driver_alias not in (
            [em["from"]] + em["to"] + cc_aliases
        ):
            cc_aliases.append(driver_alias)

        when = em["sentDateTime"]
        payload_base = {
            "subject": em["subject"],
            "importance": em.get("importance", "normal"),
            "body": {"contentType": "HTML", "content": html_body(em["body"])},
            "from": sender,
            "sender": sender,
            "toRecipients": [recipient(a) for a in em["to"]],
            "ccRecipients": [recipient(a) for a in cc_aliases],
            "sentDateTime": when,
            "receivedDateTime": when,
            "isRead": False,
            "singleValueExtendedProperties": [
                # PidTagMessageFlags - mark as sent/submitted so the message is
                # not treated as a draft in the recipient's Inbox.
                {"id": "Integer 0x0E07", "value": "1"},
                # Exchange silently rewrites sentDateTime/receivedDateTime to "now"
                # on create. Setting the underlying MAPI properties preserves the
                # original timeline, which the whole narrative depends on.
                # PR_CLIENT_SUBMIT_TIME / PR_MESSAGE_DELIVERY_TIME
                {"id": "SystemTime 0x0039", "value": when},
                {"id": "SystemTime 0x0E06", "value": when},
            ],
        }

        targets = list(dict.fromkeys(em["to"] + cc_aliases))
        for alias in targets:
            g.call("POST", f"/users/{upn(alias, g.config)}/mailFolders/inbox/messages",
                   json_body=payload_base)
        # keep a copy in the author's Sent Items so "what did I send" queries work
        g.call("POST", f"/users/{upn(em['from'], g.config)}/mailFolders/sentitems/messages",
               json_body=payload_base)
        print(f"  {em['id']}  {when[:10]}  {em['subject'][:52]:<52} "
              f"-> {len(targets)} inbox(es) + sent")


def purge_mail(g: Graph, data: dict) -> None:
    """Remove previously seeded copies so a re-run does not duplicate them."""
    subjects = {e["subject"] for e in data["emails"]}
    aliases = {p["alias"] for p in data["people"]}
    aliases.add(g.config.driver_alias)
    removed = 0
    for alias in sorted(aliases):
        for folder in ("inbox", "sentitems"):
            page = (f"/users/{upn(alias, g.config)}/mailFolders/{folder}/messages"
                    "?$select=subject&$top=100")
            while page:
                res = g.call("GET", page if page.startswith("http") else page)
                if not res:
                    break
                for m in res.get("value", []):
                    if m.get("subject") in subjects:
                        g.call("DELETE", f"/users/{upn(alias, g.config)}/messages/{m['id']}")
                        removed += 1
                page = res.get("@odata.nextLink")
    print(f"  purged {removed} previously seeded message(s)")


# --------------------------------------------------------------------------- #
# 2. teams
# --------------------------------------------------------------------------- #
def find_group(g: Graph, display_name: str) -> str | None:
    esc = display_name.replace("'", "''")
    r = g.call("GET", f"/groups?$filter=displayName eq '{esc}'&$select=id,displayName")
    vals = r["value"]
    return vals[0]["id"] if vals else None


def seed_teams(g: Graph, messages_only: bool = False) -> None:
    data = load("teams_messages.json")
    people = {p["alias"]: p for p in load("emails.json")["people"]}
    team_def = data["team"]
    name = team_def["displayName"]
    print(f"\n== TEAMS == {name}")

    team_id = find_group(g, name)
    if team_id:
        print(f"  team already exists: {team_id}")
    elif messages_only:
        sys.exit("  team does not exist - run --only teams first")
    else:
        # App-only team creation accepts exactly one member (the owner);
        # everyone else is added afterwards via the members collection.
        owner = team_def["ownerAliases"][0]
        g.call("POST", "/teams", json_body={
            "template@odata.bind": "https://graph.microsoft.com/v1.0/teamsTemplates('standard')",
            "displayName": name,
            "description": team_def["description"],
            "visibility": team_def["visibility"],
            "members": [{
                "@odata.type": "#microsoft.graph.aadUserConversationMember",
                "roles": ["owner"],
                "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{upn(owner, g.config)}')",
            }],
        })
        print("  team creation accepted - Graph provisions asynchronously, waiting…")
        for _ in range(30):
            time.sleep(10)
            team_id = find_group(g, name)
            if team_id:
                break
        if not team_id:
            sys.exit("  team did not provision in time; re-run --only teams in a few minutes")
        print(f"  team provisioned: {team_id}")

    # Skip only confirmed members; failed lookups or writes must stop the seed.
    if not messages_only:
        current = {
            m.get("userId")
            for m in g.call("GET", f"/teams/{team_id}/members")["value"]
        }
        added, skipped = 0, 0
        for a in team_def["ownerAliases"] + team_def["memberAliases"]:
            user = g.call("GET", f"/users/{upn(a, g.config)}?$select=id")
            if user["id"] in current:
                skipped += 1
                continue
            g.call("POST", f"/teams/{team_id}/members", json_body={
                "@odata.type": "#microsoft.graph.aadUserConversationMember",
                "roles": ["owner"] if a in team_def["ownerAliases"] else [],
                "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{user['id']}')",
            })
            current.add(user["id"])
            added += 1
        print(f"  members: +{added} added, {skipped} already present")

    existing = {c["displayName"]: c["id"]
                for c in g.call("GET", f"/teams/{team_id}/channels")["value"]}

    posted = 0

    for ch in data["channels"]:
        ch_id = existing.get(ch["displayName"])
        if not ch_id:
            created = g.call("POST", f"/teams/{team_id}/channels", json_body={
                "displayName": ch["displayName"],
                "description": ch["description"],
                "membershipType": "standard",
            })
            ch_id = created["id"]
            print(f"  + channel {ch['displayName']}")
            time.sleep(3)
        else:
            print(f"  = channel {ch['displayName']} (exists)")

        for conv in ch["conversations"]:
            root = post_message(g, team_id, ch_id, conv["from"], people,
                                subject=conv.get("subject"), text=conv["message"])
            posted += 1
            for reply in conv.get("replies", []):
                post_message(g, team_id, ch_id, reply["from"], people,
                             text=reply["message"], reply_to=root)
                posted += 1
            print(f"    {conv['id']}  {conv.get('subject','')[:52]:<52} "
                  f"+{len(conv.get('replies', []))} replies")

    print(f"\n  messages posted: {posted}")


# --------------------------------------------------------------------------- #
# 2b. teams, migration mode (Teamwork.Migrate.All)
# --------------------------------------------------------------------------- #
def _clamped_timeline(data: dict) -> dict[int, str]:
    """Original timestamps, with any that are in the future squeezed into the
    window just before now - Graph rejects future createdDateTime on import.
    Order is preserved, so replies still follow their roots."""
    from datetime import datetime, timedelta, timezone

    def parse(s: str) -> datetime:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))

    items: list[tuple[datetime, int]] = []
    for ch in data["channels"]:
        for conv in ch["conversations"]:
            items.append((parse(conv["createdDateTime"]), id(conv)))
            for r in conv.get("replies", []):
                items.append((parse(r["createdDateTime"]), id(r)))
    items.sort()
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=3)
    past = [t for t, _ in items if t <= cutoff]
    future = [(t, k) for t, k in items if t > cutoff]
    start = max(past) if past else cutoff - timedelta(hours=6)
    step = (cutoff - start) / (len(future) + 1) if future else timedelta(0)
    out = {k: t for t, k in items if t <= cutoff}
    for i, (_, k) in enumerate(future, 1):
        out[k] = start + step * i
    if future:
        print(f"  {len(future)} future-dated post(s) compressed into "
              f"{start:%Y-%m-%d %H:%M} .. {cutoff:%Y-%m-%d %H:%M} UTC (Graph rejects future timestamps)")
    return {k: v.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z" for k, v in out.items()}


def seed_teams_migration(g: Graph, recreate: bool = False) -> None:
    """Create the team in migration mode and import every post with its original
    author and timestamp, then complete migration and add the members."""
    from datetime import datetime, timedelta

    data = load("teams_messages.json")
    people = {p["alias"]: p for p in load("emails.json")["people"]}
    team_def = data["team"]
    name = team_def["displayName"]
    print(f"\n== TEAMS (migration) == {name}")

    members = team_def["ownerAliases"] + team_def["memberAliases"]
    ids = resolve_users(g, list(dict.fromkeys([*people, *members])))
    if set(people) - ids.keys():
        raise RuntimeError("All configured migration authors must resolve before team changes")
    if set(members) - ids.keys():
        raise RuntimeError("All configured migration members must resolve before team changes")
    member_roles = {}
    for alias in members:
        user_id = ids[alias]
        member_roles[user_id] = (
            member_roles.get(user_id, False) or alias in team_def["ownerAliases"]
        )
    existing = find_group(g, name)
    if existing:
        if not recreate:
            sys.exit("  team already exists - pass --recreate to delete and re-import it "
                     "(deleted groups are recoverable for 30 days)")
        g.call("DELETE", f"/groups/{existing}")
        print(f"  deleted existing team group {existing} (soft-delete, recoverable 30 days)")
        for _ in range(30):
            time.sleep(5)
            if not find_group(g, name):
                break

    times = _clamped_timeline(data)
    first = min(times.values())
    created = (datetime.fromisoformat(first.replace("Z", "+00:00")) - timedelta(days=1))
    created_s = created.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    g.call("POST", "/teams", json_body={
        "@microsoft.graph.teamCreationMode": "migration",
        "template@odata.bind": "https://graph.microsoft.com/v1.0/teamsTemplates('standard')",
        "displayName": name,
        "description": team_def["description"],
        "createdDateTime": created_s,
    })
    print("  migration-mode team requested, waiting for provisioning…")
    team_id = None
    for _ in range(40):
        time.sleep(10)
        team_id = find_group(g, name)
        if team_id and g.call("GET", f"/teams/{team_id}/channels", ok_404=True):
            break
    if not team_id:
        sys.exit("  team did not provision in time; re-run with --recreate")
    print(f"  team provisioned: {team_id}")

    chans = {c["displayName"]: c["id"]
             for c in g.call("GET", f"/teams/{team_id}/channels")["value"]}

    def author(alias: str) -> dict:
        return {"user": {"id": ids[alias], "displayName": people[alias]["displayName"],
                         "userIdentityType": "aadUser"}}

    imported = 0
    for ch in data["channels"]:
        ch_id = chans.get(ch["displayName"])
        if not ch_id:
            ch_id = g.call("POST", f"/teams/{team_id}/channels", json_body={
                "@microsoft.graph.channelCreationMode": "migration",
                "displayName": ch["displayName"],
                "description": ch["description"],
                "membershipType": "standard",
                "createdDateTime": created_s,
            })["id"]
            chans[ch["displayName"]] = ch_id
            print(f"  + channel {ch['displayName']}")
            time.sleep(2)
        for conv in ch["conversations"]:
            body = {"createdDateTime": times[id(conv)], "from": author(conv["from"]),
                    "body": {"contentType": "html", "content": f"<p>{conv['message']}</p>"}}
            if conv.get("subject"):
                body["subject"] = conv["subject"]
            root = g.call("POST", f"/teams/{team_id}/channels/{ch_id}/messages", json_body=body)
            imported += 1
            for r in conv.get("replies", []):
                g.call("POST", f"/teams/{team_id}/channels/{ch_id}/messages/{root['id']}/replies",
                       json_body={"createdDateTime": times[id(r)], "from": author(r["from"]),
                                  "body": {"contentType": "html", "content": f"<p>{r['message']}</p>"}})
                imported += 1
            print(f"    {conv['id']}  {conv.get('subject', '')[:50]:<50} +{len(conv.get('replies', []))}")

    for ch_name, ch_id in chans.items():
        g.call("POST", f"/teams/{team_id}/channels/{ch_id}/completeMigration")
    g.call("POST", f"/teams/{team_id}/completeMigration")
    print(f"  imported {imported} posts; migration completed")

    added = 0
    for user_id, is_owner in member_roles.items():
        g.call("POST", f"/teams/{team_id}/members", json_body={
            "@odata.type": "#microsoft.graph.aadUserConversationMember",
            "roles": ["owner"] if is_owner else [],
            "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{user_id}')",
        })
        added += 1
    print(f"  members added: {added}")


def post_message(g: Graph, team_id: str, ch_id: str, alias: str,
                 people: dict, *, text: str, subject: str | None = None,
                 reply_to: str | None = None) -> str:
    author = people[alias]
    if g.mode == "app":
        # application permissions cannot impersonate; Graph attributes the post to
        # the app. Prefix keeps the narrative attributable to the right persona.
        content = (f"<p><strong>{author['displayName']}</strong> "
                   f"<em>({author['title']})</em></p><p>{text}</p>")
    else:
        content = (f"<p><em>Posting on behalf of {author['displayName']} - "
                   f"{author['title']}</em></p><p>{text}</p>")

    body = {"body": {"contentType": "html", "content": content}}
    if subject and not reply_to:
        body["subject"] = subject

    url = (f"/teams/{team_id}/channels/{ch_id}/messages"
           if not reply_to else
           f"/teams/{team_id}/channels/{ch_id}/messages/{reply_to}/replies")
    try:
        res = g.call("POST", url, json_body=body)
    except RuntimeError as exc:
        if g.mode == "app" and str(exc).startswith(tuple(
            f"POST {GRAPH}{url} -> {status}:" for status in (401, 403)
        )):
            print("\n  Channel message POST was unauthorized or forbidden. Check the token\n"
                  "  and permissions. App-only auth may be the cause; for normal channel\n"
                  "  posting, try delegated device-code auth:\n"
                  "      python seed_work_iq.py --only teams --messages-only --auth device\n"
                  "  Earlier writes are not rolled back; re-running can duplicate messages.")
        raise
    time.sleep(1)
    return res["id"]


# --------------------------------------------------------------------------- #
# 3. files
# --------------------------------------------------------------------------- #
def seed_files(g: Graph, onedrive_alias: str | None) -> None:
    print("\n== FILES ==")
    docs = sorted((HERE / "meetings").glob("*.md"))
    # Client-facing artefacts (pre-meeting brief, pitch book extract). These are
    # what a coverage banker would actually open before a meeting, so they matter
    # more to Work IQ grounding than the raw source JSON.
    client_files = sorted((HERE / "files").glob("*.md"))
    extra = [HERE / "emails.json", HERE / "teams_messages.json"]

    targets: list[tuple[str, str]] = []

    team_name = load("teams_messages.json")["team"]["displayName"]
    group_id = find_group(g, team_name)
    if group_id:
        site = g.call("GET", f"/groups/{group_id}/sites/root?$select=id", ok_404=True)
        if site:
            drive = g.call("GET", f"/sites/{site['id']}/drive?$select=id")
            targets.append((f"/drives/{drive['id']}", f"SharePoint · {team_name}"))
    else:
        print("  !! team not found - run --only teams first to get the SharePoint library")

    if onedrive_alias:
        d = g.call("GET", f"/users/{upn(onedrive_alias, g.config)}/drive?$select=id", ok_404=True)
        if d:
            targets.append((f"/drives/{d['id']}", f"OneDrive · {onedrive_alias}"))

    if not targets:
        print("  nothing to upload to")
        return

    for drive_path, label in targets:
        print(f"  -> {label}")
        for f in docs:
            upload(g, drive_path, f"{LIBRARY_FOLDER}/Meeting Notes/{f.name}", f.read_bytes())
            print(f"     {LIBRARY_FOLDER}/Meeting Notes/{f.name}")
        for f in client_files:
            upload(g, drive_path, f"{LIBRARY_FOLDER}/Client Files/{f.name}", f.read_bytes())
            print(f"     {LIBRARY_FOLDER}/Client Files/{f.name}")
        for f in extra:
            upload(g, drive_path, f"{LIBRARY_FOLDER}/Source/{f.name}", f.read_bytes())
            print(f"     {LIBRARY_FOLDER}/Source/{f.name}")


def upload(g: Graph, drive_path: str, item_path: str, content: bytes) -> None:
    g.call("PUT", f"{drive_path}/root:/{item_path}:/content",
           raw=content, content_type="text/plain")


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", choices=["mail", "teams", "files"])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--auth", choices=["app", "device", "cli"], default="app")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check-users", action="store_true")
    ap.add_argument("--map-users", action="store_true",
                    help="rename the mapped accounts to the persona identities "
                         "(snapshots originals to WORKIQ_RESTORE_FILE)")
    ap.add_argument("--restore-users", action="store_true",
                    help="undo --map-users from the snapshot")
    ap.add_argument("--messages-only", action="store_true",
                    help="with --only teams: post channel messages into an existing team")
    ap.add_argument("--purge", action="store_true",
                    help="with --only mail: delete previously seeded messages first")
    ap.add_argument("--migrate", action="store_true",
                    help="with --only teams: import posts in migration mode with original "
                         "authors and timestamps (needs Teamwork.Migrate.All)")
    ap.add_argument("--recreate", action="store_true",
                    help="with --migrate: delete the existing team first")
    ap.add_argument("--onedrive-alias",
                    help="also copy files into this explicitly mapped user's OneDrive; omitted means SharePoint only")
    args = ap.parse_args()

    steps = ["mail", "teams", "files"] if (args.all or not args.only) else [args.only]
    user_actions = [name for name, enabled in (
        ("map", args.map_users), ("restore", args.restore_users), ("check", args.check_users)
    ) if enabled]
    if len(user_actions) > 1:
        ap.error("Choose only one of --map-users, --restore-users, --check-users")
    try:
        config = load_config(
            args.auth, actions=tuple(user_actions or steps),
            onedrive_alias=args.onedrive_alias, source_dir=HERE,
        )
    except ConfigurationError as exc:
        ap.error(str(exc))
    g = Graph(args.auth, dry_run=args.dry_run, config=config)

    if args.map_users:
        map_users(g)
        return

    if args.restore_users:
        restore_users(g)
        return

    if args.check_users:
        aliases = [p["alias"] for p in load("emails.json")["people"]]
        found = resolve_users(g, aliases)
        print(f"\n{len(found)}/{len(aliases)} personas resolved")
        for a in aliases:
            print(f"  {'OK ' if a in found else 'MISS'}  {a:<18} -> {upn(a, config)}")
        if config.driver_alias:
            print(f"\ndemo driver: {config.driver_alias} -> {upn(config.driver_alias, config)}")
        return

    for s in steps:
        if s == "mail":
            seed_mail(g, purge=args.purge)
        elif s == "teams":
            if args.migrate:
                seed_teams_migration(g, recreate=args.recreate)
            else:
                seed_teams(g, messages_only=args.messages_only)
        elif s == "files":
            seed_files(g, args.onedrive_alias)

    print("\nDone. Allow 15-30 minutes for Microsoft 365 / Copilot indexing "
          "before querying through Work IQ.")


if __name__ == "__main__":
    main()
