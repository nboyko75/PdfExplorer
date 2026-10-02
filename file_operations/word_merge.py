"""Text-level Word merge, with an Office-rendered, in-place HTML review.

COM objects never leave the worker thread. Only plain snapshots and conflicts
are passed to the UI. Paragraph/table structure belongs to the original.
"""
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
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

from file_operations.excel_merge import MergeError, fingerprint, source_key

EXTENSIONS = {'.doc', '.docx', '.docm'}
MAX_CHARACTERS = 500000
CONTROL = re.compile(r'[\x00-\x08\x0c-\x1f]')
TOKEN = re.compile(r'\w+|[^\w\s]|[^\S\r]+|\r', re.UNICODE)


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
    finally:
        document.Close(False)
        document = None
    if fingerprint(path) != digest:
        raise MergeError('merge_changed', path=path)
    return Document(path, digest, text, protected)


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


def edits_for(base, other):
    """Align paragraphs first so insertions do not shift subsequent choices."""
    left, right = paragraphs(base.text), paragraphs(other.text)
    edits, skipped = [], 0
    matcher = SequenceMatcher(None, [p.group() for p in left],
                              [p.group() for p in right], autojunk=len(right) > 2000)
    for tag, i, j, k, l in matcher.get_opcodes():
        if tag == 'equal':
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


def conflicts_for(base, others):
    proposals, skipped = [], []
    for other in others:
        edits, count = edits_for(base, other)
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
        values, sources = [original], [[source_key(base.path)]]
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
            options.append('<option value="%s" style="color:%s"%s>%s</option>' % (
                choice, color, ' selected' if conflict.selected == choice else '',
                escape(label + ' [' + provenance + ']')))
        select = ('<select class="word-merge-choice" data-conflict="%s" aria-label="%s">%s</select>'
                  % (index, escape(labels['choose'], quote=True), ''.join(options)))
        if html.count(marker) != 1:
            raise MergeError('word_merge_preview_failed')
        html = html.replace(marker, select)
    style = '<style>.word-merge-choice {font:inherit;max-width:100%;background:#fff7ce;border:1px solid #b18a25;border-radius:3px;padding:1px 3px;}</style>'
    script = '''<script>
document.querySelectorAll('.word-merge-choice').forEach(function(select) {
    function color() { select.style.color = select.options[select.selectedIndex].style.color; }
    color();
    select.addEventListener('change', function() {
        color();
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
            document.SaveAs2(FileName=os.path.abspath(output), FileFormat=10,
                             AddToRecentFiles=False, Encoding=65001)
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


def save_merge(base, conflicts, backup_original=True):
    if any(type(c.selected) is not int or not 0 <= c.selected < len(c.values) for c in conflicts):
        raise MergeError('merge_unresolved')
    if fingerprint(base.path) != base.digest:
        raise MergeError('merge_changed', path=base.path)
    changes = sorted((c for c in conflicts if c.selected != 0), key=lambda c: c.start)
    if not changes:
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
                                     suffix=os.path.splitext(base.path)[1], dir=os.path.dirname(base.path))
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
                    checked_range(document, base, conflict).Text = conflict.values[conflict.selected]
                document.TrackRevisions = track
                document.Save()
            finally:
                document.Close(False)
                document = None
            verified = read_document(app, temporary)
            if verified.text != expected:
                raise MergeError('word_merge_verify_failed')
            app = None
        if fingerprint(base.path) != base.digest:
            raise MergeError('merge_changed', path=base.path)
        if backup_original:
            backup, number = base.path + '.merge-backup', 1
            while os.path.exists(backup):
                backup = base.path + '.merge-backup.' + str(number)
                number += 1
            shutil.copy2(base.path, backup)
        os.replace(temporary, base.path)
        base.text, base.protected, base.digest = verified.text, verified.protected, fingerprint(base.path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
