"""Text-level Word merge, with an Office-rendered, in-place HTML review.

COM objects never leave the worker thread. Only plain snapshots and conflicts
are passed to the UI. Table additions preserve the original merged-cell layout.
"""
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from bisect import bisect_left
from difflib import SequenceMatcher
from html import escape
import gc
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid

from file_operations.excel_merge import (MergeError, fingerprint, is_merge_backup,
                                        merge_backup_path, source_key)
from file_operations.office_session import save_word_html
from file_operations.merge_structure import align_grids, added_axes
from file_operations.word_table_structure import read_layout, mapped_spans, union_spans, resize_table

EXTENSIONS = {'.doc', '.docx', '.docm'}
MAX_CHARACTERS = 500000
CONTROL = re.compile(r'[\x00-\x08\x0c-\x1f]')
TOKEN = re.compile(r'\w+|[^\w\s]|[^\S\r]+|\r', re.UNICODE)

# WdColorIndex values supported by Word's Text Highlight Color command.
HIGHLIGHT_COLORS = {
    1: (0, 0, 0), 2: (0, 0, 255), 3: (0, 255, 255),
    4: (0, 255, 0), 5: (255, 0, 255), 6: (255, 0, 0),
    7: (255, 255, 0), 8: (255, 255, 255), 9: (0, 0, 128),
    10: (0, 128, 128), 11: (0, 128, 0), 12: (128, 0, 128),
    13: (128, 0, 0), 14: (128, 128, 0), 15: (128, 128, 128),
    16: (192, 192, 192),
}


def highlight_color_index(color):
    """Map the RGB picker to Word's fixed native highlight palette."""
    return min(HIGHLIGHT_COLORS, key=lambda index: sum(
        (a - b) ** 2 for a, b in zip(color, HIGHLIGHT_COLORS[index])))


def is_word(path):
    return bool(path and os.path.isfile(path) and
                os.path.splitext(path)[1].lower() in EXTENSIONS and
                not os.path.basename(path).startswith('~$'))


@dataclass
class Document:
    path: str
    digest: str
    text: str
    protected: list = field(default_factory=list)
    tables: list = field(default_factory=list)
    original: object = None


@dataclass
class Table:
    start: int
    end: int
    rows: int
    cols: int
    cells: dict  # (row, column) -> Python text offsets, excluding cell markers
    spans: dict = field(default_factory=dict)  # anchor -> (row span, column span)

    def layout(self):
        return {pos: self.spans.get(pos, (1, 1)) for pos in self.cells}


@dataclass
class Conflict:
    start: int  # Python string offsets in the original main story
    end: int
    values: list
    sources: list
    selected: object = None


@contextmanager
def word_app():
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    app = None
    update_links = None
    try:
        app = win32com.client.DispatchEx('Word.Application')
        app.Visible = False
        app.DisplayAlerts = 0
        app.ScreenUpdating = False
        app.AutomationSecurity = 3
        update_links = app.Options.UpdateLinksAtOpen
        app.Options.UpdateLinksAtOpen = False
        yield app
    finally:
        if app is not None:
            if update_links is not None:
                try:
                    app.Options.UpdateLinksAtOpen = update_links
                except Exception:
                    pass
            try:
                app.Quit(0)
            except Exception:
                pass
        app = None
        gc.collect()
        pythoncom.CoUninitialize()


def open_document(app, path, readonly=True):
    return app.Documents.Open(
        FileName=os.path.abspath(path), ConfirmConversions=False,
        ReadOnly=readonly, AddToRecentFiles=False, Visible=False,
        PasswordDocument='', WritePasswordDocument='', OpenAndRepair=False,
        NoEncodingDialog=True)


def word_offset(text, offset):
    """UTF-16 positions; each exported CR+cell marker is one Word character."""
    prefix = text[:offset].replace('\r\x07', '\x07')
    return len(prefix.encode('utf-16-le', errors='surrogatepass')) // 2


def story_snapshot(document):
    """Mask protected ranges without losing Word's character positions.

    Range.Text omits field codes even though Range.Start/End count them. Read
    the ordinary text between fields and reserve their full UTF-16 lengths.
    This also prevents comparisons from offering field/control contents.
    """
    protected = [(int(item.Code.Start) - 1, int(item.Result.End) + 1)
                 for item in document.Fields]
    for item in document.ContentControls:
        area = item.Range
        if area.StoryType == 1:
            protected.append((int(area.Start), int(area.End)))
    merged = []
    for start, end in sorted(protected):
        if merged and start <= merged[-1][1]:
            merged[-1] = merged[-1][0], max(end, merged[-1][1])
        else:
            merged.append((start, end))
    pieces, cursor = [], 0
    story_end = int(document.Content.End)
    if story_end > MAX_CHARACTERS:
        raise MergeError('word_merge_too_large', path=str(document.Name), count=MAX_CHARACTERS)
    for start, end in merged + [(story_end, story_end)]:
        area = document.Range(cursor, start)
        area.TextRetrievalMode.IncludeHiddenText = True
        text = str(area.Text or '')
        if word_offset(text, len(text)) != start - cursor:
            raise MergeError('word_merge_protected')
        pieces.extend((text, '\x00' * (end - start)))
        cursor = end
    return ''.join(pieces), merged


def read_document(app, path):
    digest = fingerprint(path)
    document = open_document(app, path)
    try:
        if document.ProtectionType != -1 or document.Revisions.Count:
            raise MergeError('word_merge_protected')
        text, protected = story_snapshot(document)
        tables = table_snapshot(document, text)
    finally:
        document.Close(False)
        document = None
    if fingerprint(path) != digest:
        raise MergeError('merge_changed', path=path)
    return Document(path, digest, text, protected, tables)


def table_snapshot(document, text):
    positions, offset = [], 0
    for index, char in enumerate(text):
        positions.append(offset)
        if char == '\r' and text[index:index+2] == '\r\x07':
            continue
        offset += 2 if ord(char) > 0xffff else 1
    positions.append(offset)
    def python_offset(value):
        return bisect_left(positions, int(value))
    tables = []
    for table in document.Tables:
        start, end = python_offset(table.Range.Start), python_offset(table.Range.End)
        cells, spans, rows, cols = {}, {}, 0, 0
        try:
            # COM Rows/Columns and ColumnIndex are unreliable for merged tables.
            # XML provides grid positions; COM provides exact story offsets.
            rows, cols, spans = read_layout(table.Range.WordOpenXML)
            word_cells = list(table.Range.Cells)
            if len(word_cells) != len(spans):
                raise ValueError('Cell layout does not match Word ranges')
            for pos, cell in zip(sorted(spans), word_cells):
                if cell.Tables.Count > 1:
                    raise ValueError('Nested table')
                cells[pos] = (
                    python_offset(cell.Range.Start), python_offset(cell.Range.End - 1))
        except Exception:
            cells = {}  # Existing text merging still works for irregular tables.
            spans = {}
        tables.append(Table(start, end, rows, cols, cells, spans))
    return tables


def replace_table_xml(document, index, xml):
    table = document.Tables(index + 1)
    start = int(table.Range.Start)
    following = str(document.Range(int(table.Range.End), int(document.Content.End)).Text or '')
    # InsertXML on a table range nests the new table inside its first cell.
    # Replace at the collapsed story range, in the temporary document only.
    table.Delete()
    document.Range(start, start).InsertXML(xml)
    end = int(document.Tables(index + 1).Range.End)
    suffix = str(document.Range(end, int(document.Content.End)).Text or '')
    # Word appends an empty paragraph when importing a standalone table.
    # Remove only that verified addition, preserving existing blank paragraphs.
    if suffix == '\r' + following:
        document.Range(end, end + 1).Delete()
    elif suffix != following:
        raise MergeError('word_merge_verify_failed')


def prepare_structure(base, others, folder):
    aligned = [replace(other, tables=list(other.tables)) for other in others]
    plans = {}
    for index, table in enumerate(base.tables):
        # An irregular table must not prevent additions to other tables or
        # ordinary text merging. Such tables use the text comparison below.
        if not table.cells:
            continue
        related = [(number, other) for number, other in enumerate(others)
                   if len(other.tables) == len(base.tables) and other.tables[index].cells]
        models = [base] + [other for _, other in related]
        tables = [model.tables[index] for model in models]
        grids = [{pos: model.text[start:end] for pos, (start, end) in item.cells.items()
                  if model.text[start:end]} for model, item in zip(models, tables)]
        axes = [(list(range(1, item.rows + 1)), list(range(1, item.cols + 1))) for item in tables]
        maps, (rows, cols) = align_grids(grids, axes)
        layouts = [mapped_spans(item.layout(), rm, cm)
                   for item, (rm, cm) in zip(tables, maps)]
        added_rows, added_cols = added_axes(maps[0][0], rows), added_axes(maps[0][1], cols)
        if added_rows or added_cols:
            if touches_protected(base, table.start, table.end):
                raise MergeError('word_merge_protected')
            merged = any(span != (1, 1) for layout in layouts for span in layout.values())
            shape = union_spans(layouts, rows, cols) if merged else None
            plans[index] = added_rows, added_cols, maps[0], (rows, cols), shape
        for (number, _), item, (rm, cm), layout in zip(related, tables[1:], maps[1:], layouts[1:]):
            aligned[number].tables[index] = replace(item, rows=rows, cols=cols,
                cells={(rm[r], cm[c]): span for (r, c), span in item.cells.items()}, spans=layout)
    if not plans:
        return base, aligned
    os.makedirs(folder, exist_ok=True)
    fd, path = tempfile.mkstemp(prefix='structure_', suffix=os.path.splitext(base.path)[1], dir=folder)
    os.close(fd)
    try:
        if fingerprint(base.path) != base.digest:
            raise MergeError('merge_changed', path=base.path)
        shutil.copy2(base.path, path)
        with word_app() as app:
            document = open_document(app, path, readonly=False)
            try:
                document.TrackRevisions = False
                for index, (rows, cols, (rm, cm), (height, width), shape) in plans.items():
                    table = document.Tables(index + 1)
                    if shape is not None:
                        xml = resize_table(table.Range.WordOpenXML, rm, cm, height, width, shape)
                        replace_table_xml(document, index, xml)
                        continue
                    for row in rows:
                        if row <= table.Rows.Count:
                            table.Rows.Add(BeforeRow=table.Rows(row))
                        else:
                            table.Rows.Add()
                    for col in cols:
                        if col <= table.Columns.Count:
                            table.Columns.Add(BeforeColumn=table.Columns(col))
                        else:
                            table.Columns.Add()
                document.Save()
            finally:
                table = None
                document.Close(False)
                document = None
            prepared = read_document(app, path)
        # Word can normalize XML on import. Never offer a review with a layout
        # different from the plan or with missing original cell contents.
        if len(prepared.tables) != len(base.tables):
            raise MergeError('word_merge_verify_failed')
        a_cursor = b_cursor = 0
        for index, (original, actual) in enumerate(zip(base.tables, prepared.tables)):
            if (base.text[a_cursor:original.start] != prepared.text[b_cursor:actual.start]
                    or index not in plans and base.text[original.start:original.end] != prepared.text[actual.start:actual.end]):
                raise MergeError('word_merge_verify_failed')
            a_cursor, b_cursor = original.end, actual.end
        if base.text[a_cursor:] != prepared.text[b_cursor:]:
            raise MergeError('word_merge_verify_failed')
        for index, (_, _, (rm, cm), (rows, cols), shape) in plans.items():
            original, actual = base.tables[index], prepared.tables[index]
            if shape is not None and (actual.rows != rows or actual.cols != cols or actual.layout() != shape):
                raise MergeError('word_merge_verify_failed')
            for (r, c), (start, end) in original.cells.items():
                span = actual.cells.get((rm[r], cm[c]))
                if span is None or prepared.text[span[0]:span[1]] != base.text[start:end]:
                    raise MergeError('word_merge_verify_failed')
        prepared.original = base
        return prepared, aligned
    except Exception:
        os.remove(path)
        raise


def similarity(base, other):
    a = Counter(re.findall(r'\w+', base.text.casefold()))
    b = Counter(re.findall(r'\w+', other.text.casefold()))
    denom = math.sqrt(sum(v*v for v in a.values()) * sum(v*v for v in b.values()))
    return sum(v*b[k] for k, v in a.items()) / denom if denom else 0.0


def search_documents(path, base=None, cache=None, progress=None):
    matches, skipped = [], []
    cache = {} if cache is None else cache
    with word_app() as app:
        if base is None or fingerprint(path) != base.digest:
            base = read_document(app, path)
        with os.scandir(os.path.dirname(path)) as entries:
            candidates = sorted((e.path for e in entries if e.is_file() and is_word(e.path)
                                 and not is_merge_backup(e.path)
                                 and source_key(e.path) != source_key(path)), key=str.casefold)
        for index, candidate in enumerate(candidates):
            if progress:
                progress(index, len(candidates), os.path.basename(candidate))
            try:
                other = cache.get(candidate)
                if other is None or fingerprint(candidate) != other.digest:
                    other = read_document(app, candidate)
                    cache[candidate] = other
                score = similarity(base, other)
                if score >= .45:
                    matches.append((other, score))
            except Exception as exc:
                skipped.append((candidate, exc))
        if progress:
            progress(len(candidates), len(candidates), '')
        app = None
    return base, sorted(matches, key=lambda item: (-item[1], item[0].path.casefold())), skipped


def paragraphs(text):
    # Include cell/end-of-row markers in their paragraphs, not in the next one.
    return list(re.finditer(r'[^\r]*\r\x07?|[^\r]+$', text))


def touches_protected(document, start, end):
    start, end = word_offset(document.text, start), word_offset(document.text, end)
    return any(start < b and end > a or start == end and a <= start <= b
               for a, b in document.protected)


def edits_for(base, other, add_structure=False):
    """Align paragraphs first so insertions do not shift subsequent choices."""
    left, right = paragraphs(base.text), paragraphs(other.text)
    edits, skipped = [], 0
    matcher = SequenceMatcher(None, [p.group() for p in left],
                              [p.group() for p in right], autojunk=len(right) > 2000)
    for tag, i, j, k, l in matcher.get_opcodes():
        if tag == 'equal':
            continue
        if add_structure and tag == 'insert':
            start = left[i].start() if i < len(left) else len(base.text)
            value = ''.join(p.group() for p in right[k:l])
            if not CONTROL.search(value) and not touches_protected(base, start, start):
                edits.append((start, start, value))
                continue
        if tag != 'replace' or j - i != l - k:
            skipped += 1
            continue
        for original, candidate in zip(left[i:j], right[k:l]):
            a, b = original.group(), candidate.group()
            # A table cell must never be matched to an ordinary paragraph.
            if CONTROL.findall(a) != CONTROL.findall(b):
                skipped += 1
                continue
            aa, bb = list(TOKEN.finditer(a)), list(TOKEN.finditer(b))
            words = SequenceMatcher(None, [t.group() for t in aa],
                                    [t.group() for t in bb], autojunk=len(bb) > 2000)
            for action, x, y, u, v in words.get_opcodes():
                if action == 'equal':
                    continue
                start = aa[x].start() if x < len(aa) else len(a)
                end = aa[y-1].end() if y > x else start
                new_start = bb[u].start() if u < len(bb) else len(b)
                new_end = bb[v-1].end() if v > u else new_start
                value = b[new_start:new_end]
                absolute = original.start() + start, original.start() + end
                if (CONTROL.search(a[start:end] + value) or
                        touches_protected(base, *absolute) or
                        touches_protected(other, candidate.start() + new_start,
                                          candidate.start() + new_end)):
                    skipped += 1
                    continue
                edits.append((*absolute, value))
    return edits, skipped


def structured_edits_for(base, other):
    """Compare aligned cells independently, so added cells cannot shift choices."""
    if len(base.tables) != len(other.tables):
        # Without matching table boundaries, use paragraph/cell-marker anchors.
        # This reports unsupported table additions instead of dropping content.
        return edits_for(base, other, add_structure=True)
    edits, skipped = [], 0
    a_cursor = b_cursor = 0
    for left, right in zip(base.tables + [None], other.tables + [None]):
        a_end = left.start if left else len(base.text)
        b_end = right.start if right else len(other.text)
        # Keep protected offsets relative to the non-table segment.
        def segment(model, start, end):
            offset = word_offset(model.text, start)
            protected = [(a-offset, b-offset) for a, b in model.protected]
            return Document(model.path, model.digest, model.text[start:end], protected)
        changes, count = edits_for(segment(base, a_cursor, a_end),
                                   segment(other, b_cursor, b_end), add_structure=True)
        edits.extend((a+a_cursor, b+a_cursor, value) for a, b, value in changes)
        skipped += count
        if left is None:
            break
        if not left.cells or not right.cells:
            changes, count = edits_for(segment(base, left.start, left.end),
                                       segment(other, right.start, right.end))
            edits.extend((a+left.start, b+left.start, value) for a, b, value in changes)
            skipped += count
            a_cursor, b_cursor = left.end, right.end
            continue
        for pos, (start, end) in left.cells.items():
            if pos not in right.cells:
                continue  # A missing source row/column never deletes the original.
            if left.spans.get(pos, (1, 1)) != right.spans.get(pos, (1, 1)):
                skipped += 1
                continue
            other_start, other_end = right.cells[pos]
            value = other.text[other_start:other_end]
            if value == base.text[start:end]:
                continue
            if (CONTROL.search(value + base.text[start:end])
                    or touches_protected(base, start, end)
                    or touches_protected(other, other_start, other_end)):
                skipped += 1
            else:
                edits.append((start, end, value))
        skipped += sum(pos not in left.cells for pos in right.cells)
        a_cursor, b_cursor = left.end, right.end
    return edits, skipped


def conflicts_for(base, others, add_structure=False):
    proposals, skipped = [], []
    for other in others:
        edits, count = (structured_edits_for(base, other) if add_structure
                        else edits_for(base, other))
        proposals.extend((start, end, value, source_key(other.path))
                         for start, end, value in edits)
        if count:
            skipped.append((other.path, count))
    # Overlapping edits from different sources form one choice, never two
    # independent replacements that could overwrite each other when saved.
    groups = []
    for edit in sorted(proposals):
        if groups and edit[0] <= max(e[1] for e in groups[-1]):
            groups[-1].append(edit)
        else:
            groups.append([edit])
    conflicts = []
    for group in groups:
        start, end = min(e[0] for e in group), max(e[1] for e in group)
        original = base.text[start:end]
        values, sources = [original], [[source_key((base.original or base).path)]]
        for other in others:
            source = source_key(other.path)
            value = original
            for a, b, replacement, _ in sorted((e for e in group if e[3] == source), reverse=True):
                value = value[:a-start] + replacement + value[b-start:]
            if value not in values:
                values.append(value)
                sources.append([])
            sources[values.index(value)].append(source)
        conflicts.append(Conflict(start, end, values, sources,
                                  1 if len(values) == 2 else None))
    return conflicts, skipped


def checked_range(document, base, conflict):
    area = document.Range(word_offset(base.text, conflict.start),
                          word_offset(base.text, conflict.end))
    if str(area.Text or '') != base.text[conflict.start:conflict.end]:
        raise MergeError('merge_changed', path=base.path)
    return area


def review_html(html, markers, conflicts, colors, labels, token):
    """Replace export-only markers; values and filenames are always escaped."""
    for index, (marker, conflict) in enumerate(zip(markers, conflicts)):
        options = ['<option value="" disabled%s>%s</option>' % (
            ' selected' if conflict.selected is None else '', escape(labels['choose']))]
        for choice, value in enumerate(conflict.values):
            source = conflict.sources[choice][0]
            color = '#%02x%02x%02x' % colors.get(source, (0, 0, 0))
            label = value or labels['empty']
            provenance = ', '.join(os.path.basename(p) for p in conflict.sources[choice])
            options.append('<option value="%s" data-label="%s" style="color:%s"%s>%s</option>' % (
                choice, escape(label, quote=True), color, ' selected' if conflict.selected == choice else '',
                escape(label + ' [' + provenance + ']')))
        select = ('<select class="word-merge-choice" data-conflict="%s" aria-label="%s">%s</select>'
                  % (index, escape(labels['choose'], quote=True), ''.join(options)))
        if html.count(marker) != 1:
            raise MergeError('word_merge_preview_failed')
        html = html.replace(marker, select)
    style = '<style>.word-merge-choice {font:inherit;box-sizing:border-box;max-width:100%;background:#fff7ce;border:1px solid #b18a25;border-radius:3px;padding:1px 3px;}</style>'
    script = '''<script>
document.querySelectorAll('.word-merge-choice').forEach(function(select) {
    function update() {
        var selected = select.options[select.selectedIndex];
        select.style.color = selected.style.color;
        select.title = selected.text;
        // Let the native control measure values, including its arrow and padding.
        var measure = select.cloneNode(true);
        measure.removeAttribute('aria-label');
        measure.style.cssText = 'position:absolute;visibility:hidden;width:auto;max-width:none;';
        Array.from(measure.options).forEach(function(option) {
            if (option.disabled && select.value !== '') {
                option.remove();
            } else if (option.dataset.label !== undefined) {
                option.text = option.dataset.label;
            }
        });
        select.parentNode.appendChild(measure);
        select.style.width = Math.ceil(measure.getBoundingClientRect().width) + 'px';
        measure.remove();
    }
    update();
    if (document.fonts) document.fonts.ready.then(update);
    select.addEventListener('change', function() {
        update();
        window.wordMerge.postMessage(JSON.stringify({token:TOKEN,
            conflict:Number(select.dataset.conflict), choice:Number(select.value)}));
    });
});
</script>'''.replace('TOKEN', json.dumps(token))
    return html + style + script


def render_preview(base, folder, conflicts=(), colors=None, labels=None, token=''):
    if fingerprint(base.path) != base.digest:
        raise MergeError('merge_changed', path=base.path)
    os.makedirs(folder, exist_ok=True)
    output = os.path.join(folder, 'document.html')
    markers = ['DXMERGE' + uuid.uuid4().hex + 'END' for _ in conflicts]
    with word_app() as app:
        document = open_document(app, base.path)
        try:
            document.TrackRevisions = False
            for conflict, marker in reversed(list(zip(conflicts, markers))):
                checked_range(document, base, conflict).Text = marker
            document.WebOptions.Encoding = 65001
            save_word_html(document, output)
        finally:
            document.Close(False)
            document = None
        app = None
    if fingerprint(base.path) != base.digest:
        raise MergeError('merge_changed', path=base.path)
    if conflicts:
        html = Path(output).read_text(encoding='utf-8-sig')
        Path(output).write_text(review_html(html, markers, conflicts, colors or {}, labels, token),
                                encoding='utf-8')
    return output


def save_merge(base, conflicts, backup_original=True, change_color=None):
    if any(type(c.selected) is not int or not 0 <= c.selected < len(c.values) for c in conflicts):
        raise MergeError('merge_unresolved')
    if fingerprint(base.path) != base.digest:
        raise MergeError('merge_changed', path=base.path)
    target = base.original or base
    if fingerprint(target.path) != target.digest:
        raise MergeError('merge_changed', path=target.path)
    changes = sorted((c for c in conflicts if c.selected != 0), key=lambda c: c.start)
    if not changes and base.original is None:
        return
    for index, conflict in enumerate(changes):
        if (not 0 <= conflict.start <= conflict.end <= len(base.text) or
                conflict.values[0] != base.text[conflict.start:conflict.end] or
                CONTROL.search(conflict.values[0] + conflict.values[conflict.selected]) or
                touches_protected(base, conflict.start, conflict.end) or
                index and changes[index-1].end > conflict.start):
            raise MergeError('word_merge_protected')
    expected = base.text
    for conflict in reversed(changes):
        expected = expected[:conflict.start] + conflict.values[conflict.selected] + expected[conflict.end:]
    fd, temporary = tempfile.mkstemp(prefix='DocExplorer_merge_',
                                     suffix=os.path.splitext(base.path)[1], dir=os.path.dirname(target.path))
    os.close(fd)
    try:
        shutil.copy2(base.path, temporary)
        with word_app() as app:
            document = open_document(app, temporary, readonly=False)
            try:
                if document.ReadOnly or document.ProtectionType != -1 or document.Revisions.Count:
                    raise MergeError('word_merge_protected')
                track = document.TrackRevisions
                document.TrackRevisions = False
                for conflict in reversed(changes):
                    replacement = conflict.values[conflict.selected]
                    checked_range(document, base, conflict).Text = replacement
                    if change_color is not None and replacement:
                        # Explicit offsets cover insertions and UTF-16 characters.
                        # Deletions leave no text to color.
                        start = word_offset(base.text, conflict.start)
                        area = document.Range(start, start + word_offset(replacement, len(replacement)))
                        # Native highlighting can be changed/removed with Word's
                        # Text Highlight Color command. Preserve existing shading.
                        area.HighlightColorIndex = highlight_color_index(change_color)
                        area = None
                document.TrackRevisions = track
                document.Save()
            finally:
                document.Close(False)
                document = None
            verified = read_document(app, temporary)
            if verified.text != expected:
                raise MergeError('word_merge_verify_failed')
            app = None
        if fingerprint(target.path) != target.digest:
            raise MergeError('merge_changed', path=target.path)
        if backup_original:
            shutil.copy2(target.path, merge_backup_path(target.path))
        os.replace(temporary, target.path)
        target.text, target.protected, target.digest = verified.text, verified.protected, fingerprint(target.path)
        target.tables = verified.tables
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
