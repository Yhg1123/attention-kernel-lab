import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qa_evidence import snapshot_sources, source_directory


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.code = self.root / "code"
        self.code.mkdir()
        (self.code / "app.py").write_bytes(b"version one\n")
        self.hashes = {"app.py": hashlib.sha256(b"version one\n").hexdigest()}
        self.run = self.root / "run"
        self.run.mkdir()

    def test_archived_result_survives_application_upgrade(self):
        snapshot_sources(self.run, self.hashes, self.code)
        (self.code / "app.py").write_bytes(b"version two\n")
        self.assertEqual(source_directory(self.run, self.hashes, self.code), self.run / "source")

    def test_corrupt_archive_cannot_be_hidden_by_good_current_code(self):
        snapshot_sources(self.run, self.hashes, self.code)
        (self.run / "source" / "app.py").write_bytes(b"modified\n")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            source_directory(self.run, self.hashes, self.code)

    def test_old_run_without_archive_requires_exact_current_source(self):
        self.assertEqual(source_directory(self.run, self.hashes, self.code), self.code)
        (self.code / "app.py").write_bytes(b"changed\n")
        with self.assertRaises(ValueError):
            source_directory(self.run, self.hashes, self.code)

    def test_manifest_cannot_escape_its_source_directory(self):
        for name in ("../secret", "..\\secret", "C:secret", "/secret", ""):
            with self.assertRaises(ValueError):
                source_directory(self.run, {name: "x"}, self.code)
