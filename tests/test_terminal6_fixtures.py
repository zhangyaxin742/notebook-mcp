import json
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "fixtures" / "terminal6"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"

FORBIDDEN_SECRET_PATTERNS = (
    re.compile(r"Bearer\s+[A-Za-z0-9._-]+"),
    re.compile(r"(?i)__Secure-[^=]+="),
    re.compile(r"(?i)SAPISID="),
    re.compile(r"(?i)HSID="),
    re.compile(r"(?i)SID="),
    re.compile(r"(?i)csrf[^\"'\n\r]{0,20}[:=][^<\n\r]{6,}"),
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class Terminal6FixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = load_json(MANIFEST_PATH)

    def test_manifest_references_existing_files(self) -> None:
        referenced_paths = self.manifest["canonical_examples"] + self.manifest["failure_mode_cases"]
        for relative_path in referenced_paths:
            with self.subTest(relative_path=relative_path):
                self.assertTrue((FIXTURE_ROOT / relative_path).exists())

    def test_canonical_examples_match_required_contract_fields(self) -> None:
        required_fields = {
            "notebook_record.json": {"id", "origin", "title", "url"},
            "source_record.json": {"id", "notebook_id", "origin", "title", "url", "source_type"},
            "artifact_record.json": {"id", "notebook_id", "origin", "artifact_kind", "title", "url"},
            "document_record.json": {
                "id",
                "notebook_id",
                "origin_type",
                "origin_id",
                "document_kind",
                "title",
                "text",
                "url",
                "content_sha256",
            },
            "chunk_record.json": {"id", "document_id", "notebook_id", "chunk_index", "text", "content_sha256"},
        }

        for relative_path in self.manifest["canonical_examples"]:
            path = FIXTURE_ROOT / relative_path
            payload = load_json(path)
            with self.subTest(relative_path=relative_path):
                self.assertTrue(required_fields[path.name].issubset(payload.keys()))
                self.assertTrue(str(payload["id"]).startswith("nlm:"))

        document_payload = load_json(FIXTURE_ROOT / "canonical" / "document_record.json")
        self.assertTrue(document_payload["id"].startswith("nlm:document:"))
        self.assertTrue(document_payload["url"].startswith("https://"))

        chunk_payload = load_json(FIXTURE_ROOT / "canonical" / "chunk_record.json")
        self.assertTrue(chunk_payload["id"].startswith("nlm:chunk:"))
        self.assertEqual(chunk_payload["chunk_index"], 0)

    def test_failure_mode_examples_cover_expected_classifications(self) -> None:
        expected = {
            "auth-expired.json": "auth_expired",
            "endpoint-drift.json": "endpoint_drift",
            "unsupported-shape.json": "unsupported_shape",
            "partial-sync.json": "partial_sync_failure",
            "fetch-not-found.json": "not_found",
        }

        for filename, classification in expected.items():
            payload = load_json(FIXTURE_ROOT / "failure-modes" / filename)
            with self.subTest(filename=filename):
                self.assertEqual(payload["expected_classification"], classification)
                self.assertEqual(payload["status"], "documented")
                self.assertTrue(payload["operator_action"])
                self.assertIn("redacted_observations", payload)

    def test_fixtures_do_not_contain_live_secrets(self) -> None:
        for path in FIXTURE_ROOT.rglob("*.json"):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=str(path.relative_to(REPO_ROOT))):
                for pattern in FORBIDDEN_SECRET_PATTERNS:
                    self.assertIsNone(pattern.search(text))

    def test_redacted_placeholders_exist_in_sensitive_failure_cases(self) -> None:
        sensitive_cases = [
            FIXTURE_ROOT / "failure-modes" / "auth-expired.json",
            FIXTURE_ROOT / "failure-modes" / "endpoint-drift.json",
            FIXTURE_ROOT / "failure-modes" / "unsupported-shape.json",
        ]

        for path in sensitive_cases:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=str(path.relative_to(REPO_ROOT))):
                self.assertIn("<redacted", text)


if __name__ == "__main__":
    unittest.main()
