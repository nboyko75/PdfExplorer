"""Word table geometry and insertion, independent of Word's uniform-table COM API.

Keep the complete WordOpenXML package so relationships, styles and namespace
declarations survive Range.InsertXML, including in legacy .doc documents.
"""
from xml.dom import minidom


W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


def children(node, name):
    return [item for item in node.childNodes
            if item.namespaceURI == W and item.localName == name]


def child(node, name):
    return next(iter(children(node, name)), None)


def value(node, default='0'):
    return (node.getAttributeNS(W, 'val') or default) if node is not None else default


def element(node, name):
    return node.ownerDocument.createElementNS(W, 'w:' + name)


def property_value(node, name, val):
    prop = child(node, name)
    if prop is None:
        prop = element(node, name)
        node.appendChild(prop)
    prop.setAttributeNS(W, 'w:val', str(val))
    return prop


def table_xml(xml):
    package = minidom.parseString(xml)
    bodies = package.getElementsByTagNameNS(W, 'body')
    tables = children(bodies[0], 'tbl') if bodies else []
    if len(tables) != 1 or len(tables[0].getElementsByTagNameNS(W, 'tbl')):
        raise ValueError('Expected one table without nested tables')
    return package, tables[0]


def geometry(table):
    """Return anchor spans and physical XML cells (including continuations)."""
    grid = child(table, 'tblGrid')
    cols = len(children(grid, 'gridCol')) if grid is not None else 0
    spans, physical, active = {}, {}, {}
    rows = children(table, 'tr')
    for row, tr in enumerate(rows, 1):
        trpr = child(tr, 'trPr')
        before = int(value(child(trpr, 'gridBefore'))) if trpr is not None else 0
        col, following = before + 1, {}
        for tc in children(tr, 'tc'):
            props = child(tc, 'tcPr')
            width = int(value(child(props, 'gridSpan'), '1')) if props is not None else 1
            merge = child(props, 'vMerge') if props is not None else None
            if width < 1 or (props is not None and child(props, 'hMerge') is not None):
                raise ValueError('Unsupported cell geometry')
            physical[row, col] = tc
            if merge is not None and value(merge, 'continue') == 'continue':
                anchor = active.get((col, width))
                if anchor is None:
                    raise ValueError('Vertical merge without an anchor')
                height, _ = spans[anchor]
                spans[anchor] = height + 1, width
            else:
                anchor = row, col
                spans[anchor] = 1, width
            if merge is not None:
                following[col, width] = anchor
            col += width
        after = int(value(child(trpr, 'gridAfter'))) if trpr is not None else 0
        cols = max(cols, col - 1 + after)
        active = following
    if not rows or not cols or not spans:
        raise ValueError('Empty table')
    return len(rows), cols, spans, physical


def read_layout(xml):
    package, table = table_xml(xml)
    try:
        rows, cols, spans, _ = geometry(table)
        return rows, cols, spans
    finally:
        package.unlink()


def mapped_spans(spans, row_map, col_map):
    return {(row_map[r], col_map[c]):
            (row_map[r + h - 1] - row_map[r] + 1,
             col_map[c + w - 1] - col_map[c] + 1)
            for (r, c), (h, w) in spans.items()}


def coverage(pos, span):
    r, c = pos
    h, w = span
    return {(i, j) for i in range(r, r + h) for j in range(c, c + w)}


def union_spans(layouts, rows, cols):
    """Preserve original merges; use source merges only in newly added space."""
    result, occupied = {}, set()
    for layout in layouts:
        for pos, span in layout.items():
            area = coverage(pos, span)
            if not area & occupied:
                result[pos] = span
                occupied.update(area)
    for r in range(1, rows + 1):
        for c in range(1, cols + 1):
            if (r, c) not in occupied:
                result[r, c] = 1, 1
    return result


def blank_cell(template):
    """Copy formatting only; never duplicate fields, images or identifiers."""
    tc = element(template, 'tc')
    props = child(template, 'tcPr')
    if props is not None:
        tc.appendChild(props.cloneNode(True))
    paragraph = element(template, 'p')
    paragraphs = children(template, 'p')
    ppr = child(paragraphs[0], 'pPr') if paragraphs else None
    if ppr is not None:
        paragraph.appendChild(ppr.cloneNode(True))
    tc.appendChild(paragraph)
    return tc


def resize_table(xml, row_map, col_map, rows, cols, spans):
    """Expand a table in a Flat OPC package without flattening merged cells."""
    package, table = table_xml(xml)
    try:
        # Word exports a trailing paragraph and section settings for a table
        # range. They are context, not part of the table being replaced.
        for item in list(table.parentNode.childNodes):
            if item is not table:
                table.parentNode.removeChild(item)
        old_rows, old_cols, old_spans, physical = geometry(table)
        original_rows = children(table, 'tr')
        grid = child(table, 'tblGrid')
        grid_cols = children(grid, 'gridCol')
        widths = [int(item.getAttributeNS(W, 'w') or '1') for item in grid_cols]
        if len(widths) != old_cols:
            raise ValueError('Incomplete table grid')
        inverse_rows = {v: k for k, v in row_map.items()}
        inverse_cols = {v: k for k, v in col_map.items()}
        new_widths = [widths[inverse_cols.get(c, min(old_cols, c)) - 1]
                      for c in range(1, cols + 1)]
        scale = sum(widths) / max(1, sum(new_widths))
        new_widths = [max(1, round(width * scale)) for width in new_widths]
        for item in list(grid.childNodes):
            grid.removeChild(item)
        for width in new_widths:
            item = element(table, 'gridCol')
            item.setAttributeNS(W, 'w:w', str(width))
            grid.appendChild(item)

        # A continuation has its own borders/shading. Retain those where possible.
        retained = {(row_map[r], col_map[c]): tc for (r, c), tc in physical.items()}
        originals = {(row_map[r], col_map[c]): physical[r, c] for r, c in old_spans}
        row_cells = {r: [] for r in range(1, rows + 1)}
        for (r, c), (height, width) in sorted(spans.items()):
            template = originals.get((r, c))
            if template is None:
                template = physical[min(physical, key=lambda p:
                    abs(row_map[p[0]] - r) + abs(col_map[p[1]] - c))]
            for rr in range(r, r + height):
                original = retained.get((rr, c))
                tc = (original.cloneNode(True) if original is not None
                      else blank_cell(template))
                props = child(tc, 'tcPr')
                if props is None:
                    props = element(tc, 'tcPr')
                    tc.insertBefore(props, tc.firstChild)
                for name in ('gridSpan', 'vMerge', 'hMerge'):
                    for prop in children(props, name):
                        props.removeChild(prop)
                tcw = child(props, 'tcW')
                if tcw is None:
                    tcw = element(tc, 'tcW')
                    props.insertBefore(tcw, props.firstChild)
                tcw.setAttributeNS(W, 'w:type', 'dxa')
                tcw.setAttributeNS(W, 'w:w', str(sum(new_widths[c-1:c+width-1])))
                if width > 1:
                    property_value(props, 'gridSpan', width)
                if height > 1:
                    property_value(props, 'vMerge', 'restart' if rr == r else 'continue')
                row_cells[rr].append((c, tc))

        for tr in original_rows:
            table.removeChild(tr)
        for r in range(1, rows + 1):
            source_row = inverse_rows.get(r, min(old_rows, r))
            source = original_rows[source_row - 1]
            tr = source.cloneNode(True) if r in inverse_rows else element(table, 'tr')
            if r not in inverse_rows and child(source, 'trPr') is not None:
                tr.appendChild(child(source, 'trPr').cloneNode(True))
            for tc in children(tr, 'tc'):
                tr.removeChild(tc)
            props = child(tr, 'trPr')
            if props is not None:
                for name in ('gridBefore', 'gridAfter', 'wBefore', 'wAfter') + (() if r in inverse_rows else ('tblHeader',)):
                    for prop in children(props, name):
                        props.removeChild(prop)
            for _, tc in sorted(row_cells[r]):
                tr.appendChild(tc)
            table.appendChild(tr)
        return package.toxml()
    finally:
        package.unlink()
