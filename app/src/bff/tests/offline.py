"""Fail closed on network, credential or child-process access during tests."""

import os
import platform
import socket
import subprocess
import sys
import unittest
from contextlib import ExitStack
from unittest.mock import patch


class OfflineViolation(BaseException):
    """Cannot be swallowed by application best-effort Exception handlers."""


def blocked(*args, **kwargs):
    raise OfflineViolation("Offline tests prohibit network, credentials and subprocesses.")


class _Offline:
    def setUp(self):
        super().setUp()
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.dict(os.environ, {}, clear=True))
        stack.enter_context(patch.object(sys, "dont_write_bytecode", True))
        for target, attribute in (
            (socket.socket, "connect"), (socket.socket, "connect_ex"),
            (socket.socket, "sendto"), (socket, "getaddrinfo"),
            (subprocess, "Popen"), (os, "system"),
        ):
            stack.enter_context(patch.object(target, attribute, blocked))

        # Azure's user-agent construction invokes platform.platform(), which
        # may shell out on Windows. Test metadata must not launch a process.
        stack.enter_context(patch.object(platform, "platform", return_value="offline-tests"))

        import httpx
        import jwt
        import azure.identity
        import azure.identity.aio

        for target, attribute in (
            (httpx.HTTPTransport, "handle_request"),
            (httpx.AsyncHTTPTransport, "handle_async_request"),
            (jwt.PyJWKClient, "fetch_data"),
            (azure.identity, "DefaultAzureCredential"),
            (azure.identity.aio, "DefaultAzureCredential"),
        ):
            stack.enter_context(patch.object(target, attribute, blocked))


class OfflineTestCase(_Offline, unittest.TestCase):
    pass


class OfflineAsyncTestCase(_Offline, unittest.IsolatedAsyncioTestCase):
    pass
