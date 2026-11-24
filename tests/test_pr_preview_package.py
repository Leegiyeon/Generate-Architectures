"""Local release packaging must preserve inputs and keep unrelated files out."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from scripts import build_pr_preview as builder


class LocalPreviewPackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.output = self.root / "site"
        self.output.mkdir()

    def populate(self):
        source = Path(builder.__file__).resolve().parent.parent
        assets = [Path(path.name) for path in (source / "app/pr_preview").iterdir() if path.is_file()]
        assets += [Path("analyzer") / name for name in builder.MODULES]
        assets += [Path("pyodide") / name for name in (*builder.RUNTIME_FILES, "LICENSE")]
        for path in assets:
            target = self.output / path
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(b"fixture web asset")

    def test_archive_inside_web_output_preserves_input(self):
        archive = self.output / "python_stdlib.zip"
        archive.write_bytes(b"original runtime")
        with self.assertRaisesRegex(ValueError, "outside"):
            builder.package(self.output, archive)
        self.assertEqual(archive.read_bytes(), b"original runtime")

    def test_non_zip_destination_preserves_existing_file(self):
        archive = self.root / "notes.txt"
        archive.write_text("original notes")
        with self.assertRaisesRegex(ValueError, "extension"):
            builder.package(self.output, archive)
        self.assertEqual(archive.read_text(), "original notes")

    def test_write_failure_preserves_existing_archive_and_cleans_temporary_file(self):
        self.populate()
        archive = self.root / "release.zip"
        archive.write_bytes(b"previous release")
        with patch.object(builder.ZipFile, "write", side_effect=OSError("disk write failed")):
            with self.assertRaisesRegex(OSError, "disk write failed"):
                builder.package(self.output, archive)
        self.assertEqual(archive.read_bytes(), b"previous release")
        self.assertEqual(list(self.root.glob(".release.zip.*.tmp")), [])

    def test_unrelated_files_are_excluded_and_launchers_are_present(self):
        self.populate()
        (self.output / ".env").write_text("NOT_A_REAL_SECRET=test")
        (self.output / "old-report.txt").write_text("unrelated report")
        archive = self.root / "release.zip"
        builder.package(self.output, archive)
        with ZipFile(archive) as bundle:
            self.assertIsNone(bundle.testzip())
            names = bundle.namelist()
            self.assertIn("fastapi-pr-review/site/index.html", names)
            self.assertIn("fastapi-pr-review/site/analyzer/pr_preview_structure.py", names)
            self.assertIn("fastapi-pr-review/start.py", names)
            self.assertFalse(any(".env" in name or "old-report" in name for name in names))
            self.assertTrue(bundle.getinfo("fastapi-pr-review/START.command").external_attr >> 16 & 0o111)


if __name__ == "__main__":
    unittest.main()
