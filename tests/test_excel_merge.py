"""Run with: python -m unittest discover -s tests -p test_excel_merge.py -v"""
import ast
from contextlib import contextmanager
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from file_operations import excel_merge as m


def book(path, values, name='Sheet1'):
    return m.Book(path, '', {name: m.Sheet({p: m.Cell(v) for p, v in values.items()})})


class MergeTests(unittest.TestCase):
    def test_same_values_no_conflicts(self):
        self.assertEqual(m.conflicts_for(book('base', {(1,1):1}), [book('other', {(1,1):1.0})]), [])

    def test_single_alternative_auto_selected_with_sources(self):
        result = m.conflicts_for(book('base.xlsx', {(1,1):'old'}),
                                 [book('b.xlsx', {(1,1):'new'}), book('c.xlsx', {(1,1):'new'})])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].selected, 1)
        self.assertEqual(result[0].sources, [['base.xlsx'], ['b.xlsx','c.xlsx']])

    def test_multiple_alternatives_require_choice(self):
        result = m.conflicts_for(book('a', {(1,1):'A'}),
                                 [book('b', {(1,1):'B'}), book('c', {(1,1):'C'})])
        self.assertIsNone(result[0].selected)
        self.assertEqual(len(result[0].values), 3)

    def test_blank_is_an_explicit_choice(self):
        result = m.conflicts_for(book('a', {(1,1):'A'}), [book('b', {})])
        self.assertEqual(result[0].values[1], m.EMPTY)

    def test_new_cells_are_included(self):
        result = m.conflicts_for(book('a', {}), [book('b', {(4,3):'new'})])
        self.assertEqual((result[0].row, result[0].col), (4,3))
        self.assertEqual(result[0].values[0], m.EMPTY)

    def test_sheets_matched_by_name_not_order(self):
        a = book('a', {(1,1):'a'}, 'First')
        a.sheets['Second'] = m.Sheet({(1,1):m.Cell('b')})
        b = book('b', {(1,1):'c'}, 'Second')
        b.sheets['First'] = a.sheets['First']
        changes = m.conflicts_for(a,[b])
        self.assertEqual([c.sheet for c in changes], ['Second'])

    def test_unmatched_sheets_are_not_silently_added(self):
        self.assertEqual(m.conflicts_for(book('a', {(1,1):1},'One'),[book('b',{(1,1):2},'Two')]), [])

    def test_bool_number_text_formula_are_distinct(self):
        cells = [m.Cell(True),m.Cell(1),m.Cell('1'),m.Cell('=1',True),m.Cell('=1',False)]
        self.assertEqual(len({c.key for c in cells}),5)

    def test_similarity_by_content(self):
        a=book('a',{(1,1):'Product',(1,2):'Quantity',(2,1):'Paper',(2,2):4})
        b=book('unrelated-name',{(1,1):'Product',(1,2):'Quantity',(2,1):'Paper',(2,2):7})
        c=book('a-copy',{(1,1):'Sky',(1,2):'Weather',(2,1):'Rain'})
        self.assertGreater(m.similarity(a,b),.45)
        self.assertLess(m.similarity(a,c),.45)

    def test_empty_books_not_similar(self):
        self.assertEqual(m.similarity(book('a',{}),book('b',{})),0)

    def test_unresolved_cannot_save(self):
        c=m.Conflict('s',1,1,[m.Cell(1),m.Cell(2)], [['a'],['b']])
        with self.assertRaises(m.MergeError) as error:
            m.save_merge(book('a',{}),[c])
        self.assertEqual(error.exception.key,'merge_unresolved')

    def test_changed_original_cannot_save(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'a.xlsx';path.write_bytes(b'changed')
            with self.assertRaises(m.MergeError) as error:
                m.save_merge(m.Book(str(path),'old',{}),[])
            self.assertEqual(error.exception.key,'merge_changed')

    def test_reject_keeps_original_without_excel(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'a.xlsx';path.write_bytes(b'original')
            base=m.Book(str(path),m.fingerprint(path),{})
            c=m.Conflict('s',1,1,[m.Cell(1),m.Cell(2)],[['a'],['b']],0)
            with patch.object(m,'excel_app') as excel:
                m.save_merge(base,[c])
                excel.assert_not_called()
            self.assertEqual(path.read_bytes(),b'original')

    def test_atomic_save_and_failure(self):
        for fail in (False, True):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as d:
                path=Path(d)/'a.xlsm';path.write_bytes(b'original')
                base=m.Book(str(path),m.fingerprint(path),{})
                cell=Mock(HasArray=False,MergeCells=False)
                sheet=Mock(ProtectContents=False)
                sheet.Cells.return_value=cell
                document=Mock(ReadOnly=False)
                document.Worksheets.return_value=sheet
                def opened(app, temporary, readonly=False):
                    def save():
                        Path(temporary).write_bytes(b'merged')
                        if fail:
                            raise RuntimeError('disk error')
                    document.Save.side_effect=save
                    return document
                @contextmanager
                def excel():
                    yield object()
                c=m.Conflict('s',1,1,[m.Cell('old'),m.Cell('new')],[['a'],['b']],1)
                with patch.object(m,'excel_app',excel),patch.object(m,'open_book',opened):
                    if fail:
                        with self.assertRaises(RuntimeError):m.save_merge(base,[c])
                    else:
                        m.save_merge(base,[c])
                self.assertEqual(path.read_bytes(),b'original' if fail else b'merged')
                if not fail:
                    self.assertEqual(Path(str(path)+'.merge-backup').read_bytes(),b'original')
                    self.assertEqual(cell.Value2,'new')
                self.assertFalse(list(Path(d).glob('~$*')))
                document.Close.assert_called_once_with(False)

    def test_search_is_non_recursive_and_excludes_target_and_locks(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            for name in ('base.xlsx','copy.xlsm','~$locked.xlsx','text.txt'):
                (folder/name).write_text('x')
            (folder/'sub').mkdir();(folder/'sub/nested.xlsx').write_text('x')
            @contextmanager
            def excel():yield object()
            def read(app,path):return book(path,{(1,1):'same'})
            with patch.object(m,'excel_app',excel),patch.object(m,'read_book',side_effect=read):
                base, matches, skipped=m.search_books(str(folder/'base.xlsx'))
            self.assertEqual([Path(b.path).name for b,s in matches],['copy.xlsm'])

    def test_all_languages_have_merge_labels(self):
        required=set()
        for module in ('controls/merge_documents.py','file_operations/excel_merge.py'):
            tree=ast.parse((ROOT/module).read_text())
            for node in ast.walk(tree):
                if isinstance(node,ast.Constant) and isinstance(node.value,str) and node.value.startswith('merge_'):
                    required.add(node.value)
        for path in (ROOT/'localization').glob('localization_*.py'):
            env={};exec(compile(path.read_text(),str(path),'exec'),env)
            self.assertFalse(required-set(env['TRANSLATIONS']), (path.name,required-set(env['TRANSLATIONS'])))


if __name__=='__main__':unittest.main()
