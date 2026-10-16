"""Live Word table-generator regression checks on temporary synthetic files."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from file_operations.document_generator import DocumentGenerator, GeneratorError, TABLE_STATE_VARIABLE


def cell_text(table, row, column):
    return DocumentGenerator._cell_text(table.Cell(row, column))


def merged_cases(app, folder, extension, format_code):
    for kind in ('horizontal_header', 'horizontal_template', 'vertical_header', 'vertical_template'):
        source = folder / (kind + extension)
        document = app.Documents.Add(Visible=False)
        session = DocumentGenerator(str(source))
        session.app, session.document = app, document
        try:
            table = document.Tables.Add(document.Range(0, 0), 5, 3)
            for row in range(1, 6):
                for column in range(1, 4):
                    table.Cell(row, column).Range.Text = f'{row}:{column}'
            if kind == 'horizontal_header':
                table.Cell(1, 1).Merge(table.Cell(1, 3))
            elif kind == 'horizontal_template':
                table.Cell(3, 1).Merge(table.Cell(3, 2))
                table.Cell(5, 1).Merge(table.Cell(5, 3))
            elif kind == 'vertical_header':
                table.Cell(1, 1).Merge(table.Cell(2, 1))
            else:
                table.Cell(2, 1).Merge(table.Cell(3, 1))
            template = session._table_rows(table)[2]
            template.Font.Bold = True
            template.Shading.BackgroundPatternColor = 65535
            template.Select()
            document.SaveAs2(FileName=str(source), FileFormat=format_code, AddToRecentFiles=False)
            session.add_table_selection()
            columns = len(session.tables[0]['widths'])
            assert columns == (2 if kind in ('horizontal_template', 'vertical_template') else 3)
            widths = session.tables[0]['widths']
            original_rows = session._table_rows(table)
            before = [row.Text for row in original_rows[:2]]
            after = [row.Text for row in original_rows[3:]]
            values = [{'name': 'Merged', 'rows': [
                [f'Edited {col}' for col in range(columns)],
                [f'Added {col}' for col in range(columns)]]}]
            session.update_fields([], values)
            session.save_document()
            session.save_document()
            rows = session._table_rows(table)
            assert len(rows) == 6, kind
            assert [row.Text for row in rows[:2]] == before, kind
            assert [row.Text for row in rows[4:]] == after, kind
            for offset, expected in enumerate(values[0]['rows'], 2):
                assert [session._cell_text(cell) for cell in rows[offset].Cells] == expected, kind
                assert rows[offset].Cells.Count == columns, kind
                assert rows[offset].Font.Bold == -1, kind
                for col, width in enumerate(widths, 1):
                    assert abs(rows[offset].Cells(col).Width - width) < 1, kind
            result = folder / (kind + '-result' + extension)
            session.export_document(str(result))
            document.Close(False)
            session.document = document = app.Documents.Open(FileName=str(source), Visible=False)
            session.tables = session._load_tables()
            assert session.tables[0]['rows'] == values[0]['rows'], kind
            session.save_document()
            # Shrinking must remove whole rows, including merged cells.
            values[0]['rows'] = values[0]['rows'][:1]
            session.update_fields([], values)
            session.save_document()
            rows = session._table_rows(document.Tables(1))
            assert len(rows) == 5, kind
            assert [row.Text for row in rows[:2]] == before, kind
            assert [row.Text for row in rows[3:]] == after, kind
            document.Close(False)
            session.document = document = app.Documents.Open(FileName=str(result), ReadOnly=True, Visible=False)
            rows = session._table_rows(document.Tables(1))
            assert len(rows) == 6, kind
            assert session._cell_text(rows[3].Cells(1)) == 'Added 0', kind
            print(f'PASS {extension} {kind}: merged layout, formatting, Save/reopen/Export and shrink', flush=True)
        finally:
            document.Close(False)
            session.app = session.document = None


def run(folder):
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    app = session = None
    try:
        app = win32com.client.DispatchEx('Word.Application')
        app.Visible = False
        app.DisplayAlerts = 0
        app.AutomationSecurity = 3
        for extension, format_code in (('.docx', 12), ('.doc', 0), ('.docm', 13)):
            merged_cases(app, folder, extension, format_code)
            source = folder / ('tables' + extension)
            document = app.Documents.Add(Visible=False)
            document.Content.Text = 'Customer\r'
            end = document.Range(document.Content.End - 1, document.Content.End - 1)
            table = document.Tables.Add(end, 4, 3)
            for row in range(1, 5):
                for column in range(1, 4):
                    table.Cell(row, column).Range.Text = f'Row {row} cell {column}'
            table.Rows(2).Range.Font.Bold = True
            table.Rows(2).Shading.BackgroundPatternColor = 65535
            table.Rows(2).Cells(1).Width = 80
            document.SaveAs2(FileName=str(source), FileFormat=format_code, AddToRecentFiles=False)
            table = None
            document.Close(False)
            document = None
            session = DocumentGenerator(str(source))
            session.open()
            session.document.Range(0, 8).Select()
            session.add_selection()
            session.update_rows([{'name': 'Customer', 'value': 'Export customer'}])
            table = session.document.Tables(1)
            # Partial cells cannot accidentally turn into managed full rows.
            table.Cell(2, 1).Range.Select()
            try:
                session.add_table_selection()
            except GeneratorError:
                pass
            else:
                raise AssertionError('Partial row was accepted')
            area = table.Rows(1).Range.Duplicate
            area.End = table.Rows(2).Range.End
            area.Select()
            session.add_table_selection()
            assert session.tables[0]['rows'] == [['Row 2 cell 1', 'Row 2 cell 2', 'Row 2 cell 3']]
            widths = list(session.tables[0]['widths'])
            assert widths[0] != widths[1]
            assert table.Rows.Count == 4, 'Adding an editor must not insert Word rows'
            values = [{'name': 'Products', 'rows': [
                ['Updated first', 'Україна\n日本', '10'], ['Added second', 'Description', '20']]}]
            session.update_fields(session.snapshot(), values)
            assert table.Rows.Count == 4
            session.save_document()
            assert table.Rows.Count == 5, table.Rows.Count
            assert cell_text(table, 1, 1) == 'Row 1 cell 1'
            assert cell_text(table, 2, 1) == 'Updated first'
            assert cell_text(table, 2, 2) == 'Україна\n日本'
            assert cell_text(table, 3, 1) == 'Added second'
            assert cell_text(table, 4, 1) == 'Row 3 cell 1'
            assert cell_text(table, 5, 1) == 'Row 4 cell 1'
            assert table.Rows(3).Range.Font.Bold == -1
            assert table.Rows(3).Shading.BackgroundPatternColor == 65535
            assert abs(table.Cell(3, 1).Width - widths[0]) < 1
            session.save_document()
            assert table.Rows.Count == 5, 'Repeated save duplicated rows'
            result = folder / ('result' + extension)
            session.export_document(str(result))
            assert table.Rows.Count == 5
            output = app.Documents.Open(FileName=str(result), ReadOnly=True, Visible=False)
            assert output.Range(0, 15).Text == 'Export customer'
            assert output.Tables(1).Rows.Count == 5
            assert cell_text(output.Tables(1), 3, 1) == 'Added second'
            assert all(output.Variables.Item(i).Name != TABLE_STATE_VARIABLE
                       for i in range(1, output.Variables.Count + 1))
            output.Close(False)
            output = None
            table = None
            session.close_document()
            session = DocumentGenerator(str(source))
            session.open()
            assert session.tables[0]['applied_rows'] == 2
            assert session.tables[0]['rows'] == values[0]['rows']
            table = session.document.Tables(1)
            values[0]['rows'].append(['Third', 'More', '30'])
            session.update_fields(session.snapshot(), values)
            session.save_document()
            assert table.Rows.Count == 6
            assert cell_text(table, 4, 1) == 'Third'
            assert cell_text(table, 5, 1) == 'Row 3 cell 1'
            # A failure after insertion must roll back the structural changes.
            before_text = session.document.Content.Text
            before_state = deepcopy(session.tables)
            values[0]['rows'].append(['Rollback', '', ''])
            session.update_fields(session.snapshot(), values)
            copy_row = session._copy_row_style
            def fail_after_copy(source, target):
                copy_row(source, target)
                raise RuntimeError('Injected failure')
            with patch.object(session, '_copy_row_style', side_effect=fail_after_copy):
                try:
                    session.save_document()
                except RuntimeError:
                    pass
                else:
                    raise AssertionError('Expected injected failure')
            assert session.document.Content.Text == before_text
            assert session.tables[0]['applied_rows'] == before_state[0]['applied_rows']
            session.save_document()
            assert table.Rows.Count == 7, 'Retry after rollback duplicated rows'
            # Adjacent managed blocks must remain separate through growth.
            table.Rows(6).Range.Select()
            session.add_table_selection()
            all_values = [{'name': item['name'], 'rows': deepcopy(item['rows'])} for item in session.tables]
            all_values[0]['rows'].append(['Another', '', ''])
            all_values[1]['rows'].append(['Other block', '', ''])
            session.update_fields(session.snapshot(), all_values)
            session.save_document()
            count = table.Rows.Count
            session.save_document()
            assert table.Rows.Count == count
            session.close_document()
            session = None
            table = None
            print(f'PASS {extension}: last selected row, cells/formatting, Save/reopen/Export, rollback, multiple tables and repeated saves', flush=True)
    finally:
        if session is not None and session.app is not None:
            session.app.Quit(0)
            session.detach()
        if app is not None:
            app.Quit(0)
        app = session = None
        pythoncom.CoUninitialize()


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='generator-tables-probe-') as folder:
        run(Path(folder))
