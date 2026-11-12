"""Merged-table snapshots, structural additions, and lossless XML expansion."""
from contextlib import contextmanager
from html import escape
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from file_operations import word_merge as m
from file_operations import word_table_structure as s


def table_xml(rows, cols, spans, values):
    cells = {}
    for (r, c), (h, w) in spans.items():
        for row in range(r, r + h):
            props = '<w:gridSpan w:val="%s"/>' % w if w > 1 else ''
            if h > 1:
                props += '<w:vMerge w:val="%s"/>' % ('restart' if row == r else 'continue')
            text = escape(values.get((r, c), '')) if row == r else ''
            cells[row, c] = ('<w:tc><w:tcPr><w:tcW w:w="1000" w:type="dxa"/>'
                             '<w:shd w:fill="ABCDEF"/>%s</w:tcPr>'
                             '<w:p><w:pPr><w:jc w:val="center"/></w:pPr>'
                             '<w:r><w:rPr><w:b/></w:rPr><w:t>%s</w:t></w:r></w:p></w:tc>') % (props, text)
    grid = '<w:tblGrid>' + '<w:gridCol w:w="1000"/>' * cols + '</w:tblGrid>'
    body = ''.join('<w:tr>' + ''.join(tc for (rr, _), tc in sorted(cells.items()) if rr == r) + '</w:tr>'
                   for r in range(1, rows + 1))
    return ('<pkg:package xmlns:pkg="http://schemas.microsoft.com/office/2006/xmlPackage" '
            'xmlns:w="%s" xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
            'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml">'
            '<pkg:part pkg:name="/word/document.xml"><pkg:xmlData><w:document mc:Ignorable="w14">'
            '<w:body><w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/></w:tblPr>%s%s</w:tbl>'
            '</w:body></w:document></pkg:xmlData></pkg:part></pkg:package>') % (s.W, grid, body)


def layout(rows, cols, merged=()):
    spans = dict(merged)
    covered = set().union(*(s.coverage(pos, span) for pos, span in spans.items())) if spans else set()
    spans.update({(r, c): (1, 1) for r in range(1, rows + 1) for c in range(1, cols + 1)
                  if (r, c) not in covered})
    return dict(sorted(spans.items()))


def snapshot(rows, cols, spans, values, path='original.docx'):
    text, cells, word_cells = '', {}, []
    for pos in sorted(spans):
        value = values.get(pos, '')
        start = len(text)
        text += value
        cells[pos] = start, len(text)
        text += '\r\x07'
        word_cells.append(SimpleNamespace(Tables=SimpleNamespace(Count=1), Range=SimpleNamespace(
            Start=m.word_offset(text, start), End=m.word_offset(text, len(text)))))
    table = SimpleNamespace(Range=SimpleNamespace(
        Start=0, End=m.word_offset(text, len(text)), Cells=word_cells,
        WordOpenXML=table_xml(rows, cols, spans, values)))
    doc = m.Document(path, '', text + '\r')
    doc.tables = m.table_snapshot(SimpleNamespace(Tables=[table]), doc.text)
    return doc


class MergedTableTests(unittest.TestCase):
    def test_xml_replacement_only_removes_words_extra_paragraph(self):
        for suffix in ('\rAfter\r', '\r\rAfter\r', 'Damaged\r'):
            with self.subTest(suffix=suffix):
                doc = Mock()
                doc.Content.End = 50
                doc.Tables.return_value.Range.Start = 10
                doc.Tables.return_value.Range.End = 30
                before, insertion, after, extra = Mock(Text='\rAfter\r'), Mock(), Mock(Text=suffix), Mock()
                doc.Range.side_effect = [before, insertion, after, extra]
                if suffix == 'Damaged\r':
                    with self.assertRaises(m.MergeError):
                        m.replace_table_xml(doc, 0, '<xml/>')
                else:
                    m.replace_table_xml(doc, 0, '<xml/>')
                doc.Tables.return_value.Delete.assert_called_once_with()
                insertion.InsertXML.assert_called_once_with('<xml/>')
                if suffix == '\r\rAfter\r':
                    extra.Delete.assert_called_once_with()
                else:
                    extra.Delete.assert_not_called()

    def test_snapshot_uses_xml_grid_and_utf16_ranges(self):
        spans = layout(3, 3, [((1, 1), (1, 3)), ((2, 1), (2, 1))])
        values = {(1, 1): 'Heading', (2, 1): 'Group', (3, 3): 'Blue \U0001f600'}
        doc = snapshot(3, 3, spans, values)
        self.assertEqual(doc.tables[0].layout(), spans)
        self.assertEqual((doc.tables[0].rows, doc.tables[0].cols), (3, 3))
        self.assertEqual({pos: doc.text[a:b] for pos, (a, b) in doc.tables[0].cells.items()},
                         {pos: values.get(pos, '') for pos in spans})

    def test_additions_inside_horizontal_and_vertical_spans(self):
        spans = layout(3, 3, [((1, 1), (1, 3)), ((2, 1), (2, 1))])
        values = {pos: str(pos) for pos in spans}
        xml = table_xml(3, 3, spans, values)
        rm, cm = {1: 1, 2: 2, 3: 4}, {1: 1, 2: 2, 3: 4}
        shape = s.union_spans([s.mapped_spans(spans, rm, cm)], 4, 4)
        result = s.resize_table(xml, rm, cm, 4, 4, shape)
        self.assertEqual(s.read_layout(result), (4, 4, shape))
        self.assertEqual(shape[1, 1], (1, 4))
        self.assertEqual(shape[2, 1], (3, 1))
        package, table = s.table_xml(result)
        _, _, _, physical = s.geometry(table)
        for (r, c), value in values.items():
            tc = physical[rm[r], cm[c]]
            self.assertIn('>%s<' % value, tc.toxml())
            self.assertIn('<w:b/>', tc.toxml())
            self.assertIn('ABCDEF', tc.toxml())
        for pos in set(shape) - {(rm[r], cm[c]) for r, c in spans}:
            self.assertFalse(physical[pos].getElementsByTagNameNS(s.W, 't'))
        self.assertIn('xmlns:w14=', result)  # mc:Ignorable names remain declared.
        self.assertIn('w:tblStyle w:val="TableGrid"', result)
        package.unlink()

    def test_source_merges_in_added_space_and_overlapping_sources(self):
        original = layout(2, 2)
        rm, cm = {1: 1, 2: 3}, {1: 1, 2: 2}
        original = s.mapped_spans(original, rm, cm)
        source = layout(3, 2, [((2, 1), (1, 2))])
        shape = s.union_spans([original, source, layout(3, 2)], 3, 2)
        self.assertEqual(shape[2, 1], (1, 2))
        self.assertNotIn((2, 2), shape)

    def test_preparation_and_choices_include_new_merged_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'original.docx'
            path.write_bytes(b'original')
            spans = layout(3, 2, [((1, 1), (1, 2))])
            values = {(1, 1): 'Heading', (2, 1): 'A', (2, 2): 'Red', (3, 1): 'B', (3, 2): 'End'}
            base = snapshot(3, 2, spans, values, str(path))
            base.digest = m.fingerprint(path)
            other_spans = layout(4, 2, [((1, 1), (1, 2)), ((3, 1), (1, 2))])
            other_values = {(1, 1): 'Heading', (2, 1): 'A', (2, 2): 'Blue', (3, 1): 'Added',
                            (4, 1): 'B', (4, 2): 'End'}
            other = snapshot(4, 2, other_spans, other_values, 'other.docx')
            prepared_values = dict(other_values)
            prepared_values[2, 2], prepared_values[3, 1] = 'Red', ''
            prepared_copy = snapshot(4, 2, other_spans, prepared_values)
            doc = Mock()
            doc.Tables.return_value.Range.Start = 0
            doc.Tables.return_value.Range.End = 50
            doc.Content.End = 51
            doc.Tables.return_value.Range.WordOpenXML = table_xml(3, 2, spans, values)
            @contextmanager
            def app():
                yield object()
            with patch.object(m, 'word_app', app), patch.object(m, 'open_document', return_value=doc), \
                    patch.object(m, 'read_document', return_value=prepared_copy):
                prepared, sources = m.prepare_structure(base, [other], folder)
            inserted = doc.Range.return_value.InsertXML.call_args.args[0]
            doc.Tables.return_value.Delete.assert_called_once_with()
            self.assertEqual(s.read_layout(inserted), (4, 2, other_spans))
            doc.Tables.return_value.Rows.Add.assert_not_called()
            doc.Tables.return_value.Columns.Add.assert_not_called()
            conflicts, skipped = m.conflicts_for(prepared, sources, add_structure=True)
            self.assertFalse(skipped)
            self.assertEqual([c.values for c in conflicts], [['Red', 'Blue'], ['', 'Added']])
            self.assertEqual(path.read_bytes(), b'original')
            self.assertEqual(other.tables[0].layout(), other_spans)
            self.assertIs(prepared.original, base)

    def test_topology_changes_do_not_overwrite_original_merges(self):
        base = snapshot(2, 2, layout(2, 2, [((1, 1), (1, 2))]), {(1, 1): 'Heading'})
        other = snapshot(2, 2, layout(2, 2), {(1, 1): 'Split', (1, 2): 'Other'}, 'other.docx')
        conflicts, skipped = m.conflicts_for(base, [other], add_structure=True)
        self.assertFalse(conflicts)
        self.assertEqual(skipped, [('other.docx', 2)])

    def test_protected_merged_table_is_not_rebuilt(self):
        base = snapshot(2, 2, layout(2, 2, [((1, 1), (1, 2))]), {(1, 1): 'Heading', (2, 1): 'End'})
        other = snapshot(3, 2, layout(3, 2, [((1, 1), (1, 2))]),
                         {(1, 1): 'Heading', (2, 1): 'Added', (3, 1): 'End'}, 'other.docx')
        base.protected = [(1, 3)]
        with patch.object(m, 'word_app') as office, self.assertRaises(m.MergeError):
            m.prepare_structure(base, [other], 'unused')
        office.assert_not_called()


if __name__ == '__main__':
    unittest.main()
