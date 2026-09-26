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
    def test_hidden_columns_excluded_from_comparison_and_similarity(self):
        base = book('base', {(1, 1): 'same', (1, 2): 'old'})
        other = book('other', {(1, 1): 'same', (1, 2): 'new'})
        for hidden_book in (base, other):
            hidden_book.sheets['Sheet1'].hidden_cols = {2}
            self.assertEqual(m.conflicts_for(base, [other]), [])
            self.assertAlmostEqual(m.similarity(base, other), 1.0)
            hidden_book.sheets['Sheet1'].hidden_cols.clear()
        visible = book('visible', {(1, 1): 'same', (1, 2): 'visible change'})
        other.sheets['Sheet1'].hidden_cols = {2}
        changes = m.conflicts_for(base, [other, visible])
        self.assertEqual([v.value for v in changes[0].values], ['old', 'visible change'])

    def test_filtered_rows_do_not_become_blank_alternatives(self):
        base = book('base', {(1, 1): 'header', (2, 1): 'old', (3, 1): 'old'})
        other = book('other', {(1, 1): 'header', (2, 1): 'new', (3, 1): 'new'})
        other.sheets['Sheet1'].hidden_rows = {2}
        changes = m.conflicts_for(base, [other])
        self.assertEqual([(c.row, c.col) for c in changes], [(3, 1)])
        base.sheets['Sheet1'].hidden_rows = {3}
        self.assertEqual(m.conflicts_for(base, [other]), [])

    def test_filter_excludes_only_the_hidden_source(self):
        base = book('base', {(2, 1): 'old'})
        hidden = book('hidden', {(2, 1): 'excluded'})
        visible = book('visible', {(2, 1): 'new'})
        hidden.sheets['Sheet1'].hidden_rows = {2}
        changes = m.conflicts_for(base, [hidden, visible])
        self.assertEqual([v.value for v in changes[0].values], ['old', 'new'])
        self.assertEqual(changes[0].row, 2)

    def test_similarity_ignores_filtered_out_content(self):
        base = book('base', {(1, 1): 'same', (2, 1): 'alpha'})
        other = book('other', {(1, 1): 'same', (2, 1): 'unrelated'})
        other.sheets['Sheet1'].hidden_rows = {2}
        self.assertAlmostEqual(m.similarity(base, other), 1.0)

    def test_read_book_records_filtered_rows(self):
        sheet = Mock(Name='Sheet1', FilterMode=False, Visible=-1)
        sheet.UsedRange.Rows.Count = 3
        sheet.UsedRange.Columns.Count = 1
        sheet.UsedRange.Row = 1
        sheet.UsedRange.Column = 1
        sheet.UsedRange.Formula = (('header',), ('hidden',), ('visible',))
        sheet.UsedRange.Value2 = sheet.UsedRange.Formula
        sheet.Rows.side_effect = lambda row: Mock(Hidden=row == 2)
        sheet.Columns.side_effect = lambda col: Mock(Hidden=col == 1)
        document = Mock(Worksheets=[sheet])
        with patch.object(m, 'fingerprint', return_value='digest'), patch.object(m, 'open_book', return_value=document), patch.object(m, 'read_range_styles', return_value={}):
            loaded = m.read_book(Mock(), 'test.xlsx')
        self.assertEqual(loaded.sheets['Sheet1'].hidden_rows, {2})
        self.assertEqual(loaded.sheets['Sheet1'].hidden_cols, {1})
        self.assertEqual(loaded.sheets['Sheet1'].cells[2, 1].value, 'hidden')
        document.Close.assert_called_once_with(False)

    def test_sheet_table_blanks_unchanged_cells(self):
        # Exercise the table model without requiring native wx on the test host.
        from types import SimpleNamespace
        tree = ast.parse((ROOT/'common/sheet_table.py').read_text())
        definitions = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
        scope = {'gridlib': SimpleNamespace(GridTableBase=object, GridCellStringRenderer=object, GridCellEditor=object), 'engine': m, 'tr': lambda key: key, 'adv': SimpleNamespace(OwnerDrawnComboBox=object)}
        exec(compile(ast.Module(body=definitions, type_ignores=[]), 'sheet_table', 'exec'), scope)
        sheet = m.Sheet({(1, 1): m.Cell('same'), (2, 1): m.Cell('changed')}, 2, 1)
        full_table = scope['SheetTable'](sheet, {})
        self.assertEqual(full_table.GetValue(0, 0), 'same')
        self.assertEqual(full_table.GetValue(1, 0), 'changed')
        table = scope['SheetTable'](sheet, {}, difference_positions={(2, 1)})
        self.assertEqual(table.GetValue(0, 0), '')
        self.assertEqual(table.GetValue(1, 0), 'changed')
        sheet.hidden_rows = {2}
        self.assertEqual(table.GetValue(1, 0), '')

    def test_formula_result_display_preserves_formula_for_merge(self):
        from types import SimpleNamespace
        tree = ast.parse((ROOT/'common/sheet_table.py').read_text())
        definitions = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
        scope = {'gridlib': SimpleNamespace(GridTableBase=object, GridCellStringRenderer=object, GridCellEditor=object),
                 'engine': m, 'tr': lambda key: key, 'adv': SimpleNamespace(OwnerDrawnComboBox=object)}
        exec(compile(ast.Module(body=definitions, type_ignores=[]), 'sheet_table', 'exec'), scope)
        formula = m.Cell('=SUM(A1:A2)', True, '12.50', 12.5)
        sheet = m.Sheet({(1, 1): formula}, 1, 1)
        self.assertEqual(scope['SheetTable'](sheet, {}).GetValue(0, 0), '12.50')
        self.assertEqual(formula.key, ('formula', '=SUM(A1:A2)'))
        conflict = m.Conflict('Sheet1', 1, 1, [formula, m.Cell('=1+2', True, '3', 3)], [['a'], ['b']], 1)
        table = scope['SheetTable'](sheet, {(1, 1): conflict})
        self.assertIn('3', table.GetValue(0, 0))
        self.assertNotIn('=1+2', table.GetValue(0, 0))

    def test_dropdown_source_colors_and_duplicate_display_values(self):
        from types import SimpleNamespace
        tree = ast.parse((ROOT/'common/sheet_table.py').read_text())
        definitions = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
        scope = {'gridlib': SimpleNamespace(GridTableBase=object, GridCellStringRenderer=object, GridCellEditor=object),
                 'engine': m, 'tr': lambda key: key, 'adv': SimpleNamespace(OwnerDrawnComboBox=object),
                 'wx': SimpleNamespace(NOT_FOUND=-1)}
        exec(compile(ast.Module(body=definitions, type_ignores=[]), 'sheet_table', 'exec'), scope)
        conflict = m.Conflict('Sheet1', 1, 1, [m.Cell('=1+1', True, '2', 2), m.Cell('=2', True, '2', 2)],
                              [['original.xlsx'], ['source.xlsx']], 0)
        table = scope['SheetTable'](m.Sheet(), {(1, 1): conflict}, source_colors={'source.xlsx': (1, 2, 3)})
        self.assertEqual(table.labels[1, 1], ['2', '2'])
        self.assertEqual(table.colors[1, 1], [(0, 0, 0), (1, 2, 3)])
        editor = scope['ColoredChoiceEditor'](table.labels[1, 1], table.colors[1, 1])
        editor.initial = 0
        editor.combo = Mock()
        editor.combo.GetSelection.return_value = 1
        grid = Mock()
        grid.GetTable.return_value = table
        self.assertEqual(editor.EndEdit(0, 0, grid, '2'), '2')
        editor.ApplyEdit(0, 0, grid)
        self.assertEqual(conflict.selected, 1)

    def test_list_arrows_select_without_checking_and_activation_toggles(self):
        from types import SimpleNamespace
        tree = ast.parse((ROOT/'controls/merge_documents.py').read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MergeFileList')
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'on_key')
        scope = {'wx': SimpleNamespace(WXK_SPACE=32, WXK_RETURN=13, WXK_NUMPAD_ENTER=370, NOT_FOUND=-1)}
        exec(compile(ast.Module(body=[method], type_ignores=[]), 'file_list', 'exec'), scope)
        control = Mock()
        control.GetSelection.return_value = 0
        control.IsItemChecked.return_value = False
        event = Mock()
        event.GetKeyCode.return_value = 315
        scope['on_key'](control, event)
        control.CheckItem.assert_not_called()
        event.Skip.assert_called_once()
        for key in (32, 13, 370):
            event.GetKeyCode.return_value = key
            scope['on_key'](control, event)
        self.assertEqual(control.CheckItem.call_count, 3)
        self.assertEqual(control.changed.call_count, 3)

    def test_formatting_uses_one_bulk_com_call(self):
        from types import SimpleNamespace
        xml = '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"><Styles/><Worksheet><Table/></Worksheet></Workbook>'
        area = Mock()
        area._oleobj_.GetIDsOfNames.return_value = 6
        area._oleobj_.Invoke.return_value = xml
        sheet = Mock()
        sheet.Range.return_value = area
        with patch.dict(sys.modules, {'pythoncom': SimpleNamespace(DISPATCH_PROPERTYGET=2)}):
            styles = m.read_range_styles(sheet, 1, 1, 1000, 20, {2}, {3})
        area._oleobj_.Invoke.assert_called_once_with(6, 0, 2, True, 11)
        self.assertEqual(len(styles), 999 * 19)
        self.assertIs(styles[1, 1], styles[1000, 20])
        self.assertNotIn((2, 1), styles)
        self.assertNotIn((1, 3), styles)

    def test_xml_style_inheritance_and_sparse_cells(self):
        xml = '''<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
        xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"><Styles>
        <Style ss:ID="Default"><Font ss:FontName="Arial" ss:Size="12"/></Style>
        <Style ss:ID="bold"><Font ss:Bold="1" ss:Color="#123456"/>
        <Interior ss:Color="#ABCDEF"/><Alignment ss:Horizontal="Right"/></Style>
        </Styles><Worksheet><Table><Row ss:Index="2"><Cell ss:Index="3" ss:StyleID="bold"/>
        </Row></Table></Worksheet></Workbook>'''
        styles = m.parse_range_styles(xml, 4, 5, 3, 4, set(), set())
        self.assertEqual(styles[5, 7]['foreground'], (18, 52, 86))
        self.assertEqual(styles[5, 7]['font_name'], 'Arial')
        self.assertTrue(styles[5, 7]['bold'])
        self.assertFalse(styles[4, 5]['bold'])
        self.assertEqual(styles[5, 7]['horizontal'], -4152)

    def test_layout_preserves_point_dimensions_and_excludes_hidden_axes(self):
        sheet = Mock()
        sheet.UsedRange.Row = sheet.UsedRange.Column = 1
        sheet.UsedRange.Rows.Count = 3
        sheet.UsedRange.Columns.Count = 2
        sheet.Rows.side_effect = lambda row: Mock(Height={1: 18, 3: 30}[row])
        sheet.Columns.side_effect = lambda col: Mock(Width=81.75)
        model = m.Sheet(rows=3, cols=2, hidden_rows={2}, hidden_cols={2})
        with patch.object(m, 'read_range_styles', return_value={}):
            styles, heights, widths = m.read_sheet_layout(sheet, model)
        self.assertEqual(heights, {1: 18, 3: 30})
        self.assertEqual(widths, {1: 81.75})

    def test_only_first_visible_sheet_loads_styles(self):
        def worksheet(name, visible):
            sheet = Mock(Name=name, Visible=visible)
            sheet.UsedRange.Rows.Count = sheet.UsedRange.Columns.Count = 1
            sheet.UsedRange.Row = sheet.UsedRange.Column = 1
            sheet.UsedRange.Formula = 'text'
            sheet.UsedRange.Value2 = 'text'
            sheet.Rows.return_value.Hidden = False
            sheet.Columns.return_value.Hidden = False
            return sheet
        first, second = worksheet('First', -1), worksheet('Second', -1)
        hidden, very_hidden = worksheet('Hidden', 0), worksheet('VeryHidden', 2)
        document = Mock(Worksheets=[hidden, first, very_hidden, second])
        with patch.object(m, 'fingerprint', return_value='digest'), patch.object(m, 'open_book', return_value=document), patch.object(m, 'read_sheet_layout', return_value=({}, {1: 30}, {1: 72})) as layout:
            result = m.read_book(Mock(), 'test.xlsx')
        self.assertEqual(list(result.sheets), ['First', 'Second'])
        self.assertEqual(layout.call_count, 1)
        self.assertIs(layout.call_args.args[0], first)
        self.assertTrue(result.sheets['First'].styles_loaded)
        self.assertFalse(result.sheets['Second'].styles_loaded)
        self.assertEqual(result.sheets['First'].row_heights[1], 30)
        self.assertEqual(result.sheets['First'].col_widths[1], 72)
        with patch.object(m, 'fingerprint', return_value='digest'), patch.object(m, 'open_book', return_value=document), patch.object(m, 'read_sheet_layout') as layout:
            m.read_book(Mock(), 'test.xlsx', load_first_style=False)
        layout.assert_not_called()

    def test_null_excel_formatting_uses_defaults(self):
        from types import SimpleNamespace
        font = SimpleNamespace(Name=None, Size=None, Bold=None, Italic=None,
                               Underline=None, Strikethrough=None, Color=None)
        interior = SimpleNamespace(Color=None, Pattern=None)
        cell = SimpleNamespace(Font=font, Interior=interior, DisplayFormat=None,
                               HorizontalAlignment=None, VerticalAlignment=None)
        style = m.read_cell_style(cell)
        self.assertEqual(style['font_name'], 'Calibri')
        self.assertEqual(style['font_size'], 11)
        self.assertEqual(style['foreground'], (0, 0, 0))
        self.assertEqual(style['background'], (255, 255, 255))
        self.assertEqual(style['horizontal'], 1)
        self.assertEqual(style['vertical'], -4107)
        self.assertFalse(style['underline'])
        self.assertEqual(m.excel_rgb(None), (0, 0, 0))

    def test_read_cell_style_colors_and_alignment(self):
        font = Mock(Name='Arial', Size=12, Bold=True, Italic=False,
                    Underline=-4142, Strikethrough=False, Color=0x332211)
        interior = Mock(Color=0x665544, Pattern=1)
        cell = Mock(HorizontalAlignment=-4152, VerticalAlignment=-4108)
        cell.DisplayFormat.Font = font
        cell.DisplayFormat.Interior = interior
        style = m.read_cell_style(cell)
        self.assertEqual(style['foreground'], (17, 34, 51))
        self.assertEqual(style['background'], (68, 85, 102))
        self.assertEqual(style['font_name'], 'Arial')
        self.assertEqual(style['horizontal'], -4152)
        self.assertTrue(style['bold'])
        self.assertFalse(style['underline'])

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
            def read(app,path,**kwargs):return book(path,{(1,1):'same'})
            with patch.object(m,'excel_app',excel),patch.object(m,'read_book',side_effect=read):
                base, matches, skipped=m.search_books(str(folder/'base.xlsx'))
            self.assertEqual([Path(b.path).name for b,s in matches],['copy.xlsm'])

    def test_all_languages_have_merge_labels(self):
        required=set()
        for module in ('controls/merge_documents.py','file_operations/excel_merge.py','common/sheet_table.py'):
            tree=ast.parse((ROOT/module).read_text())
            for node in ast.walk(tree):
                if isinstance(node,ast.Constant) and isinstance(node.value,str) and node.value.startswith('merge_'):
                    required.add(node.value)
        for path in (ROOT/'localization').glob('localization_*.py'):
            env={};exec(compile(path.read_text(),str(path),'exec'),env)
            self.assertFalse(required-set(env['TRANSLATIONS']), (path.name,required-set(env['TRANSLATIONS'])))


if __name__=='__main__':unittest.main()
