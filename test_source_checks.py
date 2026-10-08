"""Native source-only regression tests; no service access or file writes."""

from __future__ import annotations

import importlib.util
import io
from pathlib import Path
from contextlib import redirect_stdout
import subprocess
import unittest
from unittest.mock import Mock, patch

import check_loaders
import preflight
import scan_leakage

ROOT = Path(__file__).resolve().parent


class SourceCheckTests(unittest.TestCase):
    def setUp(self):
        self.network = patch("socket.socket", side_effect=AssertionError("network forbidden"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def test_loader_commands_are_explicitly_offline_and_preserve_existing_checks(self):
        commands = check_loaders.commands()
        generators = [cmd for _, cmd, _ in commands if "--check" in cmd]
        self.assertEqual(len(generators), 6)
        self.assertTrue(all("-B" in cmd for cmd in generators))
        self.assertTrue(any("--local-smoke" in cmd for _, cmd, _ in commands))
        self.assertTrue(any(cmd == ["node", "--test", "dashboard.test.mjs"]
                            for _, cmd, _ in commands))
        for _, cmd, _ in commands:
            self.assertNotIn("--tenant", cmd)
            self.assertNotIn("--create", cmd)
            self.assertNotIn("--all", cmd)

    def test_missing_tool_or_failed_generator_fails_loader_check(self):
        for result in (OSError("tool missing"), subprocess.CompletedProcess([], 1)):
            with self.subTest(result=result), patch.object(
                check_loaders, "commands", return_value=[("test check", ["python"], ROOT)]
            ), patch.object(
                check_loaders.subprocess, "run",
                **({"side_effect": result} if isinstance(result, OSError)
                   else {"return_value": result})
            ), redirect_stdout(io.StringIO()):
                self.assertEqual(check_loaders.main(), 1)

    def test_successful_checks_run_without_suppressing_failures(self):
        with patch.object(check_loaders.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0)) as run, \
                redirect_stdout(io.StringIO()):
            self.assertEqual(check_loaders.main(), 0)
        self.assertEqual(run.call_count, len(check_loaders.commands()))
        self.assertTrue(all(call.kwargs["env"]["PYTHONDONTWRITEBYTECODE"] == "1"
                            for call in run.call_args_list))

    def test_preflight_registers_real_loader_checker(self):
        command = next(cmd for label, cmd in preflight.SOURCE if label == "loaders + frontend")
        self.assertEqual(Path(command[-1]), ROOT / "check_loaders.py")
        self.assertTrue(Path(command[-1]).is_file())
        self.assertFalse(any("--tenant" in cmd for _, cmd in preflight.SOURCE))

    def test_publishable_inventory_uses_git_ignore_rules_but_keeps_tracked_files(self):
        result = Mock(stdout=b"data/facts.json\0data/facts.json\0node_modules/a.json\0")
        with patch.object(scan_leakage.subprocess, "run", return_value=result) as run:
            self.assertEqual(scan_leakage.publishable_files(ROOT), [ROOT / "data" / "facts.json"])
        command = run.call_args.args[0]
        for flag in ("--cached", "--others", "--exclude-standard", "-z"):
            self.assertIn(flag, command)
        self.assertTrue(run.call_args.kwargs["check"])

    def test_private_mapping_and_output_artifacts_cannot_be_published(self):
        for filename in ("user_mapping.json", "scope.local.json", ".env",
                         ".env.production", "user_mapping.restore.json",
                         "fabric-deployment.json", "brand/generated/config.json",
                         ".device_token_cache.json", "a/.msal_token_cache.bin",
                         "a/.identity/cache", ".tokens.json",
                         "app/src/web/public/brand/bank.json",
                         "app/src/web/public/brand/logo.png",
                         "app/src/web/public/brand/user-logo.svg"):
            self.assertTrue(scan_leakage.private_artifact(Path(filename)), filename)
        for filename in ("user_mapping.example.json", ".env.example", ".env.template"):
            self.assertFalse(scan_leakage.private_artifact(Path(filename)), filename)
        private = ROOT / "data" / "user_mapping.json"
        with patch.object(scan_leakage, "publishable_files", return_value=[private]), \
                patch.object(Path, "exists", return_value=True), \
                patch.object(Path, "read_text", side_effect=AssertionError("private read")):
            _, _, failures = scan_leakage.scan(ROOT)
        self.assertIn("private artifact", failures)

    def test_unstaged_private_deletion_still_fails_without_reading_index(self):
        private = ROOT / ".env"
        with patch.object(scan_leakage, "publishable_files", return_value=[private]), \
                patch.object(Path, "exists", return_value=False), \
                patch.object(Path, "read_text", side_effect=AssertionError("private read")):
            _, _, failures = scan_leakage.scan(ROOT)
        self.assertIn("private artifact", failures)

    def test_removed_nonprivate_source_has_no_working_tree_content_to_scan(self):
        source = ROOT / "data" / "facts.json"
        with patch.object(scan_leakage, "publishable_files", return_value=[source]), \
                patch.object(Path, "exists", return_value=False):
            _, _, failures = scan_leakage.scan(ROOT)
        self.assertEqual(failures, {})

    def test_foreign_content_and_explicit_institution_terms_fail(self):
        source = ROOT / "data" / "facts.json"
        with patch.object(scan_leakage, "publishable_files", return_value=[source]), \
                patch.object(Path, "exists", return_value=True), \
                patch.object(Path, "read_text", return_value="contoso - Fictional Test Institution"):
            _, _, failures = scan_leakage.scan(ROOT, ("Fictional Test Institution",))
        self.assertEqual(set(failures), {"contoso", "Fictional Test Institution"})

    def test_canonical_bank_and_public_clients_are_not_leakage(self):
        source = ROOT / "data" / "facts.json"
        text = "The Bank covers Gibson Energy; the Bank reviews facility renewals and M&A Advisory."
        with patch.object(scan_leakage, "publishable_files", return_value=[source]), \
                patch.object(Path, "exists", return_value=True), \
                patch.object(Path, "read_text", return_value=text):
            _, _, failures = scan_leakage.scan(ROOT)
        self.assertEqual(failures, {})

    def test_source_read_and_inventory_errors_never_report_clean(self):
        for error in (OSError("cannot read"), UnicodeError("invalid UTF-8"),
                      subprocess.CalledProcessError(1, "git")):
            with self.subTest(error=error), \
                    patch.object(scan_leakage, "scan", side_effect=error), \
                    redirect_stdout(io.StringIO()) as output:
                self.assertEqual(scan_leakage.main([]), 2)
                self.assertNotIn("CLEAN", output.getvalue())


class BriefCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("check_brief", ROOT / "docs" / "check_brief.py")
        cls.brief = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.brief)

    def check_text(self, text):
        xml = (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
        ).encode()
        with patch.object(self.brief.zipfile, "ZipFile") as archive, \
                redirect_stdout(io.StringIO()):
            archive.return_value.__enter__.return_value.read.return_value = xml
            return self.brief.check_document(Path("fixture.docx"))

    def test_brief_uses_current_scenario_facts(self):
        self.assertEqual(self.check_text(
            "500 341.7 68.3% 21.4% IG-6 4.18 4.50 Synthetic demonstration data"
        ), 0)

    def test_missing_facts_fail_instead_of_printing_success(self):
        self.assertEqual(self.check_text("Unrelated document"), 1)


if __name__ == "__main__":
    unittest.main()
