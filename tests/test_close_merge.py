"""Merge close/save lifecycle checks without Office or a GUI event loop."""
import ast
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


class MergeCloseTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'controls/merge_documents.py').read_text())
        self.wx = SimpleNamespace(
            YES_NO=1, CANCEL=2, CANCEL_DEFAULT=4, ICON_WARNING=8, OK=16,
            ICON_INFORMATION=32, ICON_ERROR=64, ID_YES=1, ID_NO=2, ID_CANCEL=3,
            MessageDialog=Mock(), MessageBox=Mock(),
            CallAfter=lambda callback, *args: callback(*args))
        self.wx.MessageDialog.return_value.ShowModal.return_value = self.wx.ID_CANCEL
        self.engine, self.word_engine = Mock(), Mock()
        scope = {'wx': self.wx, 'tr': lambda key: key, 'error_text': str,
                 'engine': self.engine, 'word_merge': self.word_engine,
                 'gridlib': SimpleNamespace(Grid=type('Grid', (), {}))}
        methods = {'on_cancel', 'resume_close', 'close_dialog', 'finish_save',
                   'save_failed', 'on_save', 'commit_pending_edits', 'finish_job'}
        classes = []
        for name in ('MergeDialog', 'WordMergeDialog'):
            original = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)
            cls = ast.ClassDef(name=name,
                              bases=[] if name == 'MergeDialog' else [ast.Name(id='MergeDialog', ctx=ast.Load())],
                              keywords=[], decorator_list=[],
                              body=[n for n in original.body if isinstance(n, ast.FunctionDef) and n.name in methods])
            classes.append(cls)
        exec(compile(ast.fix_missing_locations(ast.Module(body=classes, type_ignores=[])), 'merge_close', 'exec'), scope)
        self.classes = [scope[name] for name in ('MergeDialog', 'WordMergeDialog')]

    def dialog(self, cls=None):
        dialog = (cls or self.classes[0])()
        dialog.path = 'original.xlsx'
        dialog.disposed = dialog.busy = dialog.saving = False
        dialog.saved_changes = dialog.cancel_pending = dialog.close_after_save = False
        dialog.compared = dialog.word_preview_ready = True
        dialog.base = object()
        dialog.conflicts = [SimpleNamespace(selected=1)]
        for name in ('status', 'cancel_button', 'backup_checkbox', 'selected_change_color',
                     'update_conflicts', 'run_job', 'show_selected_book', 'load_initial',
                     'progress_timer', 'progress', 'Layout', 'update_buttons', 'EndModal', 'dispose'):
            setattr(dialog, name, Mock())
        dialog.notebook = Mock()
        dialog.notebook.GetPageCount.return_value = 0
        dialog.IsModal = Mock(return_value=True)
        return dialog

    def test_clean_or_rejected_changes_close_without_prompt(self):
        for selections in ([], [0], [0, 0]):
            dialog = self.dialog()
            dialog.conflicts = [SimpleNamespace(selected=n) for n in selections]
            dialog.on_cancel(None)
            dialog.EndModal.assert_called_once()
        self.wx.MessageDialog.assert_not_called()

    def test_cancel_keeps_choices_and_vetoes_window_close(self):
        dialog, event = self.dialog(), Mock()
        dialog.on_cancel(event)
        event.Veto.assert_called_once()
        dialog.EndModal.assert_not_called()
        self.assertEqual(dialog.conflicts[0].selected, 1)
        self.wx.MessageDialog.return_value.Destroy.assert_called_once()

    def test_no_closes_without_saving(self):
        self.wx.MessageDialog.return_value.ShowModal.return_value = self.wx.ID_NO
        dialog = self.dialog()
        dialog.on_cancel(None)
        dialog.EndModal.assert_called_once()
        dialog.run_job.assert_not_called()

    def test_save_waits_for_success_for_excel_and_word(self):
        self.wx.MessageDialog.return_value.ShowModal.return_value = self.wx.ID_YES
        for cls in self.classes:
            with self.subTest(dialog=cls.__name__):
                dialog = self.dialog(cls)
                dialog.on_cancel(None)
                self.assertTrue(dialog.saving)
                dialog.EndModal.assert_not_called()
                task, done = dialog.run_job.call_args.args
                task()
                done(None)
                dialog.EndModal.assert_called_once()
                self.assertTrue(dialog.saved_changes)
                self.assertFalse(dialog.close_after_save)
                self.assertEqual(dialog.conflicts, [])
                dialog.show_selected_book.assert_not_called()
                self.assertEqual(dialog.run_job.call_count, 1)  # Word need not reload before closing.

    def test_failed_save_keeps_choices_for_excel_and_word(self):
        self.wx.MessageDialog.return_value.ShowModal.return_value = self.wx.ID_YES
        self.engine.save_merge.side_effect = self.word_engine.save_merge.side_effect = RuntimeError('write failed')
        for cls in self.classes:
            dialog = self.dialog(cls)
            dialog.on_cancel(None)
            task, done = dialog.run_job.call_args.args
            with self.assertRaisesRegex(RuntimeError, 'write failed'):
                task()
            dialog.EndModal.assert_not_called()
            self.assertFalse(dialog.saving)
            self.assertFalse(dialog.close_after_save)
            self.assertFalse(dialog.saved_changes)
            self.assertEqual(dialog.conflicts[0].selected, 1)

    def test_unresolved_choices_prevent_save_and_close(self):
        self.wx.MessageDialog.return_value.ShowModal.return_value = self.wx.ID_YES
        dialog = self.dialog()
        dialog.conflicts.append(SimpleNamespace(selected=None))
        dialog.on_cancel(None)
        dialog.EndModal.assert_not_called()
        dialog.run_job.assert_not_called()
        self.wx.MessageBox.assert_called_once()

    def test_busy_compare_finishes_before_prompting(self):
        dialog = self.dialog()
        dialog.busy = True
        dialog.compared = False
        dialog.conflicts = []
        dialog.on_cancel(None)
        self.wx.MessageDialog.assert_not_called()
        self.assertTrue(dialog.cancel_pending)
        future = Future()
        future.set_result([SimpleNamespace(selected=1)])
        def compared(conflicts):
            dialog.conflicts = conflicts
            dialog.compared = True
        dialog.finish_job(future, compared)
        self.wx.MessageDialog.assert_called_once()
        dialog.EndModal.assert_not_called()
        self.assertFalse(dialog.cancel_pending)

    def test_busy_preview_keeps_close_pending(self):
        dialog = self.dialog()
        dialog.cancel_pending = dialog.busy = True
        dialog.resume_close()
        self.wx.MessageDialog.assert_not_called()
        dialog.busy = False
        dialog.resume_close()
        self.wx.MessageDialog.assert_called_once()
        self.assertFalse(dialog.cancel_pending)

    def test_active_cell_edit_is_committed_before_dirty_check(self):
        dialog = self.dialog()
        dialog.conflicts[0].selected = 0
        dialog.commit_pending_edits = lambda: setattr(dialog.conflicts[0], 'selected', 1)
        dialog.on_cancel(None)
        self.wx.MessageDialog.assert_called_once()
        dialog.EndModal.assert_not_called()

    def test_word_preview_not_ready_keeps_form_open(self):
        self.wx.MessageDialog.return_value.ShowModal.return_value = self.wx.ID_YES
        dialog = self.dialog(self.classes[1])
        dialog.word_preview_ready = False
        dialog.on_cancel(None)
        dialog.EndModal.assert_not_called()
        self.assertFalse(dialog.close_after_save)

    def test_close_during_save_is_vetoed_without_another_prompt(self):
        dialog, event = self.dialog(), Mock()
        dialog.busy = dialog.saving = True
        dialog.on_cancel(event)
        event.Veto.assert_called_once()
        self.wx.MessageDialog.assert_not_called()
        dialog.EndModal.assert_not_called()

    def test_modeless_close_disposes_dialog(self):
        self.wx.MessageDialog.return_value.ShowModal.return_value = self.wx.ID_NO
        dialog = self.dialog()
        dialog.IsModal.return_value = False
        dialog.on_cancel(None)
        dialog.dispose.assert_called_once()
        dialog.EndModal.assert_not_called()


if __name__ == '__main__':
    unittest.main()
