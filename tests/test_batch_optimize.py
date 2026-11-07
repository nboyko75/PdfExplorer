from contextlib import ExitStack, nullcontext
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch

from controls import file_preview, filelist


class BatchOptimizeTests(unittest.TestCase):
    def setUp(self):
        self.owner = SimpleNamespace(
            current_preview_path="open.pdf", busy_cursor=nullcontext,
            refresh_list_item_size=Mock(),
        )
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(file_preview, "_get_preview_owner_from_event", return_value=self.owner))
        self.selection = stack.enter_context(patch.object(filelist, "get_selected_list_paths"))
        self.optimize = stack.enter_context(patch.object(file_preview, "optimize_pdf"))
        self.save = stack.enter_context(patch.object(file_preview, "save_pdf"))
        self.refresh = stack.enter_context(patch.object(file_preview, "show_pdf_feed"))
        self.save_state = stack.enter_context(patch.object(file_preview, "update_pdf_save_button_state"))
        self.error = stack.enter_context(patch.object(file_preview.wx, "MessageBox"))

    def test_processes_entire_selection_without_adding_unselected_preview(self):
        self.selection.return_value = ["first.pdf", "second.PDF"]
        file_preview.on_preview_optimize(None)
        expected = [call("first.pdf"), call("second.PDF")]
        self.assertEqual(self.optimize.call_args_list, expected)
        self.assertEqual(self.save.call_args_list, expected)
        self.assertEqual(self.owner.refresh_list_item_size.call_args_list, expected)
        self.refresh.assert_not_called()
        self.error.assert_not_called()

    def test_selected_preview_is_refreshed_once_after_processing(self):
        self.selection.return_value = ["first.pdf", "open.pdf"]
        file_preview.on_preview_optimize(None)
        self.refresh.assert_called_once_with(self.owner, "open.pdf")
        self.save_state.assert_called_once_with(self.owner)

    def test_failure_does_not_prevent_remaining_files_from_being_saved(self):
        self.selection.return_value = ["broken.pdf", "good.pdf"]
        self.optimize.side_effect = [RuntimeError("Cannot read PDF"), None]
        file_preview.on_preview_optimize(None)
        self.assertEqual(self.optimize.call_count, 2)
        self.save.assert_called_once_with("good.pdf")
        self.owner.refresh_list_item_size.assert_called_once_with("good.pdf")
        message = self.error.call_args.args[0]
        self.assertIn("broken.pdf", message)
        self.assertIn("Cannot read PDF", message)

    def test_skips_other_formats_and_folders_without_falling_back_to_preview(self):
        self.selection.return_value = ["notes.txt", "folder.pdf"]
        with patch.object(file_preview.os.path, "isdir", side_effect=lambda path: path == "folder.pdf"):
            file_preview.on_preview_optimize(None)
        self.optimize.assert_not_called()
        self.save.assert_not_called()

    def test_no_selection_uses_open_pdf(self):
        self.selection.return_value = []
        file_preview.on_preview_optimize(None)
        self.optimize.assert_called_once_with("open.pdf")
        self.save.assert_called_once_with("open.pdf")
        self.refresh.assert_called_once_with(self.owner, "open.pdf")

    def test_closed_preview_does_not_process_selected_files(self):
        self.owner.current_preview_path = None
        self.selection.return_value = ["first.pdf"]
        file_preview.on_preview_optimize(None)
        self.optimize.assert_not_called()


if __name__ == "__main__":
    unittest.main()
