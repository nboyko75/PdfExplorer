"""Merge close/save lifecycle checks without Office or a GUI event loop."""
import ast
from concurrent.futures import Future
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


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

    def test_modeless_save_on_close_waits_for_success(self):
        self.wx.MessageDialog.return_value.ShowModal.return_value = self.wx.ID_YES
        for cls in self.classes:
            with self.subTest(dialog=cls.__name__):
                dialog = self.dialog(cls)
                dialog.IsModal.return_value = False
                dialog.on_cancel(None)
                dialog.dispose.assert_not_called()
                task, done = dialog.run_job.call_args.args
                task()
                done(None)
                dialog.dispose.assert_called_once()
                dialog.EndModal.assert_not_called()
                self.assertTrue(dialog.saved_changes)


class ModelessMergeTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        tree = ast.parse((root / 'controls/merge_documents.py').read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MergeDialog')
        methods = [n for n in cls.body if isinstance(n, ast.FunctionDef)
                   and n.name in ('dispose', 'refresh_owner')]
        methods += [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'show_merge_dialog']
        main = ast.parse((root / 'main.py').read_text())
        workspace = next(n for n in main.body if isinstance(n, ast.ClassDef) and n.name == 'ExplorerWorkspace')
        methods += [n for n in workspace.body if isinstance(n, ast.FunctionDef) and n.name == 'confirm_close']
        self.wx = Mock()
        self.excel, self.word = Mock(), Mock()
        self.scope = {'wx': self.wx, 'MergeDialog': self.excel, 'WordMergeDialog': self.word,
                      'engine': SimpleNamespace(is_excel=lambda p: p.endswith('.xlsx'),
                                                source_key=lambda p: os.path.normcase(os.path.abspath(p))),
                      'word_merge': SimpleNamespace(is_word=lambda p: p.endswith('.docx')),
                      'get_unsaved_pdf_paths': lambda: []}
        exec(compile(ast.Module(body=methods, type_ignores=[]), 'modeless_merge', 'exec'), self.scope)

    def test_open_returns_without_modal_loop_and_reuses_existing_form(self):
        for path, factory in (('original.xlsx', self.excel), ('original.docx', self.word)):
            with self.subTest(path=path):
                owner = SimpleNamespace()
                factory.return_value.disposed = False
                dialog = self.scope['show_merge_dialog'](owner, path)
                self.assertIs(owner._merge_dialog, dialog)
                dialog.Show.assert_called_once()
                dialog.ShowModal.assert_not_called()
                dialog.dispose.assert_not_called()
                self.assertIs(self.scope['show_merge_dialog'](owner, path), dialog)
                factory.assert_called_once_with(owner, path)
                dialog.Raise.assert_called_once()

    def test_dispose_releases_resources_and_defers_refresh_once(self):
        dialog = Mock(disposed=False)
        dialog.owner = SimpleNamespace(_merge_dialog=dialog)
        self.scope['dispose'](dialog)
        self.scope['dispose'](dialog)
        self.assertIsNone(dialog.owner._merge_dialog)
        dialog.Destroy.assert_called_once()
        dialog.executor.shutdown.assert_called_once_with(wait=False)
        dialog.preview_dir.cleanup.assert_called_once()
        self.wx.CallAfter.assert_called_once_with(dialog.refresh_owner)
        dialog.refresh_owner.assert_not_called()

    def test_close_refreshes_only_the_merged_preview_and_preserves_selection(self):
        preview = SimpleNamespace(show_file_preview=Mock())
        for saved in (False, True):
            for selected in ('original.docx', 'another.docx', None):
                with self.subTest(saved=saved, selected=selected):
                    preview.show_file_preview.reset_mock()
                    owner = SimpleNamespace(current_preview_path=selected,
                                            refresh_current_folder_preserving_context=Mock())
                    dialog = SimpleNamespace(owner=owner, path='original.docx', saved_changes=saved)
                    with patch.dict(sys.modules, {'controls.file_preview': preview}):
                        self.scope['refresh_owner'](dialog)
                    self.assertEqual(owner.current_preview_path, selected)
                    self.assertEqual(owner.refresh_current_folder_preserving_context.call_count, int(saved))
                    if selected == dialog.path:
                        preview.show_file_preview.assert_called_once_with(owner, selected, force_refresh=True)
                    else:
                        preview.show_file_preview.assert_not_called()

    def test_queued_refresh_ignores_closing_workspace(self):
        owner = SimpleNamespace(_closing_workspace=True, refresh_current_folder_preserving_context=Mock())
        self.scope['refresh_owner'](SimpleNamespace(owner=owner, saved_changes=True))
        owner.refresh_current_folder_preserving_context.assert_not_called()

    def test_workspace_stays_open_until_merge_close_completes(self):
        dialog = Mock(disposed=False)
        owner = SimpleNamespace(_merge_dialog=dialog)
        self.assertFalse(self.scope['confirm_close'](owner))
        dialog.on_cancel.assert_called_once_with(None)
        dialog.on_cancel.side_effect = lambda event: setattr(dialog, 'disposed', True)
        self.assertTrue(self.scope['confirm_close'](owner))


if __name__ == '__main__':
    unittest.main()
