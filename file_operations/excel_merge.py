"""Local content matching and cell-level Excel merge via owned COM sessions."""
from contextlib import contextmanager
from collections import Counter
from dataclasses import dataclass, field
import gc
import hashlib
import math
import os
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET

EXTENSIONS = {'.xlsx', '.xlsm', '.xls', '.xlsb'}
MAX_CELLS = 200000


class MergeError(Exception):
    def __init__(self, key, **params):
        self.key, self.params = key, params
        super().__init__(key)


def is_excel(path):
    return bool(path and os.path.isfile(path) and os.path.splitext(path)[1].lower() in EXTENSIONS
                and not os.path.basename(path).startswith('~$'))


def fingerprint(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class Cell:
    value: object = None
    formula: bool = False
    display_text: object = field(default=None, compare=False)
    result: object = field(default=None, compare=False)

    @property
    def key(self):
        # Excel numbers are equivalent regardless of int/float representation.
        kind = 'formula' if self.formula else ('bool' if isinstance(self.value, bool)
               else 'number' if isinstance(self.value, (int, float)) else type(self.value).__name__)
        return kind, self.value


EMPTY = Cell()


@dataclass
class Sheet:
    cells: dict = field(default_factory=dict)
    rows: int = 1
    cols: int = 1
    hidden_rows: set = field(default_factory=set)
    hidden_cols: set = field(default_factory=set)
    styles: dict = field(default_factory=dict)
    row_heights: dict = field(default_factory=dict)
    col_widths: dict = field(default_factory=dict)
    styles_loaded: bool = False


@dataclass
class Book:
    path: str
    digest: str
    sheets: dict


@dataclass
class Conflict:
    sheet: str
    row: int
    col: int
    values: list
    sources: list
    selected: object = None


def conflicts_for(base, others):
    conflicts = []
    for name, sheet in base.sheets.items():
        related = [book for book in others if name in book.sheets]
        positions = set(sheet.cells)
        for book in related:
            positions.update(book.sheets[name].cells)
        for row, col in sorted(positions):
            if row in sheet.hidden_rows or col in sheet.hidden_cols:
                continue
            original = sheet.cells.get((row, col), EMPTY)
            values, sources = [original], [[os.path.basename(base.path)]]
            for book in related:
                if row in book.sheets[name].hidden_rows or col in book.sheets[name].hidden_cols:
                    continue
                value = book.sheets[name].cells.get((row, col), EMPTY)
                index = next((i for i, item in enumerate(values) if item.key == value.key), None)
                if index is None:
                    values.append(value)
                    sources.append([os.path.basename(book.path)])
                else:
                    sources[index].append(os.path.basename(book.path))
            if len(values) > 1:
                conflicts.append(Conflict(name, row, col, values, sources,
                                          1 if len(values) == 2 else None))
    return conflicts


def similarity(base, other):
    """Content cosine similarity plus same-position agreement; filenames are not evidence."""
    common = set(base.sheets) & set(other.sheets)
    if not common:
        return 0.0
    def tokens(book):
        result = Counter()
        for name in common:
            hidden = base.sheets[name].hidden_rows | other.sheets[name].hidden_rows
            hidden_cols = base.sheets[name].hidden_cols | other.sheets[name].hidden_cols
            for (row, col), cell in book.sheets[name].cells.items():
                if row in hidden or col in hidden_cols:
                    continue
                result.update(re.findall(r'\w+', str(cell.value).casefold()))
        return result
    a, b = tokens(base), tokens(other)
    denom = math.sqrt(sum(v*v for v in a.values()) * sum(v*v for v in b.values()))
    cosine = sum(v*b[k] for k, v in a.items()) / denom if denom else 0
    matches = count = 0
    for name in common:
        left, right = base.sheets[name].cells, other.sheets[name].cells
        for pos in set(left) | set(right):
            if (pos[0] in base.sheets[name].hidden_rows | other.sheets[name].hidden_rows
                    or pos[1] in base.sheets[name].hidden_cols | other.sheets[name].hidden_cols):
                continue
            count += 1
            matches += pos in left and pos in right and left[pos].key == right[pos].key
    return .65*cosine + .35*(matches/count if count else 0)


@contextmanager
def excel_app():
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    app = None
    try:
        app = win32com.client.DispatchEx('Excel.Application')
        app.Visible = False
        app.DisplayAlerts = False
        app.EnableEvents = False
        app.AskToUpdateLinks = False
        app.AutomationSecurity = 3  # Never execute workbook macros.
        yield app
    finally:
        if app is not None:
            try:
                app.Quit()
            except Exception:
                pass
        app = None
        gc.collect()
        pythoncom.CoUninitialize()


def open_book(app, path, readonly=True):
    return app.Workbooks.Open(Filename=os.path.abspath(path), UpdateLinks=0, ReadOnly=readonly,
                              Password='', WriteResPassword='', IgnoreReadOnlyRecommended=True,
                              AddToMru=False, Notify=False)


def style_value(obj, name, default):
    """Excel may return Null or reject an unsupported formatting property."""
    try:
        value = getattr(obj, name)
    except Exception:
        return default
    return default if value is None else value


def style_number(value, default, converter=int):
    try:
        return converter(value)
    except (TypeError, ValueError, OverflowError):
        return default


def excel_rgb(value, default=(0, 0, 0)):
    """Excel OLE RGB colors store the red channel in the low byte."""
    value = style_number(value, -1)
    if value < 0:
        return default
    return value & 255, (value >> 8) & 255, (value >> 16) & 255


def read_cell_style(cell):
    # DisplayFormat includes effective conditional formatting. Fall back per property.
    base_font = style_value(cell, 'Font', None)
    base_interior = style_value(cell, 'Interior', None)
    appearance = style_value(cell, 'DisplayFormat', None)
    font = style_value(appearance, 'Font', base_font)
    interior = style_value(appearance, 'Interior', base_interior)
    def font_value(name, default):
        value = style_value(font, name, None)
        return style_value(base_font, name, default) if value is None else value
    def fill_value(name, default):
        value = style_value(interior, name, None)
        return style_value(base_interior, name, default) if value is None else value
    color = excel_rgb(font_value('Color', 0))
    fill = excel_rgb(fill_value('Color', 0xFFFFFF), (255, 255, 255))
    size = style_number(font_value('Size', 11), 11, float)
    if not math.isfinite(size) or size <= 0:
        size = 11
    return dict(font_name=str(font_value('Name', 'Calibri') or 'Calibri'), font_size=size,
                bold=bool(font_value('Bold', False)), italic=bool(font_value('Italic', False)),
                underline=style_number(font_value('Underline', -4142), -4142) not in (-4142, 0),
                strike=bool(font_value('Strikethrough', False)), foreground=color,
                background=fill if style_number(fill_value('Pattern', -4142), -4142) != -4142 else (255, 255, 255),
                horizontal=style_number(style_value(cell, 'HorizontalAlignment', 1), 1),
                vertical=style_number(style_value(cell, 'VerticalAlignment', -4107), -4107))


def parse_range_styles(xml, top, left, rows, cols, hidden_rows, hidden_cols):
    """Decode one Excel XML Spreadsheet snapshot entirely in Python."""
    ns = '{urn:schemas-microsoft-com:office:spreadsheet}'
    root = ET.fromstring(xml)
    definitions = {node.get(ns + 'ID'): node for node in root.findall('.//' + ns + 'Style')}
    cache = {}
    defaults = dict(font_name='Calibri', font_size=11, bold=False, italic=False,
                    underline=False, strike=False, foreground=(0, 0, 0), background=(255, 255, 255),
                    horizontal=1, vertical=-4107)
    def rgb(text, default):
        try:
            return tuple(int(text.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
        except (AttributeError, ValueError):
            return default
    def resolve(key, visiting=None):
        if key in cache:
            return cache[key]
        visiting = set() if visiting is None else visiting
        if key in visiting:
            return defaults.copy()
        visiting.add(key)
        node = definitions.get(key)
        parent = node.get(ns + 'Parent', 'Default') if node is not None else 'Default'
        result = resolve(parent, visiting).copy() if key != 'Default' else defaults.copy()
        if node is not None:
            font = node.find(ns + 'Font')
            if font is not None:
                for name, field in [('FontName', 'font_name'), ('Size', 'font_size')]:
                    value = font.get(ns + name)
                    if value is not None:
                        result[field] = style_number(value, 11, float) if name == 'Size' else value
                for name, field in [('Bold', 'bold'), ('Italic', 'italic'), ('StrikeThrough', 'strike')]:
                    value = font.get(ns + name)
                    if value is not None:
                        result[field] = value == '1'
                if font.get(ns + 'Underline') is not None:
                    result['underline'] = font.get(ns + 'Underline') != 'None'
                result['foreground'] = rgb(font.get(ns + 'Color'), result['foreground'])
            fill = node.find(ns + 'Interior')
            if fill is not None:
                result['background'] = rgb(fill.get(ns + 'Color'), result['background'])
            align = node.find(ns + 'Alignment')
            if align is not None:
                result['horizontal'] = {'Left': -4131, 'Right': -4152, 'Center': -4108,
                    'CenterAcrossSelection': 7, 'Automatic': 1}.get(align.get(ns + 'Horizontal'), result['horizontal'])
                result['vertical'] = {'Top': -4160, 'Center': -4108, 'Bottom': -4107}.get(align.get(ns + 'Vertical'), result['vertical'])
        cache[key] = result
        visiting.remove(key)
        return result
    table = root.find('.//' + ns + 'Table')
    if table is None:
        raise ValueError('Excel returned no worksheet formatting table')
    column_styles = {}
    col_index = 0
    for column in table.findall(ns + 'Column'):
        col_index = int(column.get(ns + 'Index', col_index + 1))
        span = int(column.get(ns + 'Span', 0))
        for index in range(col_index, col_index + span + 1):
            column_styles[index] = column.get(ns + 'StyleID', 'Default')
        col_index += span
    result = {}
    # Include row/column defaults and styled blank cells without any extra COM calls.
    for r in range(rows):
        row = top + r
        if row not in hidden_rows:
            for c in range(cols):
                col = left + c
                if col not in hidden_cols:
                    result[row, col] = resolve(column_styles.get(c + 1, table.get(ns + 'StyleID', 'Default')))
    row_index = 0
    for row_node in table.findall(ns + 'Row'):
        row_index = int(row_node.get(ns + 'Index', row_index + 1))
        row = top + row_index - 1
        if row in hidden_rows or not top <= row < top + rows:
            continue
        row_style = row_node.get(ns + 'StyleID')
        if row_style:
            for col in range(left, left + cols):
                if col not in hidden_cols:
                    result[row, col] = resolve(row_style)
        col_index = 0
        for cell in row_node.findall(ns + 'Cell'):
            col_index = int(cell.get(ns + 'Index', col_index + 1))
            col = left + col_index - 1
            if col not in hidden_cols and left <= col < left + cols:
                key = cell.get(ns + 'StyleID')
                if key:
                    result[row, col] = resolve(key)
            col_index += int(cell.get(ns + 'MergeAcross', 0))
    return result


def read_range_styles(sheet, top, left, rows, cols, hidden_rows, hidden_cols):
    # Value(11) returns styles for the entire range in one COM transfer.
    import pythoncom
    area = sheet.Range(sheet.Cells(top, left), sheet.Cells(top + rows - 1, left + cols - 1))
    dispid = area._oleobj_.GetIDsOfNames('Value')
    xml = area._oleobj_.Invoke(dispid, 0, pythoncom.DISPATCH_PROPERTYGET, True, 11)
    return parse_range_styles(xml, top, left, rows, cols, hidden_rows, hidden_cols)


def read_sheet_layout(sheet, model):
    used = sheet.UsedRange
    top, left = int(used.Row), int(used.Column)
    rows, cols = int(used.Rows.Count), int(used.Columns.Count)
    styles = read_range_styles(sheet, top, left, rows, cols, model.hidden_rows, model.hidden_cols)
    heights = {r: style_number(sheet.Rows(r).Height, 15, float)
               for r in range(1, model.rows + 1) if r not in model.hidden_rows}
    widths = {c: style_number(sheet.Columns(c).Width, 48, float)
              for c in range(1, model.cols + 1) if c not in model.hidden_cols}
    return styles, heights, widths


def load_sheet_layout(book, name):
    if fingerprint(book.path) != book.digest:
        raise MergeError('merge_changed', path=book.path)
    with excel_app() as app:
        document = open_book(app, book.path)
        try:
            result = read_sheet_layout(document.Worksheets(name), book.sheets[name])
        finally:
            document.Close(False)
    if fingerprint(book.path) != book.digest:
        raise MergeError('merge_changed', path=book.path)
    return result


def read_book(app, path, load_first_style=True):
    digest = fingerprint(path)
    document = open_book(app, path)
    sheet = used = None
    try:
        app.Calculate()
        sheets = {}
        total = 0
        for sheet in document.Worksheets:
            if style_value(sheet, 'Visible', -1) != -1:
                continue
            used = sheet.UsedRange
            rows, cols = int(used.Rows.Count), int(used.Columns.Count)
            total += rows * cols
            if total > MAX_CELLS:
                raise MergeError('merge_too_large', path=os.path.basename(path), count=MAX_CELLS)
            start_row, start_col = int(used.Row), int(used.Column)
            data = used.Formula
            results = used.Value2
            if rows == cols == 1:
                data = ((data,),)
                results = ((results,),)
            # Excel has already applied the saved AutoFilter on opening.
            # Track excluded rows separately: an invisible cell is not a blank.
            hidden_rows = {row for row in range(1, start_row + rows)
                           if sheet.Rows(row).Hidden}
            hidden_cols = {col for col in range(1, start_col + cols)
                           if sheet.Columns(col).Hidden}
            cells = {}
            styles = {}
            for r, line in enumerate(data):
                for c, value in enumerate(line):
                    row, col = start_row+r, start_col+c
                    if value is not None:
                        excel_cell = sheet.Cells(row, col)
                        formula = isinstance(value, str) and value.startswith('=') and bool(excel_cell.HasFormula)
                        result = results[r][c]
                        text = str(excel_cell.Text or '')
                        if text and set(text) == {'#'}:
                            text = '' if result is None else str(result)
                        cells[row, col] = Cell(value, formula, text, result)
                    excel_cell = None
            model = Sheet(cells, start_row+rows-1, start_col+cols-1,
                          hidden_rows, hidden_cols, styles)
            if load_first_style and not sheets:
                model.styles, model.row_heights, model.col_widths = read_sheet_layout(sheet, model)
                model.styles_loaded = True
            sheets[str(sheet.Name)] = model
        if fingerprint(path) != digest:
            raise MergeError('merge_changed', path=path)
        return Book(path, digest, sheets)
    finally:
        sheet = used = None
        document.Close(False)
        document = None


def search_books(path):
    matches, skipped = [], []
    with excel_app() as app:
        base = read_book(app, path, load_first_style=False)
        with os.scandir(os.path.dirname(path)) as entries:
            candidates = sorted((e.path for e in entries if e.is_file() and is_excel(e.path)
                                 and os.path.normcase(os.path.abspath(e.path)) != os.path.normcase(os.path.abspath(path))),
                                key=str.casefold)
        for candidate in candidates:
            try:
                book = read_book(app, candidate, load_first_style=False)
                score = similarity(base, book)
                if score >= .45:
                    matches.append((book, score))
            except Exception as exc:
                skipped.append((candidate, exc))
    return base, sorted(matches, key=lambda item: (-item[1], item[0].path.casefold())), skipped


def save_merge(base, conflicts):
    if any(c.selected is None for c in conflicts):
        raise MergeError('merge_unresolved')
    if fingerprint(base.path) != base.digest:
        raise MergeError('merge_changed', path=base.path)
    changes = [c for c in conflicts if c.selected != 0]
    if not changes:
        return
    # Edit a sibling copy; replace the original only after a successful Excel save.
    fd, temporary = tempfile.mkstemp(prefix='~$DocExplorer_merge_', suffix=os.path.splitext(base.path)[1],
                                     dir=os.path.dirname(base.path))
    os.close(fd)
    try:
        shutil.copy2(base.path, temporary)
        with excel_app() as app:
            document = open_book(app, temporary, readonly=False)
            cell = sheet = None
            try:
                if document.ReadOnly:
                    raise MergeError('merge_readonly')
                for conflict in changes:
                    sheet = document.Worksheets(conflict.sheet)
                    cell = sheet.Cells(conflict.row, conflict.col)
                    if sheet.ProtectContents or cell.HasArray:
                        raise MergeError('merge_protected', sheet=conflict.sheet)
                    if cell.MergeCells:
                        area = cell.MergeArea
                        if int(area.Row) != conflict.row or int(area.Column) != conflict.col:
                            raise MergeError('merge_protected', sheet=conflict.sheet)
                    value = conflict.values[conflict.selected]
                    if value.formula:
                        # Do not introduce implicit external links from another workbook.
                        if re.search(r'\[[^\]]+\][^!]*!', str(value.value)):
                            raise MergeError('merge_external_formula', sheet=conflict.sheet)
                        cell.Formula = value.value
                    elif isinstance(value.value, str) and value.value.startswith(('=', '+', '-', '@')):
                        cell.Value2 = "'" + value.value
                    else:
                        cell.Value2 = value.value
                document.Save()
            finally:
                cell = sheet = None
                document.Close(False)
                document = None
        if fingerprint(base.path) != base.digest:
            raise MergeError('merge_changed', path=base.path)
        # Retain the exact source bytes as a recovery copy.
        backup = base.path + '.merge-backup'
        n = 1
        while os.path.exists(backup):
            backup = base.path + '.merge-backup.' + str(n)
            n += 1
        shutil.copy2(base.path, backup)
        os.replace(temporary, base.path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def render_preview(path, folder):
    """Use Excel's HTML exporter, as in the app's Office preview pane."""
    os.makedirs(folder, exist_ok=True)
    output = os.path.join(folder, 'document.html')
    with excel_app() as app:
        document = open_book(app, path)
        try:
            document.SaveAs(Filename=output, FileFormat=44, ReadOnlyRecommended=False,
                            CreateBackup=False, AddToMru=False)
        finally:
            document.Close(False)
            document = None
    return output
