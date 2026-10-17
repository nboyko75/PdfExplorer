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
        self.assertIsNone(self.session.app)
        self.assertIsNone(self.session.document)

    def test_unavailable_document_does_not_launch_word(self):
        with patch.object(generator, 'check_document_available',
                          side_effect=generator.GeneratorError('File is in use')):
            with self.assertRaisesRegex(generator.GeneratorError, 'File is in use'):
                self.session.open()
        self.client.DispatchEx.assert_not_called()

    def test_open_suppresses_word_alerts_and_restores_setting(self):
        self.app.DisplayAlerts = -1
        def open_document(**kwargs):
            self.assertEqual(self.app.DisplayAlerts, 0)
            return self.document
        self.app.Documents.Open.side_effect = open_document
        self.session.open()
        self.assertEqual(self.app.DisplayAlerts, -1)

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

    def test_add_shared_selection_inserts_link_below_source_and_keeps_value(self):
        self.session.open()
        self.session.rows = [{'name': 'First', 'value': 'Shared replacement'},
                             {'name': 'Other', 'value': 'Independent'}]
        self.app.ActiveDocument.FullName = str(self.source)
        area = self.app.Selection.Range.Duplicate
        area.Start, area.End, area.StoryLength, area.Text = 20, 25, 100, 'other'
        self.session.add_selection(0)
        self.assertEqual([row['name'] for row in self.session.rows], ['First', 'bookmark3', 'Other'])
        group = self.session.rows[0]['group']
        self.assertEqual(self.session.rows[1], {'name': 'bookmark3', 'value': 'Shared replacement', 'group': group})
        self.session.add_selection(1)
        self.assertEqual(self.session.rows[2]['group'], group)
        self.assertNotIn('group', self.session.rows[3])
        self.session.delete_row(0)
        self.assertEqual(self.session.rows[0]['group'], self.session.rows[1]['group'])
        self.assertEqual(self.session.rows[0]['value'], 'Shared replacement')

    def test_shared_rows_load_and_keep_group_when_renamed(self):
        rows = [{'name': 'First', 'value': 'Shared', 'group': 'linked'},
                {'name': 'Second', 'value': 'Shared', 'group': 'linked'}]
        self.document.Variables.Count = 1
        variable = self.document.Variables.Item.return_value
        variable.Name, variable.Value = generator.STATE_VARIABLE, json.dumps(rows)
        self.assertEqual(self.session.open(), rows)
        self.document.Bookmarks.Exists.side_effect = lambda name: name in ('First', 'Second')
        updated = [dict(row, value='Updated') for row in rows]
        updated[0]['name'] = 'Renamed'
        self.session.update_rows(updated)
        self.assertEqual(json.loads(variable.Value), updated)

    def test_conflicting_or_noncontiguous_shared_rows_are_rejected(self):
        rows = [{'name': 'First', 'value': 'Shared', 'group': 'linked'},
                {'name': 'Second', 'value': 'Shared', 'group': 'linked'}]
        invalid = [
            [rows[0], dict(rows[1], value='Different')],
            [rows[0], {'name': 'Other', 'value': ''}, rows[1]],
            [dict(rows[0], group='')], [dict(rows[0], group=123)]]
        for values in invalid:
            with self.assertRaises(generator.GeneratorError):
                self.session._validate_rows(values)
        self.session.open()
        self.session.rows = rows
        with self.assertRaises(generator.GeneratorError):
            self.session.update_rows([{'name': row['name'], 'value': row['value']} for row in rows])
        self.document.Bookmarks.Add.assert_not_called()

    def test_invalid_shared_selection_keeps_existing_group_unchanged(self):
        self.session.open()
        self.session.rows = [{'name': 'First', 'value': 'Shared'}]
        self.app.ActiveDocument.FullName = str(self.source)
        area = self.app.Selection.Range.Duplicate
        area.Start, area.End, area.StoryLength, area.Text = 1, 1, 100, ''
        with self.assertRaises(generator.GeneratorError):
            self.session.add_selection(0)
        self.assertEqual(self.session.rows, [{'name': 'First', 'value': 'Shared'}])
        self.document.Bookmarks.Add.assert_not_called()

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

    def test_save_persists_fields_without_creating_or_filling_output(self):
        self.session.open()
        self.session.rows = [{'name': 'Customer', 'value': 'New value'}]
        with patch.object(self.session, '_fill_output') as fill, patch.object(generator.shutil, 'copyfile') as copy:
            self.session.save_document()
        self.document.Save.assert_called_once_with()
        self.document.SaveAs2.assert_not_called()
        self.document.Variables.Add.assert_called_once_with(
            generator.STATE_VARIABLE, json.dumps(self.session.rows, ensure_ascii=False))
        self.app.Documents.Open.assert_called_once()
        fill.assert_not_called()
        copy.assert_not_called()

    def test_table_state_loads_independently_of_legacy_bookmark_fields(self):
        table = {'name': 'Products', 'rows': [['Item', '2']], 'widths': [120, 60], 'applied_rows': 1}
        self.document.Variables.Count = 1
        variable = self.document.Variables.Item.return_value
        variable.Name = generator.TABLE_STATE_VARIABLE
        variable.Value = json.dumps([table])
        self.assertEqual(self.session.open(), [])
        self.assertEqual(self.session.tables, [table])
        state = self.session.state()
        state['tables'][0]['rows'][0][0] = 'Edited snapshot'
        self.assertEqual(self.session.tables[0]['rows'][0][0], 'Item')

    def test_corrupt_table_dimensions_and_values_are_rejected(self):
        self.document.Variables.Count = 1
        variable = self.document.Variables.Item.return_value
        variable.Name = generator.TABLE_STATE_VARIABLE
        for changes in ({'widths': []}, {'widths': [-1]}, {'rows': []}, {'rows': [['A', 'B']]},
                        {'rows': [[5]]}, {'applied_rows': 0}, {'name': 'invalid name'}):
            table = {'name': 'Products', 'rows': [['A']], 'widths': [120], 'applied_rows': 1}
            table.update(changes)
            variable.Value = json.dumps([table])
            with self.assertRaises(generator.GeneratorError):
                self.session.open()
        self.document.Save.assert_not_called()

    def test_scalar_and_table_bookmark_names_must_be_unique(self):
        self.session.open()
        self.session.rows = [{'name': 'Customer', 'value': 'A'}]
        self.session.tables = [{'name': 'Products', 'rows': [['B']], 'widths': [120], 'applied_rows': 1}]
        with self.assertRaises(generator.GeneratorError):
            self.session.update_fields(self.session.snapshot(), [{'name': 'CUSTOMER', 'rows': [['B']]}])
        self.document.Bookmarks.Add.assert_not_called()

    def test_table_rename_and_cell_edits_are_persisted_without_inserting_rows(self):
        self.session.open()
        self.session.tables = [{'name': 'table1', 'rows': [['A']], 'widths': [120], 'applied_rows': 1}]
        self.document.Bookmarks.Exists.side_effect = lambda name: name == 'table1'
        with patch.object(self.session, '_apply_tables') as apply:
            self.session.update_fields([], [{'name': 'Products', 'rows': [['Edited'], ['Added']]}])
        self.assertEqual(self.session.tables[0]['name'], 'Products')
        self.assertEqual(self.session.tables[0]['applied_rows'], 1)
        self.assertEqual(self.session.tables[0]['rows'], [['Edited'], ['Added']])
        apply.assert_not_called()
        self.document.Save.assert_not_called()
        self.document.Variables.Add.assert_called_once()

    def test_table_delete_keeps_word_rows(self):
        self.session.open()
        self.session.tables = [{'name': 'Products', 'rows': [['A']], 'widths': [120], 'applied_rows': 1}]
        self.document.Bookmarks.Exists.return_value = True
        self.session.delete_table(0)
        self.assertEqual(self.session.tables, [])
        self.document.Bookmarks.return_value.Delete.assert_called_once()
        self.assertNotIn('Tables', self.document._mock_children)

    def test_add_table_requires_selection_in_its_own_document(self):
        self.session.open()
        self.app.ActiveDocument.FullName = str(self.source.with_name('other.docx'))
        with self.assertRaises(generator.GeneratorError):
            self.session.add_table_selection()
        self.app.ActiveDocument.FullName = str(self.source)
        self.app.Selection.Range.Duplicate.Tables.Count = 0
        with self.assertRaises(generator.GeneratorError):
            self.session.add_table_selection()
        self.document.Bookmarks.Add.assert_not_called()

    def test_missing_table_bookmark_stops_save_before_changes(self):
        self.session.open()
        self.session.tables = [{'name': 'Products', 'rows': [['A']], 'widths': [120], 'applied_rows': 1}]
        with self.assertRaises(generator.GeneratorError):
            self.session.save_document()
        self.document.Save.assert_not_called()
        self.app.UndoRecord.StartCustomRecord.assert_not_called()

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

    def test_worker_suppresses_disconnect_and_stops_queued_word_operations(self):
        error = RuntimeError('The object invoked has disconnected from its clients')
        error.hresult = -2147417848
        wrapped = generator.GeneratorError('Wrapped table error')
        wrapped.__cause__ = error
        for failure in (error, wrapped):
            with self.subTest(failure=type(failure).__name__):
                completed = threading.Event()
                results = []
                operation = Mock(side_effect=failure)
                queued = Mock()
                def receive(result, error):
                    results.append((result, error))
                    if len(results) == 2:
                        completed.set()
                with patch.dict(sys.modules, {'pythoncom': Mock()}), \
                     patch.object(generator, 'DocumentGenerator', return_value=Mock()):
                    worker = generator.GeneratorWorker(str(self.source), lambda callback, *args: callback(*args))
                    try:
                        worker.submit(operation, receive)
                        worker.submit(queued, receive)
                        self.assertTrue(completed.wait(5))
                    finally:
                        worker.close()
                        worker.thread.join(5)
                queued.assert_not_called()
                for result, message in results:
                    self.assertIsNone(result)
                    self.assertIsInstance(message, generator.WordDisconnected)
                    self.assertEqual(message, generator.tr('generator_word_disconnected'))
                    self.assertNotIn('clients', message)

    def test_disconnect_detection_handles_nested_hresult_but_not_busy_or_validation_errors(self):
        nested = RuntimeError('Localized COM failure')
        nested.hresult = -2147352567  # DISP_E_EXCEPTION
        nested.excepinfo = (0, 'Word', 'Localized message', None, 0, -2147417848)
        self.assertTrue(generator._word_disconnected(nested))
        busy = RuntimeError('Word is busy')
        busy.hresult = -2147418111  # RPC_E_CALL_REJECTED
        self.assertFalse(generator._word_disconnected(busy))
        self.assertFalse(generator._word_disconnected(generator.GeneratorError('Invalid bookmark')))

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


class AvailabilityTests(unittest.TestCase):
    def setUp(self):
        self.owner = SimpleNamespace(_document_generators={})
        self.frame = Mock()
        self.message = Mock(return_value=1)
        self.controls = SimpleNamespace(DocumentGeneratorFrame=self.frame,
                                        show_generator_message=self.message)
        self.addCleanup(patch.stopall)
        patch.dict(sys.modules, {'controls.document_generator_frame': self.controls,
                                 'wx': SimpleNamespace(ID_OK=1)}).start()

    def test_retry_checks_again_before_creating_form(self):
        def confirm(*args, **kwargs):
            self.frame.assert_not_called()
            self.assertTrue(kwargs['retry'])
            return 1
        self.message.side_effect = confirm
        with patch.object(generator, 'check_document_available', side_effect=[
                generator.GeneratorError('Locked'), generator.GeneratorError('Still locked'), None]) as check:
            generator.show_document_generator(self.owner, 'example.docx')
        self.assertEqual(check.call_count, 3)
        self.assertEqual(self.message.call_count, 2)
        self.assertIn('Still locked', self.message.call_args.args[1])
        self.frame.assert_called_once_with(self.owner, 'example.docx')
        self.frame.return_value.Show.assert_called_once()

    def test_cancel_does_not_create_form_or_open_word(self):
        self.message.return_value = 2
        with patch.object(generator, 'check_document_available',
                          side_effect=generator.GeneratorError('Locked')) as check:
            generator.show_document_generator(self.owner, 'example.docx')
        check.assert_called_once()
        self.frame.assert_not_called()
        self.assertEqual(self.owner._document_generators, {})

    def test_existing_generator_is_raised_without_checking_its_own_lock(self):
        existing = Mock()
        key = generator.os.path.normcase(generator.os.path.abspath('example.docx'))
        self.owner._document_generators[key] = existing
        with patch.object(generator, 'check_document_available') as check:
            generator.show_document_generator(self.owner, 'example.docx')
        check.assert_not_called()
        self.message.assert_not_called()
        self.frame.assert_not_called()
        existing.Raise.assert_called_once()


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
