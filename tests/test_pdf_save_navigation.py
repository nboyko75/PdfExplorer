"""Verify saving a rotation while selecting another file, without opening UI."""
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import fitz
import wx

from common.workspace_context import workspace_scope
from controls import file_preview, filelist
from file_operations import pdf_utils


class PdfSaveNavigationTests(unittest.TestCase):
    def test_selecting_next_file_saves_rotated_page(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as folder:
            current = str(Path(folder) / "\u0417\u0432\u0456\u0442.pdf")
            following = str(Path(folder) / "next.pdf")
            for path in (current, following):
                with fitz.open() as document:
                    document.new_page()
                    document.new_page()
                    document.save(path)
            original = Path(current).read_bytes()
            following_bytes = Path(following).read_bytes()
            owner = SimpleNamespace(
                current_preview_path=current, _pdf_session_bytes={},
                list=None, _list_item_paths={1: following},
            )
            event = Mock()
            event.GetIndex.return_value = 1
            dialog = Mock()
            dialog.ShowModal.return_value = wx.ID_YES

            with workspace_scope(owner):
                pdf_utils.rotate_pdf_page(current, 0)
                self.assertTrue(pdf_utils.has_unsaved_pdf_changes(current))
                self.assertEqual(Path(current).read_bytes(), original)
                with patch.object(filelist, "file_preview", file_preview), \
                     patch.object(file_preview.wx, "MessageDialog", return_value=dialog), \
                     patch.object(file_preview.wx, "MessageBox") as error, \
                     patch.object(file_preview, "show_file_preview") as show, \
                     patch.object(filelist, "_schedule_list_selection_state_update"):
                    filelist.on_list_select(owner, event)
                    show.assert_called_once_with(owner, following)
                    error.assert_not_called()
                    dialog.ShowModal.assert_called_once()
                self.assertFalse(pdf_utils.has_unsaved_pdf_changes(current))
            with fitz.open(current) as document:
                self.assertEqual([page.rotation for page in document], [90, 0])
            self.assertEqual(Path(following).read_bytes(), following_bytes)


if __name__ == "__main__":
    unittest.main()
