"""Exercise the real Windows New handler and its integration without opening Office."""

from dataclasses import replace
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from file_operations import create_item, shell_new


class ShellNewTests(unittest.TestCase):
    def test_native_entries_preserve_labels_separators_and_owned_icons(self):
        with tempfile.TemporaryDirectory() as directory:
            entries = shell_new.items(directory)
        self.assertEqual([item.verb for item in entries[:2]], ["NewFolder", "NewLink"])
        self.assertTrue(any(item.separator for item in entries))
        for item in entries:
            if item.separator:
                continue
            self.assertTrue(item.label)
            self.assertNotIn("\ufffd", item.label)
            self.assertIsNotNone(item.icon, item.label)
            width, height, pixels = item.icon
            self.assertEqual(len(pixels), width * height * 4)
            self.assertTrue(any(pixels[3::4]))
        # These RGBA bytes remain valid after the native menu and its bitmaps are freed.
        self.assertNotEqual(entries[0].icon, entries[1].icon)

    def test_native_templates_create_files_without_overwriting(self):
        from zipfile import ZipFile

        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / "Нові документи 日本語"
            directory.mkdir()
            entries = shell_new.items(str(directory))
            supported = [entry for entry in entries if entry.verb in (".txt", ".bmp", ".docx", ".xlsx")]
            self.assertTrue(supported)
            for entry in supported:
                with self.subTest(type=entry.verb):
                    before = set(directory.iterdir())
                    shell_new.invoke(str(directory), entry)
                    created = set(directory.iterdir()) - before
                    self.assertEqual(len(created), 1)
                    path = created.pop()
                    self.assertEqual(path.suffix.lower(), entry.verb)
                    content = path.read_bytes()
                    # Word can register NullFile; Explorer intentionally creates an
                    # empty file for Word to initialize when it is first opened.
                    if content and entry.verb in (".docx", ".xlsx"):
                        with ZipFile(path) as archive:
                            self.assertIsNone(archive.testzip())
                            self.assertIn("[Content_Types].xml", archive.namelist())
                    shell_new.invoke(str(directory), entry)
                    self.assertEqual(path.read_bytes(), content)
                    self.assertEqual(len(set(directory.iterdir()) - before), 2)

    def test_stale_command_cannot_invoke_another_type(self):
        with tempfile.TemporaryDirectory() as directory, shell_new.NativeNewMenu(directory) as menu:
            entry = menu.items(include_icons=False)[0]
            with self.assertRaises(OSError):
                menu.invoke(replace(entry, verb="changed registration"))
            self.assertEqual(os.listdir(directory), [])

    def test_repeated_enumeration_releases_native_menus_and_bitmaps(self):
        import ctypes as ct

        user = ct.WinDLL("user32")
        user.GetGuiResources.argtypes = [ct.c_void_p, ct.c_uint32]
        user.GetGuiResources.restype = ct.c_uint32
        process = ct.c_void_p(-1)  # GetCurrentProcess pseudo-handle
        with tempfile.TemporaryDirectory() as directory:
            shell_new.items(directory)  # Allow Shell image caches to initialize.
            before = [user.GetGuiResources(process, kind) for kind in (0, 1)]
            for _ in range(12):
                shell_new.items(directory)
            after = [user.GetGuiResources(process, kind) for kind in (0, 1)]
            for initial, final in zip(before, after):
                self.assertLessEqual(final, initial + 2)

    def test_folder_and_shortcut_use_existing_dialogs(self):
        with tempfile.TemporaryDirectory() as directory:
            context = SimpleNamespace(source="list", current_folder=directory)
            for verb, kind in (("NewFolder", "folder"), ("NewLink", "shortcut")):
                with mock.patch.object(create_item, "run") as run:
                    create_item.run_shell(context, shell_new.NewItem(1, "Native label", verb))
                    run.assert_called_once_with(context, kind)

    def test_cancel_rename_keeps_shell_default_name(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "New document.txt"
            path.write_text("template content")
            owner = SimpleNamespace()
            with mock.patch.object(create_item, "_prompt", return_value=None), \
                 mock.patch.object(create_item, "_refresh_created") as refresh:
                create_item._finish_shell_creation(owner, directory, set())
            self.assertEqual(path.read_text(), "template content")
            refresh.assert_called_once_with(owner, directory, str(path))

    def test_ambiguous_new_files_are_not_renamed(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ("created.txt", "unrelated.txt"):
                (Path(directory) / name).touch()
            with mock.patch.object(create_item, "_prompt") as prompt, \
                 mock.patch.object(create_item, "_refresh_created"):
                create_item._finish_shell_creation(SimpleNamespace(), directory, set())
                prompt.assert_not_called()

    def test_async_creation_does_not_navigate_back_after_user_leaves(self):
        from controls import filelist

        with tempfile.TemporaryDirectory() as directory:
            owner = SimpleNamespace(_list_folder_path="another folder")
            with mock.patch.object(create_item, "_prompt") as prompt, \
                 mock.patch.object(filelist, "_refresh_after_fs_change") as refresh:
                create_item._finish_shell_creation(owner, directory, set(), expected_folder=directory)
                prompt.assert_not_called()
                refresh.assert_called_once_with(owner, affected_dirs=[directory])


if __name__ == "__main__":
    unittest.main()
