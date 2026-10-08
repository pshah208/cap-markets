import os
import socket
import subprocess
import sys
from unittest.mock import patch

from tests.offline import OfflineAsyncTestCase, OfflineTestCase, OfflineViolation


class SafetyTests(OfflineTestCase):
    def test_ambient_environment_is_removed(self):
        self.assertEqual(dict(os.environ), {})
        self.assertTrue(sys.dont_write_bytecode)

    def test_network_dns_subprocess_and_credentials_are_blocked(self):
        import azure.identity
        import azure.identity.aio
        import jwt

        with socket.socket() as sock:
            operations = (
                lambda: sock.connect(("192.0.2.1", 443)),
                lambda: sock.connect_ex(("192.0.2.1", 443)),
                lambda: socket.getaddrinfo("example.invalid", 443),
                lambda: subprocess.Popen(["az", "account", "get-access-token"]),
                lambda: os.system("az account show"),
                azure.identity.DefaultAzureCredential,
                azure.identity.aio.DefaultAzureCredential,
                lambda: jwt.PyJWKClient("https://example.invalid/keys").fetch_data(),
            )
            for operation in operations:
                with self.assertRaises(OfflineViolation):
                    operation()

    def test_blocker_cannot_be_hidden_by_application_exception_handlers(self):
        caught = False
        with self.assertRaises(OfflineViolation):
            try:
                socket.getaddrinfo("example.invalid", 443)
            except Exception:
                caught = True
        self.assertFalse(caught)

    def test_test_imports_do_not_authenticate_or_change_environment(self):
        import importlib
        before = dict(os.environ)
        with patch.dict(os.environ, {"AZURE_CLIENT_SECRET": "ambient-test-secret"}):
            importlib.import_module("tests.test_bank_neutral")
            importlib.import_module("tests.test_config")
            self.assertEqual(os.environ["AZURE_CLIENT_SECRET"], "ambient-test-secret")
        self.assertEqual(dict(os.environ), before)


class TransportSafetyTests(OfflineAsyncTestCase):
    async def test_real_transports_fail_but_in_memory_transports_work(self):
        import httpx
        with httpx.Client(trust_env=False) as client:
            with self.assertRaises(OfflineViolation):
                client.get("https://example.invalid")
        async with httpx.AsyncClient(trust_env=False) as client:
            with self.assertRaises(OfflineViolation):
                await client.get("https://example.invalid")
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"inMemory": True}))
        async with httpx.AsyncClient(transport=transport) as client:
            self.assertTrue((await client.get("https://example.invalid")).json()["inMemory"])
