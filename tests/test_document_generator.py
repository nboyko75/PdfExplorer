"""Generator commands, Office ownership, persistence and worker isolation."""
import ast
import importlib
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, PropertyMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from file_operations import document_generator as generator
from localization import available_locales, DEFAULT_TRANSLATIONS


class GeneratorTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.source = Path(self.folder.name) / 'original.docx'
        self.source.write_bytes(b'original document')
        self.client = Mock()
        self.app = self.client.DispatchEx.return_value
        self.app.AutomationSecurity = 2
        self.app.Options.UpdateLinksAtOpen = True
        self.document = Mock()
        self.document.ReadOnly = False
        self.document.ProtectionType = -1
        self.document.FullName = str(self.source)
        self.document.Variables.Count = 0
        self.document.Bookmarks.Exists.return_value = False
        self.document.Saved = False
        self.app.Documents.Count = 1
        self.app.Documents.Item.return_value = self.document
        self.app.Documents.Open.return_value = self.document
        self.addCleanup(patch.stopall)
        patch.dict(sys.modules, {'win32com': SimpleNamespace(client=self.client),
                                'win32com.client': self.client}).start()
        self.session = generator.DocumentGenerator(str(self.source))

    def test_opens_original_without_conversion_or_vba_for_all_formats(self):
        for extension in ('.doc', '.docx', '.docm'):
            source = self.source.with_suffix(extension)
            source.write_bytes(b'original document')
            session = generator.DocumentGenerator(str(source))
            self.assertEqual(session.open(), [])
            self.assertEqual(self.app.Documents.Open.call_args.kwargs['FileName'], str(source))
            self.assertFalse(self.app.Documents.Open.call_args.kwargs['ReadOnly'])
            self.document.SaveAs2.assert_not_called()
            self.document.Save.assert_not_called()
            self.app.Run.assert_not_called()
            self.assertNotIn('VBProject', self.document._mock_children)
            self.assertTrue(self.app.Visible)
            self.assertEqual(source.read_bytes(), b'original document')
        self.assertEqual(len(list(Path(self.folder.name).iterdir())), 3)

    def test_open_disables_macros_and_link_updates_and_restores_options(self):
        def open_document(**kwargs):
            self.assertEqual(self.app.AutomationSecurity, 3)
            self.assertFalse(self.app.Options.UpdateLinksAtOpen)
            return self.document
        self.app.Documents.Open.side_effect = open_document
        self.session.open()
        self.assertEqual(self.app.AutomationSecurity, 2)
        self.assertTrue(self.app.Options.UpdateLinksAtOpen)

    def test_open_failure_closes_only_owned_application(self):
        self.app.Documents.Open.side_effect = RuntimeError('Cannot open')
        with self.assertRaisesRegex(RuntimeError, 'Cannot open'):
            self.session.open()
        self.app.Quit.assert_called_once_with(0)
        self.assertEqual(self.app.AutomationSecurity, 2)
        self.assertTrue(self.app.Options.UpdateLinksAtOpen)

    def test_read_only_and_protected_files_are_rejected(self):
        for read_only, protection in ((True, -1), (False, 2)):
            self.document.ReadOnly = read_only
            self.document.ProtectionType = protection
            with self.assertRaises(generator.GeneratorError):
                self.session.open()
        self.document.Save.assert_not_called()

    def test_detach_leaves_word_open(self):
        self.session.open()
        self.session.detach()
        self.app.Quit.assert_not_called()
        self.document.Close.assert_not_called()
        self.assertIsNone(self.session.document)

    def test_arrange_and_close_restore_placement_before_closing_owned_document(self):
        gui = Mock()
        constants = SimpleNamespace(SW_RESTORE=9, HWND_TOP=0, SWP_SHOWWINDOW=64)
        placement = (0, 3, (0, 0), (0, 0), (50, 70, 900, 700))
        gui.GetWindowPlacement.return_value = placement
        gui.IsWindow.return_value = True
        self.document.Windows.return_value.Hwnd = 123
        self.session.open()
        events = []
        gui.SetWindowPlacement.side_effect = lambda *args: events.append('restore')
        self.document.Close.side_effect = lambda *args: events.append('close')
        with patch.dict(sys.modules, {'win32gui': gui, 'win32con': constants}):
            self.session.arrange_window((960, 0, 960, 1040))
            self.session.arrange_window((1920, 0, 960, 1040))
            gui.GetWindowPlacement.assert_called_once_with(123)
            gui.SetWindowPos.assert_called_with(123, 0, 1920, 0, 960, 1040, 64)
            gui.SetForegroundWindow.assert_called_with(123)
            self.session.close_document()
            self.session.close_document()  # Safe cleanup after an explicit close.
        self.assertEqual(events, ['restore', 'close'])
        gui.SetWindowPlacement.assert_called_once_with(123, placement)
        self.document.Close.assert_called_once_with(0)
        self.app.Quit.assert_not_called()  # Other documents in this instance survive.

    def test_closing_last_document_quits_owned_application(self):
        self.session.open()
        self.document.Close.side_effect = lambda *args: setattr(self.app.Documents, 'Count', 0)
        self.session.close_document()
        self.document.Close.assert_called_once_with(0)
        self.app.Quit.assert_called_once_with(0)

    def test_manually_closed_document_does_not_close_other_documents(self):
        self.session.open()
        self.app.Documents.Item.return_value = Mock()
        self.assertFalse(self.session.needs_save())
        self.session.close_document()
        self.document.Close.assert_not_called()
        self.app.Quit.assert_not_called()

    def test_exited_word_does_not_prevent_form_cleanup(self):
        self.session.open()
        self.session._window_placement = (123, ())
        gui = Mock()
        gui.IsWindow.return_value = False
        with patch.dict(sys.modules, {'win32gui': gui}), patch.object(
                type(self.app), 'Documents', create=True,
                new_callable=PropertyMock, side_effect=RuntimeError('Word has exited')):
            self.assertFalse(self.session.needs_save())
            self.session.close_document()
        self.assertIsNone(self.session.app)
        gui.SetWindowPlacement.assert_not_called()

    def test_word_dirty_state_and_unchanged_fields_do_not_mark_document_dirty(self):
        self.session.open()
        self.assertTrue(self.session.needs_save())
        self.document.Saved = True
        self.session.update_rows([])
        self.assertFalse(self.session.needs_save())
        self.document.Variables.Add.assert_not_called()

    def test_forced_worker_cleanup_requests_word_save_prompt(self):
        com = Mock()
        session = Mock()
        with patch.dict(sys.modules, {'pythoncom': com}), patch.object(generator, 'DocumentGenerator', return_value=session):
            worker = generator.GeneratorWorker(str(self.source), lambda *args: None)
            worker.close()
            worker.thread.join(5)
        session.close_document.assert_called_once_with(save_changes=-2)
        session.detach.assert_called_once()

    def test_unsupported_file_does_not_launch_word(self):
        with self.assertRaises(generator.GeneratorError):
            generator.DocumentGenerator(str(self.source.with_suffix('.pdf'))).open()
        self.client.DispatchEx.assert_not_called()

    def test_fields_load_from_document_variables(self):
        rows = [{'name': 'bookmark1', 'value': 'Україна\n日本 & <text>'}]
        self.document.Variables.Count = 1
        variable = self.document.Variables.Item.return_value
        variable.Name = generator.STATE_VARIABLE
        variable.Value = json.dumps(rows)
        self.assertEqual(self.session.open(), rows)

    def test_malformed_saved_fields_are_not_silently_discarded(self):
        self.document.Variables.Count = 1
        variable = self.document.Variables.Item.return_value
        variable.Name = generator.STATE_VARIABLE
        for value in ('broken JSON', '{}', '[{"name": "bad name", "value": ""}]'):
            variable.Value = value
            with self.assertRaises(generator.GeneratorError):
                self.session.open()
        self.document.Save.assert_not_called()

    def test_invalid_or_duplicate_names_do_not_modify_bookmarks(self):
        self.session.open()
        self.session.rows = [{'name': 'first', 'value': 'a'}, {'name': 'second', 'value': 'b'}]
        for names in (('bad name', 'second'), ('1first', 'second'), ('a' * 41, 'second'), ('first', 'FIRST')):
            with self.assertRaises(generator.GeneratorError):
                self.session.update_rows([{'name': name, 'value': ''} for name in names])
        self.document.Bookmarks.Add.assert_not_called()

    def test_rename_preserves_range_and_updates_state(self):
        self.session.open()
        self.session.rows = [{'name': 'old', 'value': 'a'}]
        self.document.Bookmarks.Exists.side_effect = lambda name: name == 'old'
        area = self.document.Bookmarks.return_value.Range.Duplicate
        self.session.update_rows([{'name': 'new', 'value': 'b'}])
        self.document.Bookmarks.Add.assert_called_once_with('new', area)
        self.document.Bookmarks.return_value.Delete.assert_called_once()
        self.assertEqual(self.session.rows, [{'name': 'new', 'value': 'b'}])

    def test_delete_removes_bookmark_without_replacing_text(self):
        self.session.open()
        self.session.rows = [{'name': 'field', 'value': 'a'}]
        self.document.Bookmarks.Exists.return_value = True
        self.session.delete_row(0)
        self.document.Bookmarks.return_value.Delete.assert_called_once()
        self.assertEqual(self.session.rows, [])
        self.document.Save.assert_not_called()

    def test_empty_table_or_other_document_selection_rejected(self):
        self.session.open()
        self.app.ActiveDocument.FullName = str(self.source)
        area = self.app.Selection.Range.Duplicate
        area.Start, area.End, area.StoryLength = 1, 1, 100
        area.Text = ''
        with self.assertRaises(generator.GeneratorError):
            self.session.add_selection()
        area.Text = 'cell\x07'
        area.End = 6
        with self.assertRaises(generator.GeneratorError):
            self.session.add_selection()
        area.Text = 'text'
        self.app.ActiveDocument.FullName = str(self.source.with_name('another.docx'))
        with self.assertRaises(generator.GeneratorError):
            self.session.add_selection()
        self.document.Bookmarks.Add.assert_not_called()

    def test_source_and_wrong_extension_are_rejected_before_save(self):
        self.session.open()
        for target in (self.source, self.source.with_suffix('.docm')):
            with self.assertRaises(generator.GeneratorError):
                self.session.export_document(str(target))
        self.document.Save.assert_not_called()

    def test_export_failure_preserves_existing_target_and_restores_security(self):
        self.session.open()
        target = self.source.with_name('result.docx')
        target.write_bytes(b'existing result')
        output = Mock()
        self.app.Documents.Open.return_value = output
        with patch.object(self.session, '_fill_output', side_effect=RuntimeError('Cannot fill')):
            with self.assertRaisesRegex(RuntimeError, 'Cannot fill'):
                self.session.export_document(str(target))
        self.assertEqual(target.read_bytes(), b'existing result')
        self.assertEqual(self.app.AutomationSecurity, 2)
        output.Close.assert_called_once_with(False)
        self.document.SaveAs2.assert_not_called()

    def test_worker_uses_one_thread_and_balances_com(self):
        com = Mock()
        completed = threading.Event()
        ids = []
        def dispatch(callback, result, error):
            callback(result, error)
        def work(session):
            ids.append(threading.get_ident())
        with patch.dict(sys.modules, {'pythoncom': com}):
            worker = generator.GeneratorWorker(str(self.source), dispatch)
            worker.submit(work, lambda result, error: None)
            worker.submit(work, lambda result, error: completed.set())
            self.assertTrue(completed.wait(5))
            worker.close()
            worker.thread.join(5)
        self.assertFalse(worker.thread.is_alive())
        self.assertEqual(len(set(ids)), 1)
        self.assertNotEqual(ids[0], threading.get_ident())
        com.CoInitialize.assert_called_once()
        com.CoUninitialize.assert_called_once()

    def test_all_locales_translate_generator_and_preserve_placeholders(self):
        import string
        keys = {key for key in DEFAULT_TRANSLATIONS if key.startswith('generator_') or key == 'create_document_generator'}
        def placeholders(value):
            return {name for _, name, _, _ in string.Formatter().parse(value) if name}
        for locale in available_locales():
            translations = importlib.import_module('localization.localization_' + locale).TRANSLATIONS
            for key in keys:
                self.assertIn(key, translations, (locale, key))
                self.assertEqual(placeholders(translations[key]), placeholders(DEFAULT_TRANSLATIONS[key]), (locale, key))
        self.assertEqual(DEFAULT_TRANSLATIONS['create_document_generator'], 'Create a document generator')

    def test_expand_and_save_prompt_translations_preserve_unicode(self):
        labels = {'en': 'Expand', 'uk': 'Розгорнути', 'de': 'Erweitern',
                  'fr': 'Développer', 'es': 'Expandir', 'it': 'Espandi',
                  'pt_br': 'Expandir', 'ja': '展開', 'ko': '확장',
                  'zh_cn': '展开', 'ru': 'Развернуть'}
        for locale in available_locales():
            translations = importlib.import_module('localization.localization_' + locale).TRANSLATIONS
            self.assertEqual(translations['generator_expand'], labels[locale], locale)
            message = translations['generator_confirm_save']
            self.assertNotIn('\ufffd', message, locale)
            # One grammatical question is allowed; replacement '?' characters
            # from a lossy PowerShell encoding must never reach the dialog.
            self.assertLessEqual(message.count('?'), 1, locale)
            self.assertEqual(message.count('\n'), 4, locale)


class CommandTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((ROOT / 'common/menu_utils.py').read_text(encoding='utf-8'))
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                     and node.name in ('generator_selected_path', '_handle_document_generator',
                                       'build_file_operations_menu')]
        self.append = Mock()
        keys = ('open', 'scan', 'open_with', 'folder_up', 'new_folder', 'refresh',
                'print', 'merge', 'document_generator', 'copy', 'cut', 'paste',
                'rename', 'rename_files', 'delete', 'delete_permanent', 'archive',
                'extract_here', 'extract_into', 'favorite_add', 'favorite_remove',
                'optimize_all', 'adjust_all')
        self.scope = {'wx': Mock(), 'append_command': self.append,
                      'FILE_COMMANDS': dict(zip(keys, keys))}
        exec(compile(ast.Module(body=functions, type_ignores=[]), '<commands>', 'exec'), self.scope)

    def context(self, paths, source='list', target_path=None):
        return SimpleNamespace(selected_paths=paths, source=source, target_path=target_path, owner=Mock())

    def test_only_one_existing_word_document_is_eligible(self):
        with tempfile.TemporaryDirectory() as folder:
            for name, eligible in [('file.doc', True), ('file.DOCX', True), ('file.docm', True),
                                   ('file.xlsx', False), ('file.pdf', False), ('~$lock.docx', False)]:
                path = Path(folder) / name
                path.touch()
                result = self.scope['generator_selected_path'](self.context([str(path)]))
                self.assertEqual(bool(result), eligible, name)
            self.assertIsNone(self.scope['generator_selected_path'](self.context([])))
            self.assertIsNone(self.scope['generator_selected_path'](self.context(['a.docx', 'b.docx'])))
            self.assertIsNone(self.scope['generator_selected_path'](self.context([folder])))
            self.assertIsNone(self.scope['generator_selected_path'](self.context([folder + '/missing.docx'])))
            target = str(Path(folder) / 'file.docm')
            self.assertEqual(self.scope['generator_selected_path'](self.context([], 'tree', target)), target)

    def test_command_follows_merge_in_list_and_tree_menus(self):
        for source in ('list', 'tree'):
            self.append.reset_mock()
            self.scope['build_file_operations_menu'](self.context([], source))
            commands = [call.args[2] for call in self.append.call_args_list]
            self.assertEqual(commands[commands.index('merge') + 1], 'document_generator')


if __name__ == '__main__':
    unittest.main()
