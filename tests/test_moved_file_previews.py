"""Cross-workspace cut/paste closes stale previews after real file moves."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from controls import file_preview
from file_operations import copy_and_paste


class MovedFilePreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.source = root / "source"
        self.destination = root / "destination"
        self.source.mkdir()
        self.destination.mkdir()
        self.file = self.source / "document.txt"
        self.file.write_text("previewed content")
        self.other = self.destination / "other.txt"
        self.other.write_text("other preview")
        self.first = self.workspace(self.file)
        self.second = self.workspace(self.other)
        self.host = SimpleNamespace(workspaces=[self.first, self.second], active_workspace=self.second)
        self.first.host = self.second.host = self.host
        self.addCleanup(patch.stopall)
        patch.object(file_preview, "_render_preview_tab_bar").start()
        patch.object(file_preview, "update_preview_toolbar_visibility").start()
        patch.object(copy_and_paste.wx, "MessageBox").start()

    def workspace(self, path):
        return SimpleNamespace(current_preview_path=str(path), current_preview_mode="text",
                               preview_tabs=[{"path": str(path), "pinned": True}],
                               preview_active_tab_index=0, _html_preview_request=object())

    def paste(self, paths=None, mode="cut", **kwargs):
        paths = [str(path) for path in (paths or [self.file])]
        with patch.object(copy_and_paste, "_read_native_clipboard", return_value=(paths, mode)):
            copy_and_paste.paste_into_path(self.second, str(self.destination),
                                          refresh_callback=Mock(), update_toolbar_callback=Mock(), **kwargs)

    def test_cut_closes_source_preview_without_changing_destination_preview(self):
        self.paste()
        self.assertFalse(self.file.exists())
        self.assertEqual((self.destination / self.file.name).read_text(), "previewed content")
        self.assertEqual(self.first.preview_tabs, [])
        self.assertIsNone(self.first.preview_active_tab_index)
        self.assertIsNone(self.first.current_preview_path)
        self.assertEqual(self.first.current_preview_mode, "empty")
        self.assertIsNone(self.first._html_preview_request)
        self.assertEqual(self.second.current_preview_path, str(self.other))
        self.assertEqual(self.second.current_preview_mode, "text")
        self.assertIs(self.host.active_workspace, self.second)

    def test_copy_keeps_source_preview(self):
        self.paste(mode="copy")
        self.assertTrue(self.file.exists())
        self.assertEqual(self.first.current_preview_path, str(self.file))
        self.assertEqual(len(self.first.preview_tabs), 1)

    def test_failed_move_keeps_source_preview(self):
        with patch.object(copy_and_paste.shutil, "move", side_effect=OSError("Locked file")):
            self.paste()
        self.assertTrue(self.file.exists())
        self.assertEqual(self.first.current_preview_path, str(self.file))
        self.assertEqual(len(self.first.preview_tabs), 1)

    def test_moved_folder_closes_descendant_preview_in_every_workspace(self):
        third = self.workspace(self.file)
        third.host = self.host
        self.host.workspaces.append(third)
        self.paste([self.source])
        self.assertFalse(self.file.exists())
        for workspace in (self.first, third):
            self.assertEqual(workspace.preview_tabs, [])
            self.assertIsNone(workspace.current_preview_path)

    def test_completed_move_pruned_when_later_overwrite_cancelled(self):
        conflict = self.source / self.other.name
        conflict.write_text("keep source")
        self.paste([self.file, conflict], confirm_overwrite_callback=lambda *args: None)
        self.assertFalse(self.file.exists())
        self.assertTrue(conflict.exists())
        self.assertEqual(self.first.preview_tabs, [])
        self.assertIsNone(self.first.current_preview_path)

    def test_removing_inactive_preview_preserves_active_tab_identity(self):
        last = self.source / "last.txt"
        last.write_text("last")
        active = {"path": str(self.other), "pinned": True}
        self.first.preview_tabs.extend([active, {"path": str(last), "pinned": True}])
        self.first.preview_active_tab_index = 1
        self.first.current_preview_path = str(self.other)
        self.paste()
        self.assertEqual(len(self.first.preview_tabs), 2)
        self.assertIs(self.first.preview_tabs[self.first.preview_active_tab_index], active)
        self.assertEqual(self.first.current_preview_path, str(self.other))
        self.assertEqual(self.first.current_preview_mode, "text")


if __name__ == "__main__":
    unittest.main()
