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
            original = sheet.cells.get((row, col), EMPTY)
            values, sources = [original], [[os.path.basename(base.path)]]
            for book in related:
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
            for cell in book.sheets[name].cells.values():
                result.update(re.findall(r'\w+', str(cell.value).casefold()))
        return result
    a, b = tokens(base), tokens(other)
    denom = math.sqrt(sum(v*v for v in a.values()) * sum(v*v for v in b.values()))
    cosine = sum(v*b[k] for k, v in a.items()) / denom if denom else 0
    matches = count = 0
    for name in common:
        left, right = base.sheets[name].cells, other.sheets[name].cells
        for pos in set(left) | set(right):
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


def read_book(app, path):
    digest = fingerprint(path)
    document = open_book(app, path)
    sheet = used = None
    try:
        sheets = {}
        total = 0
        for sheet in document.Worksheets:
            used = sheet.UsedRange
            rows, cols = int(used.Rows.Count), int(used.Columns.Count)
            total += rows * cols
            if total > MAX_CELLS:
                raise MergeError('merge_too_large', path=os.path.basename(path), count=MAX_CELLS)
            start_row, start_col = int(used.Row), int(used.Column)
            data = used.Formula
            if rows == cols == 1:
                data = ((data,),)
            cells = {}
            for r, line in enumerate(data):
                for c, value in enumerate(line):
                    if value is None:
                        continue
                    row, col = start_row+r, start_col+c
                    formula = isinstance(value, str) and value.startswith('=') and bool(sheet.Cells(row, col).HasFormula)
                    cells[row, col] = Cell(value, formula)
            sheets[str(sheet.Name)] = Sheet(cells, start_row+rows-1, start_col+cols-1)
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
        base = read_book(app, path)
        with os.scandir(os.path.dirname(path)) as entries:
            candidates = sorted((e.path for e in entries if e.is_file() and is_excel(e.path)
                                 and os.path.normcase(os.path.abspath(e.path)) != os.path.normcase(os.path.abspath(path))),
                                key=str.casefold)
        for candidate in candidates:
            try:
                book = read_book(app, candidate)
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
