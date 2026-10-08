import copy
import importlib
import io
import json
import runpy
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

from tests.offline import OfflineAsyncTestCase, OfflineTestCase


BFF = Path(__file__).resolve().parents[1]


def event_data(frame):
    return json.loads(next(line[6:] for line in frame.splitlines() if line.startswith("data: ")))


class CanonicalTextTests(OfflineTestCase):
    def setUp(self):
        super().setUp()
        self.names = importlib.import_module("app.bank_name")
        self.iq = importlib.import_module("app.iq")

    def test_canonical_prose_is_meaningful_and_idempotent(self):
        cases = {
            "": "",
            "the bank lends. the Bank reviews.": "The Bank lends. The Bank reviews.",
            "Ask The Bank about the the bank's role.": "Ask the Bank about the Bank's role.",
            "# the bank\n- the Bank\n1. the bank\n| the bank |": "# The Bank\n- The Bank\n1. The Bank\n| The Bank |",
            "**the bank** and the bank’s hold": "**The Bank** and the Bank’s hold",
            "A bank, a riverbank and bank_role": "A bank, a riverbank and bank_role",
            "Example Credit Union and the bank": "Example Credit Union and the Bank",
        }
        for original, expected in cases.items():
            with self.subTest(original=original):
                actual = self.names.normalize_bank_text(original)
                self.assertEqual(actual, expected)
                self.assertEqual(self.names.normalize_bank_text(actual), actual)

    def test_protected_code_links_and_citation_ids_are_byte_exact(self):
        protected = (
            "https://example.invalid/the%20bank?file=the_bank#the-bank",
            "`the bank`", "```json\n{\"id\": \"the bank\"}\n```",
            "~~~\nthe bank\n~~~", "【the bank:source-1】", "[^the bank]",
            "``literal `the bank` value``", "````json\n```\nthe bank\n```\n````",
            '    value = "the bank"\n', '\tvalue = "the bank"\n',
            '```json\n{"id": "the bank"}',
            "[the bank-id]", "[doc](<../the bank/file (1).pdf>)",
            '[doc](https://example.invalid/file "the bank")',
            '[source]: <../the bank/file.pdf> "the bank"',
            '<a href="../the bank/file" id="the bank">link</a>',
        )
        for value in protected:
            with self.subTest(value=value):
                self.assertEqual(self.names.normalize_bank_text(value), value)
        self.assertEqual(
            self.names.normalize_bank_text("[the bank](https://example.invalid/the_bank) lends."),
            "[The Bank](https://example.invalid/the_bank) lends.",
        )
        self.assertEqual(
            self.names.normalize_bank_text("Read `the bank`. the bank responds."),
            "Read `the bank`. The Bank responds.",
        )

    def test_citation_display_only_without_mutating_sources(self):
        citations = [{
            "id": "the bank", "fileId": "the bank/source-id",
            "url": "https://example.invalid/the_bank?q=the%20bank",
            "title": "the bank's policy", "snippet": "Ask the bank.", "text": "the bank agrees.",
            "start_index": 8, "end_index": 16, "metadata": {"id": "the bank"},
        }, {"title": None, "snippet": 4, "kind": "file"}]
        original = copy.deepcopy(citations)
        result = self.names.normalize_citations(citations)
        self.assertEqual(citations, original)
        self.assertIsNot(result[0], citations[0])
        self.assertEqual(result[0]["title"], "The Bank's policy")
        self.assertEqual(result[0]["snippet"], "Ask the Bank.")
        self.assertEqual(result[0]["text"], "The Bank agrees.")
        for key in ("id", "fileId", "url", "start_index", "end_index", "metadata"):
            self.assertEqual(result[0][key], original[0][key])
        self.assertEqual(result[1], original[1])
        self.assertEqual(self.names.normalize_citations(None), [])

    def test_stream_chunks_preserve_boundaries_and_final_message_normalizes(self):
        chunks = ["Ask ", "the", " bank", ". ", "the bank", " agrees. ",
                  "https://example.invalid/", "the", "_bank"]
        frames = [event_data(self.iq.token_event(chunk))["text"] for chunk in chunks]
        self.assertEqual("".join(frames), "".join(chunks))
        final = event_data(self.iq.message_event("".join(chunks)))
        self.assertEqual(final["text"],
                         "Ask the Bank. The Bank agrees. https://example.invalid/the_bank")

    def test_foundry_citation_collection_keeps_urls_and_file_ids(self):
        agent = importlib.import_module("app.agent_client")
        url = "https://source.example.invalid/the_bank?x=the%20bank"
        file_id = "the bank-file-42"
        annotation = {"type": "url_citation", "url": url, "title": "the bank report"}
        payload = {"output": [{"content": [{"annotations": [
            annotation, copy.deepcopy(annotation),
            {"type": "file_citation", "file_id": file_id, "filename": "the bank policy"},
        ]}]}]}
        original = copy.deepcopy(payload)
        citations = agent._collect_citations(payload)
        result = event_data(self.iq.message_event("the bank cites evidence.", citations))
        self.assertEqual(payload, original)
        self.assertEqual(len(result["citations"]), 2)
        self.assertEqual(result["citations"][0]["url"], url)
        self.assertEqual(result["citations"][1]["fileId"], file_id)
        self.assertEqual(result["citations"][0]["title"], "The Bank report")


class SchemaTests(OfflineTestCase):
    def setUp(self):
        super().setUp()
        self.skill = importlib.import_module("app.skill_data").SKILL_DATA

    def test_generated_contract_and_approval_calculations(self):
        opportunities = self.skill["opportunities"]
        rev = opportunities["revolver_upsize"]
        self.assertEqual(rev["bank_current_hold_m"], 165.0)
        self.assertEqual(rev["bank_proposed_hold_m"], 210.0)
        self.assertIn("bank_role", rev)
        self.assertIn("bank_role", opportunities["dcm_followon"])
        self.assertEqual({k for k in rev if k.endswith("_hold_m")},
                         {"bank_current_hold_m", "bank_proposed_hold_m"})
        papers = importlib.import_module("app.papers")
        bundle = papers.build()
        self.assertEqual(bundle["inputs"]["hold_m"], 187.5)
        text = json.dumps(bundle)
        self.assertIn("The Bank's role", text)
        self.assertIn(rev["bank_role"], text)
        self.assertIn("The Bank's hold", text)
        self.assertIn("CP-005", text)
        from docx import Document
        document = Document(io.BytesIO(papers.to_docx(bundle)))
        rendered = "\n".join(cell.text for table in document.tables
                             for row in table.rows for cell in row.cells)
        self.assertIn("The Bank's role", rendered)

    def load_generator(self, name, facts=None):
        stub = ModuleType("scenario_facts")
        stub.FACTS = facts or {}
        stub.PEOPLE = []
        with patch.dict(sys.modules, {"scenario_facts": stub}), patch.object(sys, "path", sys.path.copy()):
            return runpy.run_path(str(BFF / name))

    def test_market_generator_requires_canonical_wallet_column(self):
        generator = self.load_generator("generate_market_data.py")
        build = generator["build"]
        wallet = {"client_id": "CLI-TEST", "estimated_street_wallet_cad_k": "200",
                  "bank_revenue_cad_k": "50"}
        rows = {"clients.csv": [{"client_id": "CLI-TEST", "last_meeting_date": "2026-01-01",
                                "relationship_owner_alias": "owner", "coverage_banker_alias": "banker"}],
                "wallet_share.csv": [wallet]}
        scenario = {"as_of": "2026-01-02", "id": "test"}

        def read(path, **kwargs):
            return json.dumps({"emails": []} if path.name == "emails.json" else scenario)

        with patch.dict(build.__globals__, {"rows": lambda name: rows.get(name, []),
                                            "_sensitivity": lambda: {}}), \
             patch.object(Path, "read_text", autospec=True, side_effect=read), \
             patch.object(Path, "glob", return_value=[]):
            self.assertEqual(build()["extra"]["CLI-TEST"]["wallet_share_pct"], 25.0)
            del wallet["bank_revenue_cad_k"]
            with self.assertRaisesRegex(KeyError, "bank_revenue_cad_k"):
                build()

    def test_skill_generator_requires_canonical_attendee_and_role_keys(self):
        d = self.skill
        facts = {
            "hero_client_id": d["client"]["id"], "hero_client_name": d["client"]["name"],
            "hero_ticker": d["client"]["ticker"], "as_of": d["client"]["as_of"],
            "currency": d["client"]["currency"], "client_financials": d["financials"],
            "covenant_tension": {"covenant": d["covenant"]["name"], **d["covenant"],
                                 "prior_quarter_actual": d["covenant"]["prior"]},
            "mnpi_tension": {**d["restriction"], "restricted_persons": []},
            "meeting": {**d["meeting"], "bank_attendees": []},
            "opportunities": d["opportunities"], "hero_metrics": d["metrics"],
        }
        build = self.load_generator("generate_skill_data.py", facts)["build"]
        facility = {"client_id": d["client"]["id"], "facility_id": "FAC-TEST",
                    "facility_type": "Revolver", "commitment_cad_m": "100",
                    "drawn_cad_m": "50", "maturity_date": "2027-01-01", "bank_role": "Arranger"}
        with patch.dict(build.__globals__, {"rows": lambda name: [facility] if name == "credit_facilities.csv" else []}), \
             patch.object(Path, "read_text", return_value='{"companies": []}'):
            result = build()
            self.assertEqual(result["facilities"][0]["role"], "Arranger")
            self.assertEqual(result["opportunities"]["revolver_upsize"]["bank_current_hold_m"], 165.0)
            del facility["bank_role"]
            with self.assertRaisesRegex(KeyError, "bank_role"):
                build()
            facility["bank_role"] = "Arranger"
            del facts["meeting"]["bank_attendees"]
            with self.assertRaisesRegex(KeyError, "bank_attendees"):
                build()


class BootstrapTests(OfflineAsyncTestCase):
    def setUp(self):
        super().setUp()
        self.main = importlib.import_module("app.main")
        self.auth = importlib.import_module("app.auth")
        self.cfg = importlib.import_module("app.config").Settings()
        for module in (self.main, self.auth):
            patcher = patch.object(module, "settings", self.cfg)
            patcher.start()
            self.addCleanup(patcher.stop)

    async def test_public_bootstrap_and_story_are_canonical_not_environment_branded(self):
        import httpx
        with patch.dict("os.environ", {"BANK_NAME": "Ignored Brand", "BANK_DISPLAY_NAME": "Ignored Brand"}):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.main.app),
                                         base_url="http://test.invalid") as client:
                cfg = (await client.get("/api/config")).json()
                story = (await client.get("/api/story")).json()
                health = (await client.get("/health")).json()
                denied = await client.get("/api/skills")
        self.assertEqual(cfg["bank"], "The Bank")
        self.assertIn("The Bank is a fictional institution", cfg["disclaimer"])
        self.assertEqual(story["persona"]["org"], "The Bank")
        self.assertNotIn("Ignored Brand", json.dumps([cfg, story]))
        self.assertNotIn("secret", json.dumps(cfg).lower())
        self.assertFalse(health["authConfigured"])
        self.assertFalse(health["agentConfigured"])
        self.assertEqual(denied.status_code, 401)

    async def test_health_requires_agent_name_and_diagnostics_fail_before_auth(self):
        self.cfg.project_endpoint = "https://project.example.invalid/projects/test"
        self.assertFalse((await self.main.health())["agentConfigured"])
        user = self.auth.User({"name": "Test User", "oid": "test"}, "")
        result = await self.main.diag(user)
        self.assertFalse(result["checks"][-1]["ok"])
        self.assertEqual(result["checks"][-1]["check"], "agent configuration")
        self.assertEqual(result["settings"]["projectEndpoint"], self.cfg.project_endpoint)
        self.cfg.agent_name = "configured-agent"
        self.assertTrue((await self.main.health())["agentConfigured"])
        self.cfg.project_endpoint = "https://user:private-secret@example.invalid"
        result = await self.main.diag(user)
        self.assertNotIn("private-secret", json.dumps(result))
        self.assertEqual(result["settings"]["projectEndpoint"], "(invalid)")

    async def test_mock_profile_is_explicit_and_neutral(self):
        from starlette.requests import Request
        self.cfg.mock_mode = True
        user = await self.auth.current_user(Request({"type": "http", "headers": []}))
        profile = await self.main.me(user)
        self.assertEqual(profile["name"], "Demo User (mock)")
        self.assertEqual(profile["department"], "Capital Markets")
        self.assertEqual(profile["jobTitle"], "Coverage Banker (mock)")
        result = await self.main.diag(user)
        self.assertIn("Azure calls are bypassed", result["checks"][-1]["detail"])
