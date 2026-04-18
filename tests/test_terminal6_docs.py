import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def read_text(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8").lower()


class Terminal6DocsTests(unittest.TestCase):
    def test_setup_doc_covers_required_operator_flows(self) -> None:
        setup_doc = read_text("docs/setup.md")
        for required_term in ("setup", "login", "sync", "reindex", "serve", "validation"):
            with self.subTest(required_term=required_term):
                self.assertIn(required_term, setup_doc)

    def test_runbook_documents_main_failure_modes_and_gaps(self) -> None:
        runbook_doc = read_text("docs/runbook.md")
        for required_term in (
            "auth expired",
            "endpoint drift",
            "unsupported shape",
            "partial sync",
            "not found",
            "testing gaps",
            "limitations",
        ):
            with self.subTest(required_term=required_term):
                self.assertIn(required_term, runbook_doc)

    def test_production_readiness_checklist_distinguishes_modes(self) -> None:
        readiness_doc = read_text("docs/setup-production-readiness.md")
        for required_term in (
            "prototype mode",
            "real deployment mode",
            "local-dev readiness",
            "private self-hosted readiness",
            "remote-exposed readiness",
            "bearer",
            "allowed origins",
        ):
            with self.subTest(required_term=required_term):
                self.assertIn(required_term, readiness_doc)

    def test_status_file_is_present_and_factual(self) -> None:
        status_doc = read_text("docs/status/terminal-6.md")
        for required_term in ("current scope", "files owned", "current blocker", "last meaningful change"):
            with self.subTest(required_term=required_term):
                self.assertIn(required_term, status_doc)


if __name__ == "__main__":
    unittest.main()
