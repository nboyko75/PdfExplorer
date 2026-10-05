"""Shared Excel/Word merge review form. Office I/O runs off the GUI thread."""
import os
import colorsys
import tempfile
import threading
import time
import json
import uuid
from pathlib import Path
import wx.html2 as html2
from concurrent.futures import ThreadPoolExecutor
import wx
import wx.grid as gridlib
from localization import tr
from file_operations import excel_merge as engine
from file_operations import word_merge
from common.webview import create_webview
from common.sheet_table import SheetTable, OverflowRenderer
from common.window_tools import load_settings, update_settings


def error_text(exc):
    return tr(exc.key, **exc.params) if isinstance(exc, engine.MergeError) else str(exc)


def file_color(index):
    # Golden-angle spacing gives each file a stable, non-black text color.
    rgb = colorsys.hsv_to_rgb((0.61 + index * 0.61803398875) % 1, 0.82, 0.64)
    return tuple(round(channel * 255) for channel in rgb)


class MergeFileList(wx.ListCtrl):
    def __init__(self, parent, changed):
        super().__init__(parent, style=wx.LC_REPORT | wx.LC_NO_HEADER | wx.LC_SINGLE_SEL)
        self.changed = changed
        self.InsertColumn(0, '')
        self.EnableCheckBoxes(True)
        self.Bind(wx.EVT_LEFT_DOWN, self.on_mouse)
        self.Bind(wx.EVT_LEFT_DCLICK, self.on_mouse)
        self.Bind(wx.EVT_LEFT_UP, self.on_mouse_up)
        self.pressed_row = wx.NOT_FOUND
        self.Bind(wx.EVT_KEY_DOWN, self.on_key)
        self.Bind(wx.EVT_SIZE, self.on_size)
        self.Bind(wx.EVT_LIST_ITEM_CHECKED, self.on_check)
        self.Bind(wx.EVT_LIST_ITEM_UNCHECKED, self.on_check)

    def on_check(self, event):
        # Native check notifications can arrive before IsItemChecked changes.
        wx.CallAfter(self.changed, None)
        event.Skip()

    def on_size(self, event):
        self.SetColumnWidth(0, max(80, self.GetClientSize().width - 8))
        event.Skip()

    def Clear(self):
        self.DeleteAllItems()

    def Append(self, label):
        return self.InsertItem(self.GetItemCount(), label)

    def Check(self, index, checked=True):
        self.CheckItem(index, checked)

    def GetCheckedItems(self):
        return [i for i in range(self.GetItemCount()) if self.IsItemChecked(i)]

    def GetSelection(self):
        return self.GetFirstSelected()

    def on_mouse(self, event):
        index = self.row_at(event.GetPosition())
        self.pressed_row = index
        if index != wx.NOT_FOUND:
            self.SetFocus()
            self.Select(index)
            self.Focus(index)
            return
        event.Skip()

    def row_at(self, point):
        # Resolve the clicked row from its visible bounds, including scrolling,
        # independently of the selected row or header offsets.
        first = max(0, self.GetTopItem())
        last = min(self.GetItemCount(), first + self.GetCountPerPage() + 2)
        for index in range(first, last):
            rect = self.GetItemRect(index)
            if rect.y <= point.y < rect.y + rect.height:
                return index
        return wx.NOT_FOUND

    def on_mouse_up(self, event):
        index, self.pressed_row = self.pressed_row, wx.NOT_FOUND
        if index != wx.NOT_FOUND:
            if index == self.row_at(event.GetPosition()):
                self.CheckItem(index, not self.IsItemChecked(index))
                self.changed(None)
            return  # Consume both halves of the click; native code must not toggle again.
        event.Skip()

    def on_key(self, event):
        if event.GetKeyCode() in (wx.WXK_SPACE, wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            index = self.GetSelection()
            if index != wx.NOT_FOUND:
                self.CheckItem(index, not self.IsItemChecked(index))
                self.changed(None)
            return
        event.Skip()  # Arrow keys change selection only.


class MergeDialog(wx.Dialog):
    instructions_key = 'merge_instructions'
    ready_key = 'merge_ready'

    def __init__(self, owner, path):
        super().__init__(owner, title=tr('merge_documents'), size=(1150, 750),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.owner = owner
        self.path = os.path.abspath(path)
        self.preview_dir = tempfile.TemporaryDirectory(prefix="docexplorer_merge_")
        self.preview_paths = {}
        self.base = None
        self.matches = []
        self.source_colors = {}
        self.book_cache = {}
        self.progress_lock = threading.Lock()
        self.progress_state = None
        self.conflicts = []
        self.compared = False
        self.saved_changes = False
        self.busy = False
        self.cancel_pending = False
        self.close_after_save = False
        self.disposed = False
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.display_book = None
        self.building_pages = False
        outer = wx.BoxSizer(wx.VERTICAL)
        header = wx.BoxSizer(wx.HORIZONTAL)
        title = wx.StaticText(self, label=self.path.replace("&", "&&"),
                              style=wx.ST_ELLIPSIZE_MIDDLE)
        title.SetToolTip(self.path)
        header.Add(title, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        info = wx.BitmapButton(self, bitmap=wx.ArtProvider.GetBitmap(wx.ART_INFORMATION, wx.ART_BUTTON, (20, 20)))
        info.SetToolTip(tr(self.instructions_key))
        info.SetName(tr('merge_preview'))
        info.Bind(wx.EVT_BUTTON, self.show_instructions)
        header.Add(info, 0, wx.ALIGN_CENTER_VERTICAL)
        outer.Add(header, 0, wx.EXPAND | wx.ALL, 10)
        splitter = wx.SplitterWindow(self, style=wx.SP_LIVE_UPDATE)
        left = wx.Panel(splitter)
        left_sizer = wx.BoxSizer(wx.VERTICAL)
        check_bar = wx.BoxSizer(wx.HORIZONTAL)
        self.check_all = wx.CheckBox(left, label='')
        self.uncheck_all = wx.CheckBox(left, label='')
        self.check_all.SetValue(True)
        self.check_all.SetToolTip(tr('merge_check_all'))
        self.uncheck_all.SetToolTip(tr('merge_uncheck_all'))
        self.check_all.SetName(tr('merge_check_all'))
        self.uncheck_all.SetName(tr('merge_uncheck_all'))
        check_bar.Add(self.check_all, 0, wx.RIGHT, 10)
        check_bar.Add(self.uncheck_all, 0)
        left_sizer.Add(check_bar, 0, wx.ALL, 5)
        self.check_all.Bind(wx.EVT_CHECKBOX, lambda event: self.set_all_checks(True))
        self.uncheck_all.Bind(wx.EVT_CHECKBOX, lambda event: self.set_all_checks(False))
        self.files = MergeFileList(left, self.on_checks)
        left_sizer.Add(self.files, 1, wx.EXPAND)
        left.SetSizer(left_sizer)
        right = wx.Panel(splitter)
        right_sizer = wx.BoxSizer(wx.VERTICAL)
        self.notebook = wx.Notebook(right, style=wx.NB_BOTTOM)
        self.notebook.SetFont(wx.Font(10, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL,
                                      wx.FONTWEIGHT_NORMAL, faceName="Calibri"))
        right_sizer.Add(self.notebook, 1, wx.EXPAND)
        mark_bar = wx.BoxSizer(wx.HORIZONTAL)
        self.mark_changes_checkbox = wx.CheckBox(right, label=tr('merge_mark_changes'))
        self.change_color_picker = wx.ColourPickerCtrl(right, colour=wx.Colour(255, 255, 0))
        self.change_color_picker.SetName(tr('merge_change_color'))
        self.change_color_picker.SetToolTip(tr('merge_change_color'))
        self.change_color_picker.Disable()
        self.mark_changes_checkbox.Bind(wx.EVT_CHECKBOX, self.on_mark_changes)
        mark_bar.Add(self.mark_changes_checkbox, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        mark_bar.Add(self.change_color_picker, 0, wx.ALIGN_CENTER_VERTICAL)
        right_sizer.Add(mark_bar, 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 8)
        right.SetSizer(right_sizer)
        splitter.SplitVertically(left, right, 250)
        splitter.SetMinimumPaneSize(160)
        outer.Add(splitter, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        self.status = wx.StaticText(self, label=tr(self.ready_key))
        info_bar = wx.BoxSizer(wx.HORIZONTAL)
        info_bar.Add(self.status, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        self.progress = wx.Gauge(self, range=1000, size=(180, 16))
        self.progress.Hide()
        info_bar.Add(self.progress, 0, wx.ALIGN_CENTER_VERTICAL)
        outer.Add(info_bar, 0, wx.EXPAND | wx.ALL, 10)
        self.progress_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_progress_timer, self.progress_timer)
        bar = wx.BoxSizer(wx.HORIZONTAL)
        self.backup_checkbox = wx.CheckBox(self, label=tr('merge_backup_original_file'))
        self.backup_checkbox.SetValue(bool(load_settings().get('merge_backup_original_file', True)))
        self.backup_checkbox.Bind(wx.EVT_CHECKBOX, self.on_backup_checkbox)
        bar.Add(self.backup_checkbox, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 12)
        bar.AddStretchSpacer()
        self.search_button = wx.Button(self, label=tr('merge_search'))
        self.compare_button = wx.Button(self, label=tr('merge_compare'))
        self.save_button = wx.Button(self, label=tr('merge_save'))
        self.cancel_button = wx.Button(self, wx.ID_CANCEL, tr('exit_button'))
        for button in (self.search_button, self.compare_button, self.save_button, self.cancel_button):
            bar.Add(button, 0, wx.LEFT, 7)
        outer.Add(bar, 0, wx.EXPAND | wx.ALL, 10)
        self.SetSizer(outer)
        self.SetMinSize((800, 500))
        self.search_button.Bind(wx.EVT_BUTTON, self.on_search)
        self.compare_button.Bind(wx.EVT_BUTTON, self.on_compare)
        self.save_button.Bind(wx.EVT_BUTTON, self.on_save)
        self.cancel_button.Bind(wx.EVT_BUTTON, self.on_cancel)
        self.Bind(wx.EVT_CLOSE, self.on_cancel)
        self.files.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_select)
        self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.on_sheet_changed)
        self.update_buttons()
        self.CentreOnParent()
        wx.CallAfter(self.run_job, self.load_initial, self.loaded, tr('merge_initializing'))

    def on_backup_checkbox(self, event):
        update_settings({'merge_backup_original_file': bool(self.backup_checkbox.GetValue())})

    def on_mark_changes(self, event):
        self.change_color_picker.Enable(not self.busy and self.mark_changes_checkbox.GetValue())

    def selected_change_color(self):
        if not self.mark_changes_checkbox.GetValue():
            return None
        color = self.change_color_picker.GetColour()
        return color.Red(), color.Green(), color.Blue()

    def show_instructions(self, event):
        popup = wx.PopupTransientWindow(self, wx.BORDER_SIMPLE)
        panel = wx.Panel(popup)
        label = wx.StaticText(panel, label=tr(self.instructions_key))
        label.Wrap(480)
        content = wx.BoxSizer(wx.VERTICAL)
        content.Add(label, 0, wx.ALL, 12)
        panel.SetSizerAndFit(content)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(panel)
        popup.SetSizerAndFit(outer)
        button = event.GetEventObject()
        popup.Position(button.ClientToScreen((0, 0)), button.GetSize())
        popup.Popup()

    def load_initial(self):
        with engine.excel_app() as app:
            book = engine.read_book(app, self.path, progress=self.report_progress)
        return book, None

    def loaded(self, result):
        book, html = result
        if html:
            self.preview_paths[book.digest] = html
        self.base = book
        self.show_book(book, True)
        self.status.SetLabel(tr('merge_ready'))

    def report_progress(self, current, total, detail):
        # A single latest value prevents thousands of queued GUI callbacks.
        with self.progress_lock:
            self.progress_state = (current, total, detail)

    def on_progress_timer(self, event):
        if self.disposed or not self.busy:
            return
        with self.progress_lock:
            state = self.progress_state
        if state is None:
            self.progress.Pulse()
        else:
            current, total, detail = state
            self.progress.SetValue(min(1000, int(1000 * current / max(1, total))))
            if not self.cancel_pending:
                self.status.SetLabel(f'{self.job_label} {detail} ({int(current)}/{total})')

    def run_job(self, task, done, label=None):
        if self.disposed:
            return
        self.busy = True
        self.job_label = label or tr('merge_working')
        with self.progress_lock:
            self.progress_state = None
        self.progress.SetValue(0)
        self.progress.Show()
        self.progress_timer.Start(100)
        self.Layout()
        self.wait_cursor = wx.BusyCursor()
        self.status.SetLabel(self.job_label)
        self.update_buttons()
        try:
            future = self.executor.submit(task)
        except Exception:
            self.progress_timer.Stop()
            self.progress.Hide()
            self.busy = False
            self.wait_cursor = None
            if getattr(self, 'saving', False):
                self.save_failed()
            self.update_buttons()
            raise
        def finished(future):
            if not self.disposed:
                wx.CallAfter(self.finish_job, future, done)
        future.add_done_callback(finished)

    def finish_job(self, future, done):
        if self.disposed:
            return
        self.progress_timer.Stop()
        self.progress.Hide()
        self.Layout()
        self.busy = False
        self.wait_cursor = None
        try:
            result = future.result()
            done(result)
        except Exception as exc:
            self.status.SetLabel(tr('merge_failed'))
            wx.MessageBox(error_text(exc), tr('merge_documents'), wx.OK | wx.ICON_ERROR, self)
        if not self.disposed:
            self.update_buttons()
            wx.CallAfter(self.resume_close)

    def update_buttons(self):
        self.search_button.Enable(not self.busy and self.base is not None)
        self.compare_button.Enable(not self.busy and bool(self.matches) and bool(self.files.GetCheckedItems()))
        self.save_button.Enable(not self.busy and self.compared and all(c.selected is not None for c in self.conflicts))
        self.files.Enable(not self.busy)
        self.check_all.Enable(not self.busy)
        self.uncheck_all.Enable(not self.busy)
        self.notebook.Enable(not self.busy)
        self.mark_changes_checkbox.Enable(not self.busy)
        self.on_mark_changes(None)

    def on_search(self, event):
        self.compared = False
        self.conflicts = []
        self.matches = []
        self.files.Clear()
        self.source_colors = {}
        def done(result):
            self.base, self.matches, skipped = result
            self.matches.sort(key=lambda match: os.path.basename(match[0].path).casefold())
            for book, score in self.matches:
                index = self.files.Append(os.path.basename(book.path))
                self.files.Check(index, True)
                color = file_color(index)
                self.source_colors[engine.source_key(book.path)] = color
                self.files.SetItemTextColour(index, wx.Colour(*color))
            if self.matches:
                self.files.Select(0)
                self.files.Focus(0)
            self.show_selected_book()
            self.status.SetLabel(tr('merge_found', count=len(self.matches), skipped=len(skipped)))
            if skipped:
                wx.MessageBox('\n'.join(os.path.basename(p) + ': ' + error_text(e) for p, e in skipped),
                              tr('merge_documents'), wx.OK | wx.ICON_INFORMATION, self)
        self.run_job(lambda: engine.search_books(self.path, self.base, self.book_cache,
                                                    self.report_progress), done, tr('merge_search'))

    def on_compare(self, event):
        self.on_checks(None)
        books = [self.matches[i][0] for i in self.files.GetCheckedItems()]
        # Read the displayed colors, so choice provenance matches the actual
        # rows even after a new search or a change in their ordering.
        self.source_colors = {engine.source_key(self.base.path): (0, 0, 0)}
        for index in self.files.GetCheckedItems():
            color = self.files.GetItemTextColour(index)
            self.source_colors[engine.source_key(self.matches[index][0].path)] = (
                color.Red(), color.Green(), color.Blue())
        def task():
            for book in [self.base] + books:
                if engine.fingerprint(book.path) != book.digest:
                    raise engine.MergeError('merge_changed', path=book.path)
            # Search caches contain raw values only. Read checked inputs with
            # Excel display text before offering their values in the review.
            with engine.excel_app() as app:
                formatted_books = [engine.read_book(app, book.path, load_first_style=False)
                                   for book in books]
            return engine.conflicts_for(self.base, formatted_books)
        def done(conflicts):
            if books != [self.matches[i][0] for i in self.files.GetCheckedItems()]:
                self.on_checks(None)
                return
            self.conflicts = conflicts
            self.compared = True
            self.show_selected_book()
            self.update_conflicts()
            unmatched = []
            for book in books:
                for name in sorted(set(book.sheets) ^ set(self.base.sheets)):
                    unmatched.append(os.path.basename(book.path) + ': ' + name)
            if unmatched:
                wx.MessageBox(tr('merge_unmatched') + '\n' + '\n'.join(unmatched),
                              tr('merge_documents'), wx.OK | wx.ICON_INFORMATION, self)
        self.run_job(task, done)

    def show_book(self, book, target=False):
        book = self.base  # The review always edits the original workbook.
        if book is None:
            return
        selection = self.notebook.GetSelection()
        selected_name = (self.notebook.GetPage(selection).sheet_name
                         if selection != wx.NOT_FOUND else None)
        self.building_pages = True
        try:
            self.display_book = book
            self.notebook.DeleteAllPages()
            for name in book.sheets:
                page = wx.Panel(self.notebook)
                page.sheet_name = name
                page.grid = None
                self.notebook.AddPage(page, name, select=name == selected_name)
        finally:
            self.building_pages = False
        self.Layout()
        wx.CallAfter(self.ensure_selected_sheet)

    def on_sheet_changed(self, event):
        event.Skip()
        if not self.building_pages:
            wx.CallAfter(self.ensure_selected_sheet)

    def ensure_selected_sheet(self):
        if self.disposed or self.busy or self.building_pages:
            return
        index = self.notebook.GetSelection()
        if index == wx.NOT_FOUND:
            return
        page = self.notebook.GetPage(index)
        if page.grid is not None:
            page.grid.ForceRefresh()
            return
        book = self.display_book
        name = page.sheet_name
        sheet = book.sheets[name]
        if sheet.styles_loaded:
            self.build_sheet_page(page, name, sheet)
            return
        def done(result):
            sheet.styles, sheet.row_heights, sheet.col_widths = result
            sheet.styles_loaded = True
            if self.display_book is book and page and not page.IsBeingDeleted():
                self.build_sheet_page(page, name, sheet)
            if self.compared:
                self.update_conflicts()
            else:
                self.status.SetLabel(tr('merge_ready'))
        self.run_job(lambda: engine.load_sheet_layout(book, name), done)

    def build_sheet_page(self, page, name, sheet):
        conflicts = {(c.row, c.col): c for c in self.conflicts if c.sheet == name and c.row not in sheet.hidden_rows and c.col not in sheet.hidden_cols}
        grid = gridlib.Grid(page)
        # Excel UsedRange ends at the last used column. Keep real blank grid
        # cells to its right, otherwise even a renderer cannot spill into them.
        min_columns = max(1, (page.GetClientSize().width - 48) // 100 + 2)
        table = SheetTable(sheet, conflicts, source_colors=self.source_colors,
                           min_columns=min_columns)
        grid.SetTable(table, takeOwnership=True)
        font = wx.Font(11, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL,
                       wx.FONTWEIGHT_NORMAL, faceName="Calibri")
        grid.SetDefaultCellFont(font)
        grid.SetLabelFont(font)
        grid.SetDefaultCellBackgroundColour(wx.Colour(255, 255, 255))
        grid.SetDefaultCellTextColour(wx.Colour(32, 32, 32))
        grid.SetDefaultCellOverflow(True)
        grid.SetDefaultRenderer(OverflowRenderer())
        grid.SetDefaultCellAlignment(wx.ALIGN_LEFT, wx.ALIGN_CENTER)
        grid.SetLabelBackgroundColour(wx.Colour(242, 242, 242))
        grid.SetLabelTextColour(wx.Colour(80, 80, 80))
        grid.SetGridLineColour(wx.Colour(217, 217, 217))
        grid.SetSelectionBackground(wx.Colour(226, 239, 218))
        grid.SetSelectionForeground(wx.Colour(32, 32, 32))
        grid.SetCellHighlightColour(wx.Colour(33, 115, 70))
        grid.SetCellHighlightPenWidth(2)
        grid.SetRowLabelSize(48)
        grid.SetColLabelSize(24)
        grid.SetDefaultColSize(100)
        grid.SetDefaultRowSize(23)
        grid.Bind(gridlib.EVT_GRID_CELL_CHANGED, self.on_cell_changed)
        grid.Bind(gridlib.EVT_GRID_CELL_LEFT_CLICK, self.on_cell_click)
        page.grid = grid
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(grid, 1, wx.EXPAND)
        page.SetSizer(sizer)
        page.Layout()
        dpi = grid.GetDPI()
        def populate():
            for row, col in set(sheet.styles) | set(sheet.cells) | set(conflicts):
                position = table.grid_position(row, col)
                if position is not None:
                    grid.SetAttr(*position, table.build_attr(*position))
                yield
            for row, points in sheet.row_heights.items():
                if row in table.row_indices:
                    grid.SetRowSize(table.row_indices[row], max(1, round(points * dpi.height / 72)))
                yield
            for col, points in sheet.col_widths.items():
                if col in table.col_indices:
                    grid.SetColSize(table.col_indices[col], max(1, round(points * dpi.width / 72)))
                yield
        # Keep native event processing alive while installing large grids.
        remaining = populate()
        previous_status = tr('merge_ready')
        self.busy = True
        self.job_label = tr('merge_initializing')
        with self.progress_lock:
            self.progress_state = None
        self.status.SetLabel(self.job_label + ' ' + name)
        self.progress.Show()
        self.progress_timer.Start(100)
        self.update_buttons()
        self.Layout()
        def batch():
            if self.disposed:
                return
            complete = False
            failure = None
            grid.BeginBatch()
            try:
                deadline = time.monotonic() + .012
                while not complete and time.monotonic() < deadline:
                    try:
                        next(remaining)
                    except StopIteration:
                        complete = True
            except Exception as exc:
                failure = exc
                complete = True
            finally:
                grid.EndBatch()
            if not complete:
                wx.CallLater(1, batch)
                return
            self.progress_timer.Stop()
            self.progress.Hide()
            self.busy = False
            self.status.SetLabel(tr('merge_failed') if failure else previous_status)
            if failure:
                wx.MessageBox(error_text(failure), tr('merge_documents'), wx.OK | wx.ICON_ERROR, self)
            elif self.compared:
                self.update_conflicts()
            self.update_buttons()
            self.Layout()
            if conflicts:
                row, col = next(iter(conflicts))
                position = table.grid_position(row, col)
                if position is not None:
                    grid.SetGridCursor(*position)
                    grid.MakeCellVisible(*position)
            wx.CallAfter(self.resume_close)
        wx.CallLater(1, batch)

    def select_preview(self, book, target=False):
        if book is not None:
            self.show_book(book, target)

    def on_cell_click(self, event):
        grid = event.GetEventObject()
        row, col = event.GetRow(), event.GetCol()
        if grid.GetTable().cell_position(row, col) in grid.GetTable().conflicts:
            # Consume this event so wx does not activate a second editor itself.
            self.edit_cell(grid, row, col)
        else:
            event.Skip()

    def edit_cell(self, grid, row, col):
        if self.disposed or self.busy or not grid or grid.IsBeingDeleted():
            return
        if grid.IsCellEditControlEnabled():
            if (grid.GetGridCursorRow(), grid.GetGridCursorCol()) == (row, col):
                return
            grid.SaveEditControlValue()
            grid.DisableCellEditControl()
        grid.SetGridCursor(row, col)
        grid.EnableCellEditControl()

    def on_cell_changed(self, event):
        event.Skip()
        wx.CallAfter(self.update_conflicts)

    def update_conflicts(self):
        if self.disposed:
            return
        unresolved = sum(c.selected is None for c in self.conflicts)
        self.status.SetLabel(tr('merge_conflicts', total=len(self.conflicts), count=unresolved))
        self.update_buttons()

    def show_selected_book(self):
        self.show_book(self.base, True)

    def on_select(self, event):
        # Source selection only highlights a list entry; checkboxes select inputs.
        event.Skip()

    def set_all_checks(self, checked):
        for index in range(self.files.GetItemCount()):
            self.files.Check(index, checked)
        self.check_all.SetValue(True)
        self.uncheck_all.SetValue(False)
        self.on_checks(None)

    def on_checks(self, event):
        self.compared = False
        self.conflicts = []
        # Keep the existing pages, scroll positions and loaded formatting.
        for index in range(self.notebook.GetPageCount()):
            grid = getattr(self.notebook.GetPage(index), 'grid', None)
            if grid is None:
                continue
            if grid.IsCellEditControlEnabled():
                grid.DisableCellEditControl()
            table = grid.GetTable()
            old_positions = list(table.conflicts)
            table.conflicts = {}
            table.labels.clear()
            table.colors.clear()
            table.value_indices.clear()
            table.choice_sources.clear()
            grid.BeginBatch()
            try:
                for position in old_positions:
                    mapped = table.grid_position(*position)
                    if mapped is not None:
                        grid.SetAttr(*mapped, table.build_attr(*mapped))
            finally:
                grid.EndBatch()
            grid.ForceRefresh()
        self.status.SetLabel(tr('merge_recompare'))
        self.update_buttons()

    def commit_pending_edits(self):
        for i in range(self.notebook.GetPageCount()):
            grid = getattr(self.notebook.GetPage(i), "grid", None)
            if isinstance(grid, gridlib.Grid) and grid.IsCellEditControlEnabled():
                grid.SaveEditControlValue()
                grid.DisableCellEditControl()

    def on_save(self, event):
        self.commit_pending_edits()
        if not self.compared or any(c.selected is None for c in self.conflicts):
            self.update_conflicts()
            return
        self.cancel_button.Disable()
        self.saving = True
        backup = self.backup_checkbox.GetValue()
        change_color = self.selected_change_color()
        def done(result):
            if self.finish_save():
                return
            self.show_selected_book()
            self.status.SetLabel(tr('merge_saved'))
        def save():
            try:
                engine.save_merge(self.base, self.conflicts, backup_original=backup,
                                  change_color=change_color)
            except Exception:
                wx.CallAfter(self.save_failed)
                raise
        self.run_job(save, done)

    def finish_save(self):
        self.saving = False
        self.saved_changes = True
        self.cancel_button.Enable()
        self.conflicts = []
        self.compared = False
        if self.close_after_save:
            self.close_after_save = False
            self.close_dialog()
            return True
        return False

    def save_failed(self):
        if not self.disposed:
            self.saving = False
            self.close_after_save = False
            self.cancel_button.Enable()

    def resume_close(self):
        if not self.disposed and self.cancel_pending and not self.busy:
            self.cancel_pending = False
            self.cancel_button.Enable()
            self.on_cancel(None)

    def close_dialog(self):
        if self.IsModal():
            self.EndModal(wx.ID_CANCEL)
        else:
            self.dispose()

    def on_cancel(self, event):
        if self.disposed:
            return
        if hasattr(event, 'Veto') and event.CanVeto():
            event.Veto()
        if getattr(self, 'saving', False):
            return
        if self.busy:
            self.cancel_pending = True
            self.status.SetLabel(tr('merge_cancelling'))
            self.cancel_button.Disable()
            return
        self.commit_pending_edits()
        if self.compared and any(c.selected != 0 for c in self.conflicts):
            prompt = wx.MessageDialog(
                self, tr('confirm_save_selected_file') + '\n\n' + self.path,
                tr('merge_documents'), wx.YES_NO | wx.CANCEL | wx.CANCEL_DEFAULT | wx.ICON_WARNING)
            prompt.SetYesNoCancelLabels(tr('merge_save'), tr('confirm_no'), tr('cancel_button'))
            try:
                answer = prompt.ShowModal()
            finally:
                prompt.Destroy()
            if answer == wx.ID_YES:
                if any(c.selected is None for c in self.conflicts):
                    wx.MessageBox(tr('merge_unresolved'), tr('merge_documents'), wx.OK | wx.ICON_INFORMATION, self)
                    return
                self.close_after_save = True
                try:
                    self.on_save(None)
                finally:
                    if not getattr(self, 'saving', False):
                        self.close_after_save = False
                return
            if answer != wx.ID_NO:
                return
        self.close_dialog()

    def dispose(self):
        if self.disposed:
            return
        self.disposed = True
        if getattr(self.owner, '_merge_dialog', None) is self:
            self.owner._merge_dialog = None
        self.progress_timer.Stop()
        self.wait_cursor = None
        self.executor.shutdown(wait=False)
        self.Destroy()
        try:
            self.preview_dir.cleanup()
        except OSError:
            pass
        wx.CallAfter(self.refresh_owner)

    def refresh_owner(self):
        owner = self.owner
        if not owner or getattr(owner, '_closing_workspace', False):
            return
        if self.saved_changes:
            owner.refresh_current_folder_preserving_context()
        # The user may have selected another file while this form was open.
        current_path = getattr(owner, 'current_preview_path', None)
        if current_path and engine.source_key(current_path) == engine.source_key(self.path):
            from controls.file_preview import show_file_preview
            show_file_preview(owner, current_path, force_refresh=True)


class WordMergeDialog(MergeDialog):
    """The same form, with the original Word document as its review surface."""
    instructions_key = 'word_merge_instructions'
    ready_key = 'word_merge_ready'

    def load_initial(self):
        with word_merge.word_app() as app:
            document = word_merge.read_document(app, self.path)
            app = None
        return document, self.render_word(document)

    def render_word(self, document, conflicts=(), token=''):
        return word_merge.render_preview(
            document, os.path.join(self.preview_dir.name, uuid.uuid4().hex),
            conflicts, self.source_colors,
            {'choose': tr('merge_choose'), 'empty': tr('merge_empty'), 'keep': tr('merge_keep')}, token)

    def loaded(self, result):
        super().loaded(result)
        self.status.SetLabel(tr(self.ready_key))

    def ensure_selected_sheet(self):
        pass

    def show_book(self, book, target=False):
        if self.base is None:
            return
        if not hasattr(self, 'word_view'):
            self.word_view = create_webview(html2, self.notebook, backend=html2.WebViewBackendEdge)
            if not self.word_view.AddScriptMessageHandler('wordMerge'):
                raise word_merge.MergeError('word_merge_preview_failed')
            self.word_view.Bind(html2.EVT_WEBVIEW_SCRIPT_MESSAGE_RECEIVED, self.on_word_choice)
            self.word_view.Bind(html2.EVT_WEBVIEW_NAVIGATING, self.on_word_navigation)
            self.word_view.Bind(html2.EVT_WEBVIEW_LOADED, self.on_word_loaded)
            self.word_view.Bind(html2.EVT_WEBVIEW_ERROR, self.on_word_error)
            self.word_view.Bind(html2.EVT_WEBVIEW_NEWWINDOW, lambda event: event.Veto())
            self.notebook.AddPage(self.word_view, tr('merge_preview'), select=True)
        path = self.review_path if self.compared else self.preview_paths.get(self.base.digest)
        if path:
            self.word_preview_ready = False
            self.word_preview_url = Path(path).as_uri()
            self.word_view.LoadURL(self.word_preview_url)

    def update_buttons(self):
        super().update_buttons()
        if not getattr(self, 'word_preview_ready', False):
            self.save_button.Disable()

    def on_word_loaded(self, event):
        if self.disposed:
            return
        if event.GetURL().split('#', 1)[0] == self.word_preview_url:
            self.word_preview_ready = True
            self.update_buttons()

    def on_word_error(self, event):
        if self.disposed:
            return
        self.word_preview_ready = False
        self.status.SetLabel(tr('word_merge_preview_failed') + ' ' + event.GetString())
        self.update_buttons()

    def on_word_navigation(self, event):
        if event.GetURL().split('#', 1)[0] != self.word_preview_url:
            event.Veto()

    def on_word_choice(self, event):
        if self.disposed or self.busy or not self.compared:
            return
        try:
            message = json.loads(event.GetString())
            if not isinstance(message, dict) or message.get('token') != self.review_token:
                return
            index, choice = message['conflict'], message['choice']
            if type(index) is not int or type(choice) is not int:
                return
            if not 0 <= index < len(self.conflicts):
                return
            conflict = self.conflicts[index]
            if not 0 <= choice < len(conflict.values):
                return
        except (ValueError, KeyError, TypeError):
            return
        conflict.selected = choice
        self.update_conflicts()

    def on_search(self, event):
        self.on_checks(None)
        self.matches = []
        self.files.Clear()
        self.source_colors = {}
        def task():
            result = word_merge.search_documents(self.path, self.base, self.book_cache, self.report_progress)
            base = result[0]
            preview = self.preview_paths.get(base.digest) or self.render_word(base)
            return result, preview
        def done(result):
            (self.base, self.matches, skipped), preview = result
            self.matches.sort(key=lambda match: os.path.basename(match[0].path).casefold())
            self.preview_paths[self.base.digest] = preview
            for document, score in self.matches:
                index = self.files.Append(os.path.basename(document.path))
                self.files.Check(index, True)
                color = file_color(index)
                self.source_colors[engine.source_key(document.path)] = color
                self.files.SetItemTextColour(index, wx.Colour(*color))
            self.show_selected_book()
            self.status.SetLabel(tr('merge_found', count=len(self.matches), skipped=len(skipped)))
            if skipped:
                wx.MessageBox('\n'.join(os.path.basename(p) + ': ' + error_text(e) for p, e in skipped),
                              tr('merge_documents'), wx.OK | wx.ICON_INFORMATION, self)
        self.run_job(task, done, tr('merge_search'))

    def on_compare(self, event):
        self.on_checks(None)
        documents = [self.matches[i][0] for i in self.files.GetCheckedItems()]
        token = uuid.uuid4().hex
        def task():
            for document in [self.base] + documents:
                if engine.fingerprint(document.path) != document.digest:
                    raise engine.MergeError('merge_changed', path=document.path)
            conflicts, skipped = word_merge.conflicts_for(self.base, documents)
            preview = self.render_word(self.base, conflicts, token)
            return conflicts, skipped, preview
        def done(result):
            self.conflicts, skipped, self.review_path = result
            self.review_token = token
            self.compared = True
            self.show_selected_book()
            self.update_conflicts()
            if skipped:
                wx.MessageBox(tr('word_merge_skipped') + '\n' + '\n'.join(
                    os.path.basename(path) + ': ' + str(count) for path, count in skipped),
                    tr('merge_documents'), wx.OK | wx.ICON_INFORMATION, self)
        self.run_job(task, done)

    def on_checks(self, event):
        had_comparison = self.compared
        self.compared = False
        self.conflicts = []
        if had_comparison:
            self.show_selected_book()
        self.status.SetLabel(tr('merge_recompare'))
        self.update_buttons()

    def update_conflicts(self):
        if not self.disposed:
            self.status.SetLabel(tr('word_merge_conflicts', total=len(self.conflicts),
                                    count=sum(c.selected is None for c in self.conflicts)))
            self.update_buttons()

    def on_save(self, event):
        if (not getattr(self, 'word_preview_ready', False) or not self.compared
                or any(c.selected is None for c in self.conflicts)):
            self.update_conflicts()
            return
        backup = self.backup_checkbox.GetValue()
        change_color = self.selected_change_color()
        self.saving = True
        self.cancel_button.Disable()
        def task():
            try:
                word_merge.save_merge(self.base, self.conflicts, backup_original=backup,
                                      change_color=change_color)
            except Exception:
                wx.CallAfter(self.save_failed)
                raise
        def done(result):
            if self.finish_save():
                return
            # Reload after saving so subsequent comparisons use new text offsets.
            self.run_job(self.load_initial, refreshed, tr('merge_initializing'))
        def refreshed(result):
            self.loaded(result)
            self.status.SetLabel(tr('merge_saved'))
        self.run_job(task, done)


def show_merge_dialog(owner, path):
    if not (engine.is_excel(path) or word_merge.is_word(path)):
        return
    existing = getattr(owner, '_merge_dialog', None)
    if existing and not existing.disposed:
        existing.Show()
        existing.Raise()
        return existing
    dialog = (WordMergeDialog if word_merge.is_word(path) else MergeDialog)(owner, path)
    owner._merge_dialog = dialog
    dialog.Show()
    return dialog
