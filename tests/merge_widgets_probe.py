"""Manual native wx regression probe; opens a temporary test window."""
import ast
import colorsys
import ctypes
from pathlib import Path
import sys
import tempfile
import time
import zipfile
import xml.etree.ElementTree as ET
from contextlib import nullcontext
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wx
import wx.grid as gridlib
from common.sheet_table import SheetTable, OverflowRenderer
from file_operations import excel_merge as engine


def check_overflow_baselines(grid):
    table = grid.GetTable()
    original = table.sheet.cells[1, 1]
    table.sheet.cells[1, 1] = engine.Cell('H' * 80)
    try:
        for size in (10, 17):
            for vertical in (wx.ALIGN_TOP, wx.ALIGN_CENTER, wx.ALIGN_BOTTOM):
                attr = table.build_attr(0, 0)
                attr.SetFont(wx.Font(size, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
                attr.SetTextColour(wx.BLACK)
                attr.SetBackgroundColour(wx.WHITE)
                attr.SetAlignment(wx.ALIGN_LEFT, vertical)
                grid.SetAttr(0, 0, attr)
                bitmap = wx.Bitmap(240, 80)
                dc = wx.MemoryDC(bitmap)
                dc.SetBackground(wx.Brush(wx.WHITE))
                dc.Clear()
                width = grid.GetColSize(0)
                rect = wx.Rect(10, 10, width, 60)
                renderer = OverflowRenderer()
                renderer.Draw(grid, attr, dc, rect, 0, 0, False)
                rect.x += width
                renderer.Draw(grid, attr, dc, rect, 0, 1, False)
                dc.SelectObject(wx.NullBitmap)
                image = bitmap.ConvertToImage()
                def ink_rows(left, right):
                    return {y for y in range(10, 70) for x in range(left, right)
                            if max(image.GetRed(x, y), image.GetGreen(x, y), image.GetBlue(x, y)) < 100}
                base = ink_rows(15, 10 + width - 5)
                spill = ink_rows(15 + width, 10 + 2 * width - 5)
                assert base and base == spill, (size, vertical, sorted(base), sorted(spill))
    finally:
        table.sheet.cells[1, 1] = original
        grid.SetAttr(0, 0, table.build_attr(0, 0))


def read_saved_book(path):
    """Read-only fixture loader: use saved Excel values without opening Office."""
    ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    rel = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
    hidden = engine.saved_hidden_axes(str(path))
    sheets = {}
    with zipfile.ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        targets = {n.get('Id'): n.get('Target')
                   for n in ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))}
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings = [''.join(n.itertext()) for n in ET.fromstring(archive.read('xl/sharedStrings.xml'))]
        for item in workbook.find('s:sheets', ns):
            if item.get('state', 'visible') != 'visible':
                continue
            name = item.get('name')
            target = targets[item.get(rel + 'id')]
            root = ET.fromstring(archive.read(target.lstrip('/') if target.startswith('/') else 'xl/' + target))
            cells = {}
            for cell in root.findall('.//s:sheetData/s:row/s:c', ns):
                address = cell.get('r')
                col = 0
                for char in address:
                    if char.isalpha():
                        col = col * 26 + ord(char) - ord('A') + 1
                row = int(''.join(c for c in address if c.isdigit()))
                raw = cell.findtext('s:v', namespaces=ns)
                if cell.get('t') == 's':
                    value = strings[int(raw)] if raw else ''
                elif cell.get('t') == 'inlineStr':
                    value = ''.join(cell.find('s:is', ns).itertext())
                elif cell.get('t') == 'b':
                    value = raw == '1'
                elif raw is None or raw == '':
                    value = None
                elif cell.get('t') in ('str', 'e'):
                    value = raw
                else:
                    value = float(raw)
                formula = cell.findtext('s:f', namespaces=ns)
                if formula is not None or value is not None:
                    cells[row, col] = engine.Cell('=' + formula if formula is not None else value,
                                                  formula is not None, result=value)
            rows = max((r for r, c in cells), default=1)
            cols = max((c for r, c in cells), default=1)
            hidden_rows, hidden_cols = hidden.get(name, (set(), set()))
            sheets[name] = engine.Sheet(cells, rows, cols, hidden_rows, hidden_cols, styles_loaded=True)
    return engine.Book(str(path), engine.fingerprint(path), sheets)


def probe_dialog(folder):
    """Exercise Search -> check three of six -> Compare -> each sheet tab."""
    from controls.merge_excel import MergeDialog
    paths = list(Path(folder).glob('*.xlsx'))
    base_path = min(paths, key=lambda path: len(path.name))
    books = {engine.source_key(path): read_saved_book(path) for path in paths}
    wanted_suffixes = (' ЗУ.xlsx', ' СА та ППО.xlsx', ' СОВТ та МСВ.xlsx')
    app = wx.App(False)
    failures, completed = [], []
    with patch.object(engine, 'excel_app', lambda: nullcontext(None)), \
         patch.object(engine, 'read_book', lambda app, path, **kw: books[engine.source_key(path)]):
        dialog = MergeDialog(None, str(base_path))
        dialog.Show()
        deadline = time.monotonic() + 40
        state = {'stage': 0, 'tab': 0, 'checked': set()}
        def tick():
            try:
                assert time.monotonic() < deadline, 'Dialog probe timed out'
                if dialog.busy or dialog.base is None:
                    wx.CallLater(50, tick)
                    return
                if state['stage'] == 0:
                    dialog.on_search(None)
                    state['stage'] = 1
                elif state['stage'] == 1:
                    assert len(dialog.matches) == 6
                    for index, (book, score) in enumerate(dialog.matches):
                        checked = book.path.endswith(wanted_suffixes)
                        dialog.files.Check(index, checked)
                        if checked:
                            state['checked'].add(engine.source_key(book.path))
                    assert len(state['checked']) == 3
                    state['stage'] = 2
                elif state['stage'] == 2:
                    dialog.on_compare(None)
                    state['stage'] = 3
                elif state['stage'] == 3:
                    assert dialog.compared
                    allowed = state['checked'] | {engine.source_key(base_path)}
                    for conflict in dialog.conflicts:
                        assert set(source for group in conflict.sources for source in group) <= allowed
                    page = dialog.notebook.GetPage(state['tab'])
                    if page.grid is None:
                        dialog.ensure_selected_sheet()
                        wx.CallLater(50, tick)
                        return
                    table = page.grid.GetTable()
                    shared = 0
                    for pos, sources in table.choice_sources.items():
                        assert set(sources) <= allowed
                        for index, source in enumerate(sources):
                            assert table.colors[pos][index] == dialog.source_colors[source]
                        conflict = table.conflicts[pos]
                        selected = conflict.selected
                        if selected is not None and table.value_indices[pos].count(selected) > 1:
                            shared += 1
                            assert table.selected_color(pos) == (0, 0, 0)
                            # Choosing another contributor of the SAME value
                            # must retain its color when the table is rebuilt.
                            option = max(i for i, n in enumerate(table.value_indices[pos]) if n == selected)
                            table.select_choice(pos, option)
                            assert table.selected_color(pos) == dialog.source_colors[sources[option]]
                            rebuilt = SheetTable(table.sheet, table.conflicts, source_colors=dialog.source_colors)
                            assert rebuilt.selected_color(pos) == table.selected_color(pos)
                    print('Sheet', page.sheet_name, ':', len(table.conflicts), 'conflicts;', shared,
                          'shared values; only checked source filenames/colors present', flush=True)
                    state['tab'] += 1
                    if state['tab'] == dialog.notebook.GetPageCount():
                        dialog.files.Check(dialog.files.GetCheckedItems()[0], False)
                        state['stage'] = 4
                    else:
                        dialog.notebook.SetSelection(state['tab'])
                else:
                    assert not dialog.compared and not dialog.conflicts
                    for i in range(dialog.notebook.GetPageCount()):
                        table = dialog.notebook.GetPage(i).grid.GetTable()
                        assert not table.conflicts and not table.choice_sources and not table.colors
                    completed.append(True)
                    dialog.dispose()
                    return
                wx.CallLater(50, tick)
            except Exception as error:
                failures.append(error)
                dialog.dispose()
        wx.CallLater(100, tick)
        app.MainLoop()
    if failures:
        raise failures[0]
    assert completed
    print('PASS: full dialog with six real workbooks, three checked, all tabs, then uncheck invalidation')


def main():
    source = ast.parse(Path('controls/merge_documents.py').read_text())
    scope = {'wx': wx, 'colorsys': colorsys}
    definitions = [n for n in source.body if isinstance(n, (ast.ClassDef, ast.FunctionDef))
                   and n.name in ('MergeFileList', 'file_color')]
    exec(compile(ast.Module(body=definitions, type_ignores=[]), 'merge_list', 'exec'), scope)
    app = wx.App(False)
    frame = wx.Frame(None, title='Merge widget regression probe', size=(800, 350))
    panel = wx.Panel(frame)
    layout = wx.BoxSizer(wx.VERTICAL)
    files = scope['MergeFileList'](panel, lambda event: None)
    colors = {}
    for name in ('one.xlsx', 'two.xlsx', 'three.xlsx'):
        index = files.Append(name)
        color = scope['file_color'](index)
        colors[name] = color
        files.SetItemTextColour(index, wx.Colour(*color))
        files.Check(index, True)
    layout.Add(files, 1, wx.EXPAND)
    sheet = engine.Sheet({(1, 1): engine.Cell('Long text overflowing into the empty cells to the right'),
                          (2, 2): engine.Cell('anchor')}, 2, 2)
    conflict = engine.Conflict('s', 2, 1, [engine.EMPTY, engine.Cell('one'), engine.Cell('two')],
                               [['base.xlsx'], ['one.xlsx'], ['two.xlsx']], 1)
    table = SheetTable(sheet, {(2, 1): conflict}, source_colors=colors, min_columns=5)
    grid = gridlib.Grid(panel)
    grid.SetTable(table, True)
    grid.SetDefaultRenderer(OverflowRenderer())
    grid.SetDefaultCellOverflow(True)
    for r in range(2):
        for c in range(5):
            grid.SetAttr(r, c, table.build_attr(r, c))
    layout.Add(grid, 1, wx.EXPAND)
    panel.SetSizer(layout)
    frame.Show()
    failures = []
    completed = []
    artifacts = Path(tempfile.mkdtemp(prefix='merge_widgets_'))
    def schedule(callback, delay=300):
        def run():
            try:
                callback()
            except Exception as error:
                failures.append(error)
                frame.Destroy()
        wx.CallLater(delay, run)
    def timeout():
        if frame:
            failures.append(AssertionError('Native widget checks timed out'))
            frame.Destroy()
    wx.CallLater(10000, timeout)
    def click(window, point):
        # Send actual MSW mouse messages to the control. Global SendInput can
        # hit the IDE if it takes foreground focus while this probe runs.
        position = (point.y << 16) | (point.x & 0xffff)
        user32 = ctypes.windll.user32
        user32.SendMessageW.argtypes = (ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t)
        user32.SendMessageW(window.GetHandle(), 0x0201, 1, position)
        user32.SendMessageW(window.GetHandle(), 0x0202, 0, position)

    def probe():
        try:
            check_overflow_baselines(grid)
            assert table.colors[2, 1] == [(0, 0, 0), colors['one.xlsx'], colors['two.xlsx']]
            files.Select(0)
            rect = files.GetItemRect(1)
            point = wx.Point(rect.x + 70, rect.y + rect.height // 2)
            event = wx.MouseEvent(wx.wxEVT_LEFT_DOWN)
            event.SetPosition(point)
            files.on_mouse(event)
            files.on_mouse_up(event)
            assert files.GetCheckedItems() == [0, 2]
            grid.SetGridCursor(1, 0)
            grid.EnableCellEditControl()
            editor = grid.GetCellEditor(1, 0)
            combo = editor.GetControl()
            assert combo.GetSelection() == 1
            combo.SetSelection(2)
            grid.SaveEditControlValue()
            grid.DisableCellEditControl()
            assert conflict.selected == 2 and table.GetValue(1, 0) == 'two'
            editor.DecRef()
            bitmap = wx.Bitmap(700, 120)
            dc = wx.MemoryDC(bitmap)
            dc.SetBackground(wx.Brush(wx.WHITE))
            dc.Clear()
            grid.Render(dc)
            dc.SelectObject(wx.NullBitmap)
            bitmap.SaveFile(str(artifacts / 'render.png'), wx.BITMAP_TYPE_PNG)
            # Exercise the popup focus/selection lifecycle with actual input.
            schedule(open_popup)
        except Exception:
            frame.Destroy()
            raise
    def open_popup():
        frame.Raise()
        files.SetFocus()
        files.Select(0)
        rect = files.GetItemRect(2)
        click(files, wx.Point(rect.x + 70, rect.y + rect.height // 2))
        schedule(open_editor)
    def open_editor():
        assert files.GetCheckedItems() == [0] and files.GetSelection() == 2, (
            files.GetCheckedItems(), files.GetSelection())
        base = engine.Book('base.xlsx', '', {'s': engine.Sheet({(1, 1): engine.Cell('base')})})
        books = [engine.Book(name, '', {'s': engine.Sheet({(1, 1): engine.Cell(name)})})
                 for name in colors]
        conflicts = engine.conflicts_for(base, [books[i] for i in files.GetCheckedItems()])
        assert [value.value for value in conflicts[0].values] == ['base', 'one.xlsx']
        grid.EnableCellEditControl()
        editor = grid.GetCellEditor(1, 0)
        combo = editor.GetControl()
        combo.Popup()
        editor.DecRef()
        schedule(choose)
    def choose():
        assert grid.IsCellEditControlEnabled(), 'Popup focus prematurely ended editing'
        editor = grid.GetCellEditor(1, 0)
        popup = editor.GetControl().GetPopupControl().GetControl()
        for key in (0x24, 0x0D):  # Win32 VK_HOME, VK_RETURN
            ctypes.windll.user32.SendMessageW(popup.GetHandle(), 0x0100, key, 0)
            ctypes.windll.user32.SendMessageW(popup.GetHandle(), 0x0101, key, 0)
        editor.DecRef()
        schedule(check_blank)
    def check_blank():
        assert conflict.selected == 0 and table.GetValue(1, 0) == ''
        grid.EnableCellEditControl()
        editor = grid.GetCellEditor(1, 0)
        combo = editor.GetControl()
        combo.Popup()
        editor.DecRef()
        schedule(choose_mouse)
    def choose_mouse():
        assert grid.IsCellEditControlEnabled()
        editor = grid.GetCellEditor(1, 0)
        combo = editor.GetControl()
        popup = combo.GetPopupWindow()
        print('Popup size:', popup.GetClientSize(), flush=True)
        bitmap = wx.Bitmap(popup.GetClientSize())
        dc = wx.MemoryDC(bitmap)
        dc.Blit(0, 0, *popup.GetClientSize(), wx.ClientDC(popup), 0, 0)
        dc.SelectObject(wx.NullBitmap)
        bitmap.SaveFile(str(artifacts / 'popup.png'), wx.BITMAP_TYPE_PNG)
        pixels = bitmap.ConvertToImage().GetData()
        for color in (colors['one.xlsx'], colors['two.xlsx']):
            assert bytes(color) in bytes(pixels), 'Missing source color in actual popup'
        click(combo.GetPopupControl().GetControl(),
              wx.Point(10, combo.OnMeasureItem(0) + combo.OnMeasureItem(1) // 2))
        editor.DecRef()
        schedule(finish)
    def finish():
        assert conflict.selected == 1 and table.GetValue(1, 0) == 'one', 'Mouse selection was lost'
        window = grid.GetGridWindow()
        bitmap = wx.Bitmap(window.GetClientSize())
        dc = wx.MemoryDC(bitmap)
        dc.Blit(0, 0, *window.GetClientSize(), wx.ClientDC(window), 0, 0)
        dc.SelectObject(wx.NullBitmap)
        image = bitmap.ConvertToImage()
        rect = grid.CellToRect(0, 2)  # Blank C, beyond the source UsedRange.
        assert any(image.GetRed(x, y) < 100 and image.GetGreen(x, y) < 100
                   and image.GetBlue(x, y) < 100
                   for x in range(rect.x + 3, rect.x + rect.width - 3)
                   for y in range(rect.y + 3, rect.y + rect.height - 3)), 'Text did not spill into C1'
        bitmap = wx.Bitmap(panel.GetClientSize())
        dc = wx.MemoryDC(bitmap)
        dc.Blit(0, 0, *panel.GetClientSize(), wx.ClientDC(panel), 0, 0)
        dc.SelectObject(wx.NullBitmap)
        bitmap.SaveFile(str(artifacts / 'window.png'), wx.BITMAP_TYPE_PNG)
        completed.append(True)
        frame.Destroy()
    schedule(probe, 500)
    app.MainLoop()
    print('Native widget screenshots:', artifacts)
    if failures:
        raise failures[0]
    assert completed, 'Native widget checks did not complete'
    print('PASS: row clicks, checked inputs, source colors, blank and mouse combo choices, visible overflow')


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--dialog':
        probe_dialog(sys.argv[2])
    else:
        main()
