"""Microsoft Word integration check, using only owned synthetic documents.

Run: python tests/word_merged_tables_probe.py
"""
from pathlib import Path
from contextlib import contextmanager
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from file_operations import word_merge as m


def fixture(app, path, file_format, vertical, extended):
    doc = app.Documents.Add(Visible=False)
    try:
        doc.Content.Text = 'Before table\rAfter table\r'
        doc.Sections(1).Headers(1).Range.Text = 'Keep header'
        table = doc.Tables.Add(doc.Range(13, 13), 4 if extended else 3, 4 if extended else 3)
        table.Borders.Enable = True
        table.Range.Font.Name = 'Arial'
        if vertical:
            values = ([['Group', 'Item', 'Extra', 'Color'], ['Team', 'A', 'X', 'Blue'],
                       ['', 'Added', 'Y', 'New'], ['', 'B', 'Z', 'End']] if extended else
                      [['Group', 'Item', 'Color'], ['Team', 'A', 'Red'], ['', 'B', 'End']])
        else:
            values = ([['Heading', '', '', ''], ['Item', 'Extra', 'Color', 'Size'],
                       ['Added', 'X', 'Green', 'Medium'], ['Car', 'Y', 'Blue', 'Small']] if extended else
                      [['Heading', '', ''], ['Item', 'Color', 'Size'], ['Car', 'Red', 'Small']])
        for r, row in enumerate(values, 1):
            for c, text in enumerate(row, 1):
                table.Cell(r, c).Range.Text = text
        if vertical:
            table.Cell(2, 1).Merge(table.Cell(len(values), 1))
            table.Cell(2, 1).Range.Text = 'Team'
            table.Cell(2, 1).Shading.BackgroundPatternColor = 0xCCEEFF
        else:
            table.Cell(1, 1).Merge(table.Cell(1, len(values[0])))
            table.Cell(1, 1).Range.Text = 'Heading'
            table.Cell(1, 1).Range.Font.Bold = True
        doc.SaveAs2(FileName=str(path), FileFormat=file_format, AddToRecentFiles=False)
    finally:
        table = None
        doc.Close(False)


def run(folder):
    # Reuse one owned instance; rapidly restarting Word can race its shutdown.
    with m.word_app() as app:
        @contextmanager
        def session():
            yield app
        with patch.object(m, 'word_app', session):
            run_cases(folder)


def run_cases(folder):
    for extension, file_format in (('.docx', 12), ('.docm', 13), ('.doc', 0)):
        for vertical in (False, True):
            label = extension + (' vertical' if vertical else ' horizontal')
            print(label, 'creating fixtures', flush=True)
            original = folder / ('original' + str(vertical) + extension)
            changed = folder / ('changed' + str(vertical) + extension)
            with m.word_app() as app:
                fixture(app, original, file_format, vertical, False)
                fixture(app, changed, file_format, vertical, True)
                base = m.read_document(app, str(original))
                other = m.read_document(app, str(changed))
            assert base.tables[0].cells, (label, 'base snapshot missing')
            assert other.tables[0].cells, (label, 'source snapshot missing')
            original_bytes = original.read_bytes()
            print(label, 'preparing merged structure', base.tables[0].layout(), flush=True)
            prepared, sources = m.prepare_structure(base, [other], str(folder / 'prepared'))
            assert prepared.original is base, label
            assert original.read_bytes() == original_bytes
            assert prepared.tables[0].layout() == other.tables[0].layout(), (label, prepared.tables[0].layout())
            conflicts, skipped = m.conflicts_for(prepared, sources, add_structure=True)
            assert not skipped, (label, skipped)
            assert ['Red', 'Blue'] in [c.values for c in conflicts], (label, conflicts)
            assert all(c.selected == 1 for c in conflicts)
            preview = m.render_preview(prepared, str(folder / 'preview'), conflicts, {},
                                       {'choose': 'Choose', 'empty': 'Empty', 'keep': 'Keep'}, 'merged')
            assert '<select ' in Path(preview).read_text(encoding='utf-8')
            m.save_merge(prepared, conflicts)
            assert original.with_name(original.stem + '.merge-backup' + extension).read_bytes() == original_bytes
            with m.word_app() as app:
                verified = m.read_document(app, str(original))
                assert verified.text == other.text, (label, repr(verified.text), repr(other.text))
                assert verified.tables[0].layout() == other.tables[0].layout()
                doc = m.open_document(app, str(original))
                try:
                    assert 'Keep header' in doc.Sections(1).Headers(1).Range.Text
                    assert doc.Tables(1).Range.Font.Name == 'Arial'
                    if vertical:
                        assert doc.Tables(1).Cell(2, 1).Shading.BackgroundPatternColor == 0xCCEEFF
                    else:
                        assert doc.Tables(1).Cell(1, 1).Range.Font.Bold == -1
                finally:
                    doc.Close(False)
            print(label, 'snapshot, structure, preview, save, backup and formatting passed', flush=True)


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='docexplorer_merged_word_') as folder:
        run(Path(folder))
