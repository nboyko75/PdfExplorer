"""Word matching, review, and transactional-save regression tests."""
import ast
from contextlib import contextmanager
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from file_operations import word_merge as m


def document(text, path='original.docx'):
    return m.Document(path, '', text)


class WordMergeTests(unittest.TestCase):
    def test_text_and_table_cell_choices(self):
        base = document('Invoice\rAmount: 100 USD\rItem\r\x07Red\r\x07')
        other = document('Invoice\rAmount: 200 USD\rItem\r\x07Blue\r\x07', 'other.doc')
        conflicts, skipped = m.conflicts_for(base, [other])
        self.assertFalse(skipped)
        self.assertEqual([c.values for c in conflicts], [['100', '200'], ['Red', 'Blue']])
        self.assertTrue(all(c.selected == 1 for c in conflicts))
        for conflict in conflicts:
            self.assertEqual(base.text[conflict.start:conflict.end], conflict.values[0])

    def test_inserted_paragraph_does_not_shift_later_matches(self):
        base = document('Heading\rFirst paragraph\rAnchor\rAmount: 100 USD\r')
        other = document('Heading\rAdded paragraph\rFirst paragraph\rAnchor\rAmount: 200 USD\r', 'b.docx')
        conflicts, skipped = m.conflicts_for(base, [other])
        self.assertEqual([c.values for c in conflicts], [['100', '200']])
        self.assertEqual(skipped, [('b.docx', 1)])

    def test_overlapping_sources_are_one_unresolved_choice(self):
        base = document('The red car arrived.\r')
        a = document('The blue car arrived.\r', 'a.docx')
        b = document('The motorcycle arrived.\r', 'b.docx')
        conflicts, skipped = m.conflicts_for(base, [a, b])
        self.assertFalse(skipped)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].values, ['red car', 'blue car', 'motorcycle'])
        self.assertIsNone(conflicts[0].selected)

    def test_duplicate_values_have_provenance_and_auto_selection(self):
        base = document('Price 100\r')
        sources = [document('Price 200\r', name) for name in ('a.docx', 'b.docm')]
        conflict = m.conflicts_for(base, sources)[0][0]
        self.assertEqual(conflict.values, ['100', '200'])
        self.assertEqual(conflict.sources[1], [m.source_key(d.path) for d in sources])
        self.assertEqual(conflict.selected, 1)

    def test_inline_insertions_and_deletions(self):
        for original, changed in [('The car arrived.\r', 'The red car arrived.\r'),
                                  ('The red car arrived.\r', 'The car arrived.\r'),
                                  ('The car arrived. \r', 'The car arrived.\r')]:
            base, other = document(original), document(changed, 'b.docx')
            conflicts, skipped = m.conflicts_for(base, [other])
            self.assertFalse(skipped)
            text = original
            for c in reversed(conflicts):
                text = text[:c.start] + c.values[c.selected] + text[c.end:]
            self.assertEqual(text, changed)

    def test_repeated_text_changes_only_correct_occurrence(self):
        base = document('100 apples and 100 pears\r100 oranges\r')
        other = document('100 apples and 200 pears\r100 oranges\r', 'b.docx')
        conflict = m.conflicts_for(base, [other])[0][0]
        self.assertEqual(conflict.start, base.text.index('100 pears'))

    def test_fields_and_content_controls_are_excluded(self):
        base = document('Price 100\r')
        base.protected = [(6, 9)]
        conflicts, skipped = m.conflicts_for(base, [document('Price 200\r', 'b.docx')])
        self.assertFalse(conflicts)
        self.assertEqual(skipped, [('b.docx', 1)])

    def test_table_structure_is_not_replaced_with_plain_paragraph(self):
        conflicts, skipped = m.conflicts_for(document('Red\r\x07'), [document('Blue\r', 'b.docx')])
        self.assertFalse(conflicts)
        self.assertTrue(skipped)

    def test_unicode_offsets(self):
        self.assertEqual(m.word_offset('A\U0001f600Б', 2), 3)
        self.assertEqual(m.word_offset('Cell\r\x07Next', 6), 5)

    def test_similarity_uses_content(self):
        self.assertGreater(m.similarity(document('Invoice total 100'), document('Invoice total 200')), .45)
        self.assertEqual(m.similarity(document('Invoice total'), document('Other content')), 0)
        self.assertEqual(m.similarity(document(''), document('')), 0)

    def test_preview_escapes_values_and_keeps_original_html(self):
        c = m.Conflict(0, 3, ['old', '<script>&"'], [['original.docx'], ['other.docx']], 1)
        output = m.review_html('<html><table><tr><td>MARKER</td></tr></table></html>',
                               ['MARKER'], [c], {},
                               {'choose': 'Choose', 'empty': 'Empty', 'keep': 'Keep original'}, 'session')
        self.assertIn('<td><select ', output)
        self.assertIn('&lt;script&gt;&amp;', output)
        self.assertIn('old [original.docx]', output)
        self.assertIn('wordMerge.postMessage', output)
        with self.assertRaises(m.MergeError):
            m.review_html('missing', ['MARKER'], [c], {},
                          {'choose': 'Choose', 'empty': 'Empty', 'keep': 'Keep'}, '')

    def test_menu_accepts_office_files_in_all_command_contexts(self):
        tree = ast.parse((ROOT/'common/menu_utils.py').read_text())
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'merge_selected_path')
        scope = {}
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'menu', 'exec'), scope)
        with tempfile.TemporaryDirectory() as folder:
            for name in ('test.doc', 'test.docx', 'test.docm', 'UPPER.DOCX', 'test.xlsx',
                         'test.xls', 'test.xlsm', 'test.xlsb', 'test.pdf', '~$test.docx'):
                path = Path(folder)/name
                path.touch()
                expected = None if name in ('test.pdf', '~$test.docx') else str(path)
                for source in ('list', 'main', 'tree'):
                    with self.subTest(name=name, source=source):
                        context = SimpleNamespace(source=source, selected_paths=[str(path)],
                                                  target_path=str(path) if source == 'tree' else None)
                        self.assertEqual(scope['merge_selected_path'](context), expected)
            for paths in ([], [str(path), str(path)], [folder], [str(Path(folder)/'missing.docx')]):
                context = SimpleNamespace(source='list', selected_paths=paths, target_path=None)
                self.assertIsNone(scope['merge_selected_path'](context))

    def test_stale_preview_messages_cannot_change_current_choices(self):
        tree = ast.parse((ROOT/'controls/merge_documents.py').read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'WordMergeDialog')
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'on_word_choice')
        scope = {'json': json}
        exec(compile(ast.Module(body=[method], type_ignores=[]), 'choice', 'exec'), scope)
        dialog = Mock(disposed=False, busy=False, compared=True, review_token='new')
        dialog.conflicts = [m.Conflict(0, 1, ['a', 'b'], [], None)]
        for token, index, choice in [('old', 0, 1), ('new', -1, 1), ('new', 0, 4), ('new', True, 1)]:
            event = Mock()
            event.GetString.return_value = json.dumps(dict(token=token, conflict=index, choice=choice))
            scope['on_word_choice'](dialog, event)
            self.assertIsNone(dialog.conflicts[0].selected)
        event.GetString.return_value = json.dumps(dict(token='new', conflict=0, choice=0))
        scope['on_word_choice'](dialog, event)
        self.assertEqual(dialog.conflicts[0].selected, 0)

    def test_save_verifies_before_replacing_and_preserves_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'original.docx'
            path.write_bytes(b'original bytes')
            base = m.Document(str(path), m.fingerprint(path), 'Price 100\r')
            conflict = m.conflicts_for(base, [document('Price 200\r', 'b.docx')])[0][0]
            doc = Mock(ReadOnly=False, ProtectionType=-1, TrackRevisions=False)
            doc.Revisions.Count = 0
            doc.Range.return_value.Text = '100'
            def opened(app, filename, **kwargs):
                doc.Range.return_value.Text = '100'
                doc.Save.side_effect = lambda: Path(filename).write_bytes(b'saved bytes')
                return doc
            @contextmanager
            def app():
                yield object()
            with patch.object(m, 'word_app', app), patch.object(m, 'open_document', opened), \
                    patch.object(m, 'read_document', return_value=document('WRONG')):
                with self.assertRaises(m.MergeError):
                    m.save_merge(base, [conflict])
            self.assertEqual(path.read_bytes(), b'original bytes')
            self.assertEqual(list(Path(folder).iterdir()), [path])
            with patch.object(m, 'word_app', app), patch.object(m, 'open_document', opened), \
                    patch.object(m, 'read_document', return_value=document('Price 200\r')):
                m.save_merge(base, [conflict])
            self.assertEqual(path.read_bytes(), b'saved bytes')
            self.assertEqual(Path(str(path) + '.merge-backup').read_bytes(), b'original bytes')
            self.assertEqual(base.text, 'Price 200\r')
            self.assertEqual(base.digest, m.fingerprint(path))

    def test_save_rejects_unresolved_and_changed_original(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'a.docx'
            path.write_bytes(b'original')
            base = m.Document(str(path), m.fingerprint(path), 'a\r')
            conflict = m.Conflict(0, 1, ['a', 'b'], [], None)
            with self.assertRaises(m.MergeError):
                m.save_merge(base, [conflict])
            conflict.selected = 1
            path.write_bytes(b'changed')
            with self.assertRaises(m.MergeError):
                m.save_merge(base, [conflict])
            self.assertEqual(path.read_bytes(), b'changed')


if __name__ == '__main__':
    unittest.main()
