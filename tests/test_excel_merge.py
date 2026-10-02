"""Run with: python -m unittest discover -s tests -p test_excel_merge.py -v"""
import ast
from contextlib import contextmanager
import os
from pathlib import Path
import sys
from string import Formatter
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from file_operations import excel_merge as m


def book(path, values, name='Sheet1'):
    return m.Book(path, '', {name: m.Sheet({p: m.Cell(v) for p, v in values.items()})})


class MergeTests(unittest.TestCase):
    def test_source_identity_distinguishes_workbooks_with_the_same_filename(self):
        from types import SimpleNamespace
        tree = ast.parse((ROOT/'common/sheet_table.py').read_text())
        definitions = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
        scope = {'gridlib': SimpleNamespace(GridTableBase=object, GridCellStringRenderer=object, GridCellEditor=object),
                 'engine': m, 'tr': lambda key: key, 'adv': SimpleNamespace(OwnerDrawnComboBox=object)}
        exec(compile(ast.Module(body=definitions, type_ignores=[]), 'sheet_table', 'exec'), scope)
        base = book('original/same.xlsx', {(1, 1): 'base'})
        left = book('left/same.xlsx', {(1, 1): 'left'})
        right = book('right/same.xlsx', {(1, 1): 'right'})
        conflict = m.conflicts_for(base, [left, right])[0]
        table = scope['SheetTable'](base.sheets['Sheet1'], {(1, 1): conflict}, min_columns=4,
                                    source_colors={left.path: (1, 2, 3), right.path: (4, 5, 6)})
        self.assertEqual(table.colors[1, 1], [(0, 0, 0), (1, 2, 3), (4, 5, 6)])
        self.assertEqual(table.GetNumberCols(), 4)
        self.assertTrue(table.IsEmptyCell(0, 3))

    def test_click_toggles_displayed_row_once_and_not_previous_selection(self):
        from types import SimpleNamespace
        tree = ast.parse((ROOT/'controls/merge_documents.py').read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MergeFileList')
        methods = [n for n in cls.body if isinstance(n, ast.FunctionDef)
                   and n.name in ('row_at', 'on_mouse', 'on_mouse_up')]
        scope = {'wx': SimpleNamespace(NOT_FOUND=-1)}
        exec(compile(ast.Module(body=methods, type_ignores=[]), 'file_list', 'exec'), scope)
        control = Mock()
        control.GetTopItem.return_value = 10
        control.GetCountPerPage.return_value = 3
        control.GetItemCount.return_value = 20
        control.GetItemRect.side_effect = lambda index: SimpleNamespace(y=(index - 10) * 20, height=20)
        control.row_at.side_effect = lambda point: scope['row_at'](control, point)
        control.IsItemChecked.return_value = True
        event = Mock()
        event.GetPosition.return_value = SimpleNamespace(x=90, y=30)
        scope['on_mouse'](control, event)
        control.Select.assert_called_once_with(11)
        control.CheckItem.assert_not_called()
        scope['on_mouse_up'](control, event)
        control.CheckItem.assert_called_once_with(11, False)
        control.changed.assert_called_once_with(None)
        self.assertEqual(control.pressed_row, -1)

    def test_numeric_display_uses_excel_format_even_when_column_rounds(self):
        sheet = Mock(Name='Sheet1', Visible=-1)
        used = sheet.UsedRange
        used.Rows.Count = used.Columns.Count = used.Row = used.Column = 1
        used.Formula = used.Value2 = 1234.567
        sheet.Rows.return_value.Hidden = sheet.Columns.return_value.Hidden = False
        sheet.Cells.return_value.Text = '1235'
        sheet.Cells.return_value.NumberFormat = '#,##0.00'
        document = Mock(Worksheets=[sheet])
        app = Mock()
        app.WorksheetFunction.Text.return_value = '1,234.57'
        with patch.object(m, 'fingerprint', return_value='digest'), \
             patch.object(m, 'open_book', return_value=document):
            result = m.read_book(app, 'test.xlsx', load_first_style=False)
        cell = result.sheets['Sheet1'].cells[1, 1]
        self.assertEqual(cell.value, 1234.567)
        self.assertEqual(cell.display_text, '1,234.57')
        app.WorksheetFunction.Text.assert_called_once_with(1234.567, '#,##0.00')

    def test_checkbox_notification_is_deferred_until_native_state_changes(self):
        tree = ast.parse((ROOT/'controls/merge_documents.py').read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MergeFileList')
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'on_check')
        wx = Mock()
        scope = {'wx': wx}
        exec(compile(ast.Module(body=[method], type_ignores=[]), 'check', 'exec'), scope)
        control, event = Mock(), Mock()
        scope['on_check'](control, event)
        control.changed.assert_not_called()
        wx.CallAfter.assert_called_once_with(control.changed, None)
        event.Skip.assert_called_once()

    def test_unchecking_clears_choices_and_editors_from_existing_tabs(self):
        tree = ast.parse((ROOT/'controls/merge_documents.py').read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MergeDialog')
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'on_checks')
        scope = {'tr': lambda key: key}
        exec(compile(ast.Module(body=[method], type_ignores=[]), 'checks', 'exec'), scope)
        dialog, grid, table = Mock(), Mock(), Mock()
        dialog.notebook.GetPageCount.return_value = 1
        dialog.notebook.GetPage.return_value.grid = grid
        grid.GetTable.return_value = table
        table.conflicts = {(1, 2): object()}
        table.labels = {(1, 2): ['old', 'unchecked']}
        table.colors = {(1, 2): [(0, 0, 0), (1, 2, 3)]}
        table.grid_position.return_value = (0, 1)
        scope['on_checks'](dialog, None)
        self.assertEqual(table.conflicts, {})
        self.assertEqual(table.labels, {})
        self.assertEqual(table.colors, {})
        grid.DisableCellEditControl.assert_called_once()
        grid.SetAttr.assert_called_once_with(0, 1, table.build_attr.return_value)
        grid.ForceRefresh.assert_called_once()

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
        table = scope['SheetTable'](m.Sheet({(1, 1): conflict.values[0]}), {(1, 1): conflict}, source_colors={'source.xlsx': (1, 2, 3)})
        self.assertEqual(table.labels[1, 1], ['2', '2'])
        self.assertEqual(table.colors[1, 1], [(0, 0, 0), (1, 2, 3)])
        editor = scope['ColoredChoiceEditor'](table.labels[1, 1], table.colors[1, 1])
        editor.initial = 0
        editor.combo = Mock()
        editor.combo.GetSelection.return_value = 1
        grid = Mock()
        grid.GetTable.return_value = table
        self.assertEqual(editor.EndEdit(0, 0, grid, '2'), '1')
        editor.ApplyEdit(0, 0, grid)
        self.assertEqual(conflict.selected, 1)

        # A duplicate source must not recolor the original workbook's value.
        conflict.sources[0].append('source.xlsx')
        conflict.values[0] = m.EMPTY
        table = scope['SheetTable'](m.Sheet({(1, 1): m.Cell('base')}),
                                    {(1, 1): conflict}, source_colors={'source.xlsx': (1, 2, 3)})
        self.assertEqual(table.colors[1, 1][0], (0, 0, 0))
        editor = scope['ColoredChoiceEditor'](table.labels[1, 1], table.colors[1, 1])
        editor.initial = 1
        editor.combo = Mock()
        editor.combo.GetSelection.return_value = 0
        grid.GetTable.return_value = table
        self.assertEqual(editor.EndEdit(0, 0, grid, '2'), '0')
        editor.ApplyEdit(0, 0, grid)
        self.assertEqual(conflict.selected, 0)
        self.assertEqual(scope['display'](m.Cell('')), '')

    def test_shared_value_has_a_named_colored_choice_per_checked_source(self):
        from types import SimpleNamespace
        tree = ast.parse((ROOT/'common/sheet_table.py').read_text())
        definitions = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
        scope = {'gridlib': SimpleNamespace(GridTableBase=object, GridCellStringRenderer=object, GridCellEditor=object),
                 'engine': m, 'tr': lambda key: key, 'os': os,
                 'adv': SimpleNamespace(OwnerDrawnComboBox=object, ODCB_PAINTING_CONTROL=1),
                 'wx': SimpleNamespace(NOT_FOUND=-1)}
        exec(compile(ast.Module(body=definitions, type_ignores=[]), 'sheet_table', 'exec'), scope)
        base = book('base.xlsx', {(1, 1): 'base'})
        sources = [book(f'source{i}.xlsx', {(1, 1): 11}) for i in range(6)]
        checked = [sources[i] for i in (2, 3, 4)]
        conflict = m.conflicts_for(base, checked)[0]
        colors = {m.source_key(b.path): (i * 20, 100, 200) for i, b in enumerate(checked)}
        table = scope['SheetTable'](base.sheets['Sheet1'], {(1, 1): conflict}, source_colors=colors)
        self.assertEqual(table.labels[1, 1], ['base', '11', '11', '11'])
        self.assertEqual(table.choice_sources[1, 1], [m.source_key(b.path) for b in [base] + checked])
        self.assertEqual(table.colors[1, 1], [(0, 0, 0)] + list(colors.values()))
        self.assertEqual(table.selected_color((1, 1)), (0, 0, 0))
        editor = scope['ColoredChoiceEditor'](table.labels[1, 1], table.colors[1, 1], table.choice_sources[1, 1])
        editor.initial = 1
        editor.combo = Mock()
        editor.combo.GetSelection.return_value = 3
        grid = Mock()
        grid.GetTable.return_value = table
        self.assertEqual(editor.EndEdit(0, 0, grid, '11'), '3')
        editor.ApplyEdit(0, 0, grid)
        self.assertEqual(conflict.selected, 1)  # Same merge value, a different source.
        self.assertEqual(conflict.selected_source, m.source_key(checked[2].path))
        rebuilt = scope['SheetTable'](table.sheet, table.conflicts, source_colors=colors)
        self.assertEqual(rebuilt.selected_color((1, 1)), colors[conflict.selected_source])
        combo = Mock()
        combo.GetString.return_value = '11'
        combo.item_sources = table.choice_sources[1, 1]
        self.assertEqual(scope['ColoredComboBox'].item_text(combo, 3), '11  [source4.xlsx]')
        self.assertEqual(scope['ColoredComboBox'].item_text(combo, 3, 1), '11')

    def test_compare_reads_formats_only_from_checked_books(self):
        tree = ast.parse((ROOT/'controls/merge_documents.py').read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MergeDialog')
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'on_compare')
        scope = {'engine': m}
        exec(compile(ast.Module(body=[method], type_ignores=[]), 'compare', 'exec'), scope)
        dialog = Mock()
        dialog.base = book('base.xlsx', {(1, 1): 1})
        checked = book('checked.xlsx', {(1, 1): 2.5})
        unchecked = book('unchecked.xlsx', {(1, 1): 99})
        formatted = book('checked.xlsx', {})
        formatted.sheets['Sheet1'].cells[1, 1] = m.Cell(2.5, display_text='2,50 €')
        dialog.matches = [(checked, 1), (unchecked, 1)]
        dialog.files.GetCheckedItems.return_value = [0]
        color = dialog.files.GetItemTextColour.return_value
        color.Red.return_value, color.Green.return_value, color.Blue.return_value = 12, 34, 56
        app = Mock()
        @contextmanager
        def excel():
            yield app
        with patch.object(m, 'excel_app', excel), patch.object(m, 'fingerprint', return_value=''), \
             patch.object(m, 'read_book', return_value=formatted) as read:
            scope['on_compare'](dialog, None)
            conflicts = dialog.run_job.call_args.args[0]()
        read.assert_called_once_with(app, 'checked.xlsx', load_first_style=False)
        self.assertEqual(conflicts[0].sources, [[m.source_key('base.xlsx')], [m.source_key('checked.xlsx')]])
        self.assertEqual(conflicts[0].values[1].display_text, '2,50 €')
        self.assertEqual(dialog.source_colors, {m.source_key('base.xlsx'): (0, 0, 0),
                                                m.source_key('checked.xlsx'): (12, 34, 56)})
        dialog.files.GetCheckedItems.return_value = []
        dialog.run_job.call_args.args[1](conflicts)
        dialog.show_selected_book.assert_not_called()
        self.assertEqual(dialog.on_checks.call_count, 2)

    def test_numeric_display_uses_system_decimal_separator(self):
        from types import SimpleNamespace
        tree = ast.parse((ROOT/'common/sheet_table.py').read_text())
        definitions = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
        scope = {'gridlib': SimpleNamespace(GridTableBase=object, GridCellStringRenderer=object, GridCellEditor=object),
                 'engine': m, 'tr': lambda key: key, 'adv': SimpleNamespace(OwnerDrawnComboBox=object),
                 'wx': SimpleNamespace(NOT_FOUND=-1)}
        exec(compile(ast.Module(body=definitions, type_ignores=[]), 'sheet_table', 'exec'), scope)
        with patch.object(m, 'get_system_decimal_separator', return_value=','):
            self.assertEqual(scope['display'](m.Cell(1250.5)), '1250,5')
            self.assertEqual(scope['display'](m.Cell('1250.5')), '1250,5')
            self.assertEqual(scope['display'](m.Cell('text')), 'text')

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
        self.assertEqual(result[0].sources, [[m.source_key('base.xlsx')],
                                            [m.source_key('b.xlsx'), m.source_key('c.xlsx')]])

    def test_multiple_alternatives_require_choice(self):
        result = m.conflicts_for(book('a', {(1,1):'A'}),
                                 [book('b', {(1,1):'B'}), book('c', {(1,1):'C'})])
        self.assertIsNone(result[0].selected)
        self.assertEqual(len(result[0].values), 3)

    def test_blank_source_does_not_offer_to_erase_original(self):
        result = m.conflicts_for(book('a', {(1,1):'A', (1,2):'keep'}),
                                 [book('b', {(1,2):'keep'})])
        self.assertEqual(result, [])

    def test_only_original_empty_choice_is_kept(self):
        base = book('base', {(1, 2): 'keep'})
        blank = book('blank', {(1, 2): 'keep'})
        empty_formula = book('formula', {(1, 2): 'keep'})
        empty_formula.sheets['Sheet1'].cells[1, 1] = m.Cell('=""', True, '', '')
        zero = book('zero', {(1, 1): 0, (1, 2): 'keep'})
        false = book('false', {(1, 1): False, (1, 2): 'keep'})
        result = m.conflicts_for(base, [blank, empty_formula, zero, false])
        self.assertEqual(len(result), 1)
        self.assertEqual([cell.key for cell in result[0].values], [m.EMPTY.key, m.Cell(0).key, m.Cell(False).key])
        self.assertEqual(result[0].sources, [[m.source_key(p)] for p in ('base', 'zero', 'false')])

    def test_new_cells_are_included(self):
        result = m.conflicts_for(book('a', {(4,1):'keep'}),
                                 [book('b', {(4,1):'keep', (4,3):'new'})])
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
                base=m.Book(str(path),m.fingerprint(path),{'s': m.Sheet({(1,1):m.Cell('old')})})
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
                self.assertFalse(list(Path(d).glob('DocExplorer_merge_*')))
                if not fail:
                    self.assertEqual(base.digest, m.fingerprint(str(path)))
                    self.assertEqual(base.sheets['s'].cells[1,1].value, 'new')
                self.assertEqual(document.Close.call_count, 1 if fail else 2)

    def test_save_colors_changed_cell_fonts_and_preserves_fill(self):
        for color in (None, (255, 255, 0), (18, 52, 86), (0, 0, 0)):
            with self.subTest(color=color), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'original.xlsx'
                path.write_bytes(b'original')
                base = m.Book(str(path), m.fingerprint(path), {'s': m.Sheet(
                    {(1, col): m.Cell('old') for col in (1, 2, 3)}, styles_loaded=True)})
                cells = {col: Mock(HasArray=False, MergeCells=False) for col in (1, 2, 3)}
                for cell in cells.values():
                    cell.Font.Color = 123
                    cell.Interior.Color = 123
                    cell.Interior.Pattern = 9
                sheet = Mock(ProtectContents=False)
                sheet.Cells.side_effect = lambda row, col: cells[col]
                doc = Mock(ReadOnly=False)
                doc.Worksheets.return_value = sheet
                conflicts = [m.Conflict('s', 1, col, [m.Cell('old'), m.Cell(value)], [], selected)
                             for col, value, selected in ((1, 'new', 1), (2, None, 1), (3, 'reject', 0))]
                @contextmanager
                def app():
                    yield object()
                with patch.object(m, 'excel_app', app), patch.object(m, 'open_book', return_value=doc):
                    m.save_merge(base, conflicts, backup_original=False, change_color=color)
                expected = 123 if color is None else color[0] | color[1] << 8 | color[2] << 16
                self.assertEqual(cells[1].Font.Color, expected)
                self.assertEqual(cells[2].Font.Color, expected)
                self.assertEqual(cells[3].Font.Color, 123)
                for cell in cells.values():
                    self.assertEqual(cell.Interior.Color, 123)
                    self.assertEqual(cell.Interior.Pattern, 9)
                self.assertEqual(base.sheets['s'].styles_loaded, color is None)

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

    def test_uniform_hidden_rows_use_one_range_read(self):
        sheet = Mock()
        sheet.Range.return_value.EntireRow.Hidden = False
        self.assertEqual(m.axis_values(sheet, 'Rows', 10000, 'Hidden'),
                         dict.fromkeys(range(1, 10001), False))
        sheet.Range.assert_called_once()
        sheet.Rows.assert_not_called()

    def test_mixed_hidden_blocks_split_without_losing_rows(self):
        from types import SimpleNamespace
        hidden = {3, 4, 7}
        class Worksheet:
            def Cells(self, row, col):
                return row, col
            def Rows(self, row):
                return SimpleNamespace(Hidden=row in hidden)
            def Range(self, first, last):
                values = {row in hidden for row in range(first[0], last[0] + 1)}
                value = values.pop() if len(values) == 1 else None
                return SimpleNamespace(EntireRow=SimpleNamespace(Hidden=value))
        result = m.axis_values(Worksheet(), 'Rows', 8, 'Hidden')
        self.assertEqual({row for row, value in result.items() if value}, hidden)

    def test_search_cache_invalidates_content_and_reports_failed_files(self):
        with tempfile.TemporaryDirectory() as directory:
            base_path = Path(directory) / 'base.xlsx'
            other_path = Path(directory) / 'other.xlsx'
            base_path.write_bytes(b'base')
            other_path.write_bytes(b'other')
            def read(app, path, **kwargs):
                result = book(path, {(1, 1): 'same'})
                result.digest = m.fingerprint(path)
                return result
            base = read(None, str(base_path))
            cache, updates = {}, []
            @contextmanager
            def excel():
                yield object()
            with patch.object(m, 'excel_app', excel), patch.object(m, 'read_book', side_effect=read) as reader:
                for _ in range(2):
                    result = m.search_books(str(base_path), base, cache,
                                            lambda *args: updates.append(args))
                self.assertEqual(reader.call_count, 1)
                self.assertIs(result[0], base)
                self.assertEqual(updates[-1][:2], (1.0, 1))
                other_path.write_bytes(b'changed')
                m.search_books(str(base_path), base, cache)
                self.assertEqual(reader.call_count, 2)
                other_path.write_bytes(b'broken')
                reader.side_effect = RuntimeError('cannot open')
                result = m.search_books(str(base_path), base, cache,
                                        lambda *args: updates.append(args))
                self.assertEqual(len(result[2]), 1)
                self.assertEqual(updates[-1][:2], (1.0, 1))

    def test_general_text_cells_avoid_individual_excel_calls(self):
        sheet = Mock(Name='Visible', Visible=-1)
        used = sheet.UsedRange
        used.Rows.Count, used.Columns.Count = 1000, 1
        used.Row = used.Column = 1
        used.NumberFormat = 'General'
        used.Formula = used.Value2 = tuple(('text',) for _ in range(1000))
        sheet.Range.return_value.EntireRow.Hidden = False
        sheet.Columns.return_value.Hidden = False
        document = Mock(Worksheets=[sheet])
        updates = []
        with patch.object(m, 'fingerprint', return_value='digest'), patch.object(m, 'open_book', return_value=document):
            result = m.read_book(Mock(), 'test.xlsx', False, lambda *args: updates.append(args))
        self.assertEqual(len(result.sheets['Visible'].cells), 1000)
        # Only two endpoint Cells calls to inspect the entire row block.
        self.assertEqual(sheet.Cells.call_count, 0)
        self.assertEqual(updates[-1], (1, 1, 'Visible'))
        document.Close.assert_called_once_with(False)

    def test_empty_rows_do_not_produce_conflicts(self):
        base = book('base', {(1, 1): 'keep', (3, 1): 'base'})
        source = book('source', {(1, 1): 'keep', (2, 1): 'source'})
        self.assertEqual(m.conflicts_for(base, [source]), [])
        sheet = m.Sheet({(1, 1): m.Cell(None), (2, 1): m.Cell(''),
                         (3, 1): m.Cell(0), (4, 1): m.Cell(False),
                         (5, 1): m.Cell('=""', True, '', ''),
                         (6, 2): m.Cell('hidden column')}, hidden_cols={2})
        self.assertEqual(m.populated_rows(sheet), {3, 4, 5})

    def test_compact_grid_preserves_excel_addresses_and_edit_targets(self):
        from types import SimpleNamespace
        tree = ast.parse((ROOT/'common/sheet_table.py').read_text())
        definitions = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
        scope = {'gridlib': SimpleNamespace(GridTableBase=object, GridCellStringRenderer=object, GridCellEditor=object),
                 'engine': m, 'tr': lambda key: key, 'adv': SimpleNamespace(OwnerDrawnComboBox=object),
                 'wx': SimpleNamespace(NOT_FOUND=-1)}
        exec(compile(ast.Module(body=definitions, type_ignores=[]), 'sheet_table', 'exec'), scope)
        sheet = m.Sheet({(2, 1): m.Cell('hidden row'), (4, 1): m.Cell('old'),
                         (4, 3): m.Cell('old C'), (7, 1): m.Cell(0)}, 9, 4,
                        hidden_rows={2}, hidden_cols={2, 4})
        conflict = m.Conflict('Sheet1', 4, 3, [m.Cell('old C'), m.Cell('new C')], [['a'], ['b']], 0)
        table = scope['SheetTable'](sheet, {(4, 3): conflict})
        self.assertEqual((table.GetNumberRows(), table.GetNumberCols()), (2, 2))
        self.assertEqual([table.GetRowLabelValue(i) for i in range(2)], ['4', '7'])
        self.assertEqual([table.GetColLabelValue(i) for i in range(2)], ['A', 'C'])
        self.assertEqual(table.cell_position(0, 1), (4, 3))
        self.assertEqual(table.grid_position(4, 3), (0, 1))
        self.assertIsNone(table.grid_position(2, 1))
        table.SetValue(0, 1, 'new C')
        self.assertEqual(conflict.selected, 1)
        editor = scope['ColoredChoiceEditor'](table.labels[4, 3], table.colors[4, 3])
        editor.pending = 0
        grid = Mock()
        grid.GetTable.return_value = table
        editor.ApplyEdit(0, 1, grid)
        self.assertEqual(conflict.selected, 0)

    def test_source_selection_keeps_original_preview(self):
        tree = ast.parse((ROOT/'controls/merge_documents.py').read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MergeDialog')
        methods = [n for n in cls.body if isinstance(n, ast.FunctionDef)
                   and n.name in ('show_selected_book', 'on_select')]
        scope = {}
        exec(compile(ast.Module(body=methods, type_ignores=[]), 'merge_dialog', 'exec'), scope)
        dialog, event = Mock(), Mock()
        scope['show_selected_book'](dialog)
        dialog.show_book.assert_called_once_with(dialog.base, True)
        dialog.show_book.reset_mock()
        scope['on_select'](dialog, event)
        dialog.show_book.assert_not_called()
        event.Skip.assert_called_once()

    def test_saved_hidden_axes_reads_grouped_columns(self):
        import zipfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.xlsx'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('xl/workbook.xml', '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Test" r:id="rId1"/></sheets></workbook>')
                archive.writestr('xl/_rels/workbook.xml.rels', '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
                archive.writestr('xl/worksheets/sheet1.xml', '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><cols><col min="4" max="5" hidden="1"/><col min="9" max="9" hidden="1"/></cols><sheetData><row r="3" hidden="1"/><row r="6" hidden="1"/><row r="10" hidden="1"/></sheetData></worksheet>')
            self.assertEqual(m.saved_hidden_axes(str(path)), {'Test': ({3,6,10}, {4,5,9})})

    def test_save_completion_keeps_dialog_open(self):
        tree = ast.parse((ROOT/'controls/merge_documents.py').read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MergeDialog')
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'on_save')
        done = next(n for n in method.body if isinstance(n, ast.FunctionDef) and n.name == 'done')
        dialog = Mock()
        scope = {'self': dialog, 'tr': lambda key: key}
        exec(compile(ast.Module(body=[done], type_ignores=[]), 'save_done', 'exec'), scope)
        scope['done'](None)
        dialog.EndModal.assert_not_called()
        self.assertFalse(dialog.saving)
        self.assertFalse(dialog.compared)
        self.assertTrue(dialog.saved_changes)
        dialog.cancel_button.Enable.assert_called_once()

    def test_values_only_does_not_fetch_text_or_styles(self):
        sheet = Mock(Name='Sheet1', Visible=-1)
        used = sheet.UsedRange
        used.Rows.Count, used.Columns.Count = 1, 3
        used.Row = used.Column = 1
        used.Formula = used.Value2 = (('00123', 42, 'plain'),)
        sheet.Rows.return_value.Hidden = False
        sheet.Columns.return_value.Hidden = False
        document = Mock(Worksheets=[sheet])
        with patch.object(m, 'fingerprint', return_value='digest'), patch.object(m, 'open_book', return_value=document), patch.object(m, 'read_sheet_layout') as layout:
            result = m.read_book(Mock(), 'test.xlsx', values_only=True)
        layout.assert_not_called()
        sheet.Cells.assert_not_called()
        self.assertEqual(result.sheets['Sheet1'].cells[1,1].value, '00123')
        self.assertIsNone(result.sheets['Sheet1'].cells[1,1].display_text)

    def test_checkbox_change_does_not_rebuild_tabs(self):
        tree = ast.parse((ROOT/'controls/merge_documents.py').read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MergeDialog')
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'on_checks')
        scope = {'tr': lambda key: key}
        exec(compile(ast.Module(body=[method], type_ignores=[]), 'on_checks', 'exec'), scope)
        dialog = Mock()
        dialog.notebook.GetPageCount.return_value = 0
        scope['on_checks'](dialog, None)
        dialog.show_selected_book.assert_not_called()
        dialog.notebook.DeleteAllPages.assert_not_called()
        self.assertEqual(dialog.conflicts, [])
        self.assertFalse(dialog.compared)

    def test_save_keeps_numeric_text_as_text(self):
        class Cell:
            HasArray = MergeCells = False
            NumberFormat = 'General'
            value = None
            @property
            def Value2(self):
                return self.value
            @Value2.setter
            def Value2(self, value):
                self.value = (int(value) if self.NumberFormat != '@' and
                              isinstance(value, str) and value.isdigit() else value)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'base.xlsx'
            path.write_bytes(b'original')
            base = m.Book(str(path), m.fingerprint(path), {'Sheet1': m.Sheet({(1,1): m.Cell('old')})})
            cell = Cell()
            sheet = Mock(ProtectContents=False)
            sheet.Cells.return_value = cell
            document = Mock(ReadOnly=False)
            document.Worksheets.return_value = sheet
            def opened(app, filename, **kwargs):
                document.Save.side_effect = lambda: Path(filename).write_bytes(b'saved')
                return document
            @contextmanager
            def excel():
                yield object()
            conflict = m.Conflict('Sheet1', 1, 1, [m.Cell('old'), m.Cell('00123')], [['a'], ['b']], 1)
            with patch.object(m, 'excel_app', excel), patch.object(m, 'open_book', opened):
                m.save_merge(base, [conflict])
            self.assertEqual(cell.Value2, '00123')
            self.assertEqual(cell.NumberFormat, 'General')
            self.assertEqual(path.read_bytes(), b'saved')

    def test_save_numeric_string_uses_system_decimal_separator(self):
        class Cell:
            HasArray = MergeCells = False
            NumberFormat = 'General'
            value = None
            @property
            def Value2(self):
                return self.value
            @Value2.setter
            def Value2(self, value):
                self.value = value
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'base.xlsx'
            path.write_bytes(b'original')
            base = m.Book(str(path), m.fingerprint(path), {'Sheet1': m.Sheet({(1,1): m.Cell('old')})})
            cell = Cell()
            sheet = Mock(ProtectContents=False)
            sheet.Cells.return_value = cell
            document = Mock(ReadOnly=False)
            document.Worksheets.return_value = sheet
            def opened(app, filename, **kwargs):
                document.Save.side_effect = lambda: Path(filename).write_bytes(b'saved')
                return document
            @contextmanager
            def excel():
                yield object()
            conflict = m.Conflict('Sheet1', 1, 1, [m.Cell('old'), m.Cell('1250.5')], [['a'], ['b']], 1)
            with patch.object(m, 'excel_app', excel), patch.object(m, 'open_book', opened), \
                 patch.object(m, 'get_system_decimal_separator', return_value=','):
                m.save_merge(base, [conflict])
            self.assertEqual(cell.Value2, 1250.5)
            self.assertEqual(cell.NumberFormat, 'General')
            self.assertEqual(path.read_bytes(), b'saved')

    def test_all_languages_have_merge_labels(self):
        required=set()
        for module in ('controls/merge_documents.py','file_operations/excel_merge.py',
                       'file_operations/word_merge.py','common/sheet_table.py'):
            tree=ast.parse((ROOT/module).read_text())
            for node in ast.walk(tree):
                if (isinstance(node,ast.Constant) and isinstance(node.value,str)
                        and node.value.startswith(('merge_', 'word_merge_'))):
                    required.add(node.value)
        english = {}
        exec((ROOT/'localization/localization_en.py').read_text(encoding='utf-8'), english)
        def placeholders(text):
            return {name for _, name, _, _ in Formatter().parse(text) if name is not None}
        for path in (ROOT/'localization').glob('localization_*.py'):
            env={};exec(compile(path.read_text(encoding='utf-8'),str(path),'exec'),env)
            self.assertFalse(required-set(env['TRANSLATIONS']), (path.name,required-set(env['TRANSLATIONS'])))
            for key in required:
                value = env['TRANSLATIONS'][key]
                self.assertTrue(value.strip(), (path.name, key))
                self.assertEqual(placeholders(value), placeholders(english['TRANSLATIONS'][key]),
                                 (path.name, key))


if __name__=='__main__':unittest.main()
