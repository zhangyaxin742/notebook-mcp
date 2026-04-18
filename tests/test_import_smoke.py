from __future__ import annotations

import importlib
import unittest


CRITICAL_MODULES = (
    "src.auth",
    "src.auth.bootstrap",
    "src.auth.cli",
    "src.auth.config",
    "src.auth.endpoint_capture",
    "src.auth.models",
    "src.auth.scrub",
    "src.auth.service",
    "src.auth.storage",
    "src.index",
    "src.index.chunking",
    "src.index.embeddings",
    "src.index.lexical",
    "src.mcp_server",
    "src.mcp_server.__main__",
    "src.mcp_server.backend",
    "src.mcp_server.http",
    "src.mcp_server.protocol",
    "src.mcp_server.tools",
    "src.mcp_server.validate_transport",
    "src.notebooklm_client",
    "src.notebooklm_client.connector",
    "src.notebooklm_client.endpoints",
    "src.notebooklm_client.errors",
    "src.notebooklm_client.http_connector",
    "src.notebooklm_client.models",
    "src.notebooklm_client.playwright_connector",
    "src.retrieval",
    "src.retrieval.models",
    "src.retrieval.repository",
    "src.retrieval.service",
    "src.store",
    "src.store.chunk_repository",
    "src.store.document_repository",
    "src.store.ids",
    "src.store.models",
    "src.store.settings",
    "src.store.snapshots",
    "src.store.sqlite_store",
    "src.sync",
    "src.sync.chunks",
    "src.sync.normalize",
    "src.sync.reindex",
    "src.sync.service",
    "src.sync.types",
)


class ImportSmokeTests(unittest.TestCase):
    def test_critical_modules_import_cleanly(self) -> None:
        for module_name in CRITICAL_MODULES:
            with self.subTest(module_name=module_name):
                module = importlib.import_module(module_name)
                self.assertIsNotNone(module)

    def test_package_exports_resolve_expected_public_symbols(self) -> None:
        retrieval = importlib.import_module("src.retrieval")
        sync = importlib.import_module("src.sync")
        store = importlib.import_module("src.store")

        self.assertTrue(hasattr(retrieval, "RetrievalService"))
        self.assertTrue(hasattr(sync, "NotebookSyncService"))
        self.assertTrue(hasattr(store, "SQLiteStore"))


if __name__ == "__main__":
    unittest.main()
