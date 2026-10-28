import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
import zipfile

from file_operations import archive_helper


class CreateZipArchiveTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)

    def test_archives_503_files_without_an_external_command(self):
        source_dir = self.root / ("long-source-folder-" * 4)
        source_dir.mkdir()
        sources = []
        expected = {}
        for index in range(503):
            path = source_dir / f"document-{index:03d}.txt"
            content = f"Document {index}".encode()
            path.write_bytes(content)
            sources.append(str(path))
            expected[path.name] = content
        self.assertGreater(len(subprocess.list2cmdline(sources)), 32767)
        destination = self.root / "bundle.zip"

        with mock.patch.object(archive_helper.subprocess, "run", side_effect=AssertionError("No subprocess needed")):
            result = archive_helper._create_zip_archive(sources, str(destination))

        self.assertEqual(result, str(destination))
        with zipfile.ZipFile(destination) as archive:
            self.assertEqual(len(archive.infolist()), 503)
            self.assertEqual({name: archive.read(name) for name in archive.namelist()}, expected)
            self.assertIsNone(archive.testzip())

    def test_preserves_folders_empty_directories_and_literal_filenames(self):
        source = self.root / "Documents"
        (source / "nested" / "empty").mkdir(parents=True)
        filename = "Звіт [1] $value `text' .txt"
        (source / "nested" / filename).write_bytes(b"nested document")
        extra = self.root / "extra.txt"
        extra.write_bytes(b"extra document")
        destination = self.root / "bundle.zip"

        archive_helper._create_zip_archive([str(source), str(extra)], str(destination))

        with zipfile.ZipFile(destination) as archive:
            self.assertEqual(set(archive.namelist()), {
                "Documents/", "Documents/nested/", "Documents/nested/empty/",
                f"Documents/nested/{filename}", "extra.txt",
            })
            self.assertEqual(archive.read(f"Documents/nested/{filename}"), b"nested document")
            self.assertEqual(archive.read("extra.txt"), b"extra document")

    def test_single_file_uses_default_destination(self):
        source = self.root / "document.txt"
        source.write_bytes(b"document")

        result = archive_helper._create_zip_archive(str(source), None)

        self.assertEqual(result, str(source) + ".zip")
        with zipfile.ZipFile(result) as archive:
            self.assertEqual(archive.namelist(), [source.name])
            self.assertEqual(archive.read(source.name), b"document")

    def test_destination_inside_source_is_not_archived(self):
        source = self.root / "Documents"
        source.mkdir()
        (source / "document.txt").write_bytes(b"document")
        destination = source / "bundle.zip"
        destination.write_bytes(b"old archive")

        archive_helper._create_zip_archive(str(source), str(destination))

        with zipfile.ZipFile(destination) as archive:
            self.assertEqual(set(archive.namelist()), {"Documents/", "Documents/document.txt"})
        self.assertEqual(sorted(path.name for path in source.iterdir()), ["bundle.zip", "document.txt"])

    def test_failure_preserves_destination_and_cleans_temporary_archive(self):
        source = self.root / "document.txt"
        source.write_bytes(b"document")
        destination = self.root / "bundle.zip"
        destination.write_bytes(b"old archive")

        with mock.patch.object(zipfile.ZipFile, "write", side_effect=PermissionError("Cannot read source")):
            with self.assertRaises(PermissionError):
                archive_helper._create_zip_archive(str(source), str(destination))

        self.assertEqual(destination.read_bytes(), b"old archive")
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), ["bundle.zip", "document.txt"])

    def test_rejects_destination_equal_to_source_without_modifying_it(self):
        source = self.root / "document.txt"
        source.write_bytes(b"document")
        for selection in (str(source), [str(source)]):
            with self.subTest(selection=selection), self.assertRaises(ValueError):
                archive_helper._create_zip_archive(selection, str(source))
        self.assertEqual(source.read_bytes(), b"document")

    def test_rejects_missing_sources(self):
        source = str(self.root / "missing.txt")
        destination = str(self.root / "bundle.zip")
        for selection in (source, [source], []):
            with self.subTest(selection=selection), self.assertRaises(FileNotFoundError):
                archive_helper._create_zip_archive(selection, destination)
        self.assertFalse(os.path.exists(destination))


if __name__ == "__main__":
    unittest.main()
