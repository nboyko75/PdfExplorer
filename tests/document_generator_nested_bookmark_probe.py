"""Live Word regression: the existing + action can link a value inside a table."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from file_operations.document_generator import DocumentGenerator, GeneratorError


def run(folder):
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    app = None
    try:
        app = win32com.client.DispatchEx('Word.Application')
        app.Visible = False
        app.DisplayAlerts = 0
        app.AutomationSecurity = 3
        for extension, file_format in (('.docx', 12), ('.doc', 0), ('.docm', 13)):
            source = folder / ('nested' + extension)
            document = app.Documents.Add(Visible=False)
            try:
                document.Content.Text = 'Customer\r'
                end = document.Content.End - 1
                table = document.Tables.Add(document.Range(end, end), 2, 2)
                table.Cell(1, 1).Range.Text = 'Before NAME after'
                table.Cell(1, 2).Range.Text = 'Other cell'
                table.Cell(2, 1).Range.Text = 'Unmanaged row'
                document.SaveAs2(FileName=str(source), FileFormat=file_format, AddToRecentFiles=False)
                session = DocumentGenerator(str(source))
                session.app, session.document = app, document
                document.Activate()
                document.Range(0, 8).Select()
                session.add_selection()
                session.update_rows([dict(session.rows[0], value='Shared\nvalue', uid=True)])
                table.Rows(1).Range.Select()
                session.add_table_selection()
                start = table.Cell(1, 1).Range.Start + len('Before ')
                document.Range(start, start + len('NAME')).Select()
                session.add_selection(0)  # The existing row + button.
                child = session.rows[1]['name']
                assert session.rows[0]['group'] == session.rows[1]['group']
                assert session.rows[1]['value'] == 'Shared\nvalue'
                assert document.Bookmarks(child).Range.Text == 'NAME'
                try:
                    session.add_selection(0)
                except GeneratorError:
                    pass
                else:
                    raise AssertionError('Overlapping value bookmarks were accepted')

                # Table growth and edits in another cell must keep the child.
                values = deepcopy(session.tables[0]['rows'])
                values[0][1] = 'Edited other cell'
                values.append(['New row', 'New cell'])
                session.update_fields(session.snapshot(), [{'name': 'Products', 'rows': values}])
                session.save_document()
                session.save_document()
                assert table.Rows.Count == 3
                assert document.Bookmarks(child).Range.Text == 'NAME'
                assert document.Bookmarks(child).Range.Start == table.Cell(1, 1).Range.Start + len('Before ')
                expected = session.state()
                document.Close(False)
                document = app.Documents.Open(FileName=str(source), Visible=False, AddToRecentFiles=False)
                session.document = document
                session.rows, session.tables = session._load_rows(), session._load_tables()
                assert session.state() == expected
                assert sum(row.get('uid', False) for row in session.rows) == 1
                output_path = folder / ('output' + extension)
                session.export_document(str(output_path))
                output = app.Documents.Open(FileName=str(output_path), ReadOnly=True, Visible=False,
                                            AddToRecentFiles=False)
                try:
                    assert output.Tables(1).Cell(1, 1).Range.Text == 'Before Shared\rvalue after\r\x07'
                    assert output.Tables(1).Cell(1, 2).Range.Text == 'Edited other cell\r\x07'
                    assert output.Tables(1).Cell(2, 1).Range.Text == 'New row\r\x07'
                    assert output.Tables(1).Cell(3, 1).Range.Text == 'Unmanaged row\r\x07'
                finally:
                    output.Close(False)
                print('PASS:', extension, 'nested +, shared value, table growth, save/reopen and export', flush=True)
            finally:
                document.Close(False)
    finally:
        if app is not None:
            app.Quit(0)
        pythoncom.CoUninitialize()


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='nested-bookmark-', dir=Path(__file__).resolve().parents[1] / 'tmp') as folder:
        run(Path(folder))
