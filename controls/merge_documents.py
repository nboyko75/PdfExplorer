"""Excel merge review dialog. All workbook I/O runs outside the GUI thread."""
import os
import colorsys
import tempfile
from pathlib import Path
import wx.html2 as html2
from concurrent.futures import ThreadPoolExecutor
import wx
import wx.grid as gridlib
from localization import tr
from file_operations import excel_merge as engine
from common.sheet_table import SheetTable


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
        self.Bind(wx.EVT_KEY_DOWN, self.on_key)
        self.Bind(wx.EVT_SIZE, self.on_size)

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
        index, flags = self.HitTest(event.GetPosition())
        if index != wx.NOT_FOUND:
            self.SetFocus()
            self.Select(index)
            self.Focus(index)
            self.CheckItem(index, not self.IsItemChecked(index))
            self.changed(None)
            return  # Consume the native checkbox click to avoid a second toggle.
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
    def __init__(self, owner, path):
        super().__init__(owner, title=tr('merge_documents'), size=(1150, 750),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.path = os.path.abspath(path)
        self.preview_dir = tempfile.TemporaryDirectory(prefix="docexplorer_merge_")
        self.preview_paths = {}
        self.base = None
        self.matches = []
        self.source_colors = {}
        self.conflicts = []
        self.compared = False
        self.busy = False
        self.cancel_pending = False
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
        info.SetToolTip(tr('merge_instructions'))
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
        right.SetSizer(right_sizer)
        splitter.SplitVertically(left, right, 250)
        splitter.SetMinimumPaneSize(160)
        outer.Add(splitter, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        self.status = wx.StaticText(self, label=tr('merge_ready'))
        outer.Add(self.status, 0, wx.EXPAND | wx.ALL, 10)
        bar = wx.BoxSizer(wx.HORIZONTAL)
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
        self.run_job(self.load_initial, lambda book: self.loaded(book))

    def show_instructions(self, event):
        popup = wx.PopupTransientWindow(self, wx.BORDER_SIMPLE)
        panel = wx.Panel(popup)
        label = wx.StaticText(panel, label=tr('merge_instructions'))
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
            book = engine.read_book(app, self.path)
        return book, None

    def loaded(self, result):
        book, html = result
        if html:
            self.preview_paths[book.digest] = html
        self.base = book
        self.show_book(book, True)
        self.status.SetLabel(tr('merge_ready'))

    def run_job(self, task, done):
        self.busy = True
        self.wait_cursor = wx.BusyCursor()
        self.status.SetLabel(tr('merge_working'))
        self.update_buttons()
        try:
            future = self.executor.submit(task)
        except Exception:
            self.busy = False
            self.wait_cursor = None
            self.update_buttons()
            raise
        def finished(future):
            if not self.disposed:
                wx.CallAfter(self.finish_job, future, done)
        future.add_done_callback(finished)

    def finish_job(self, future, done):
        if self.disposed:
            return
        self.busy = False
        self.wait_cursor = None
        if self.cancel_pending:
            self.EndModal(wx.ID_CANCEL)
            return
        try:
            result = future.result()
            done(result)
        except Exception as exc:
            self.status.SetLabel(tr('merge_failed'))
            wx.MessageBox(error_text(exc), tr('merge_documents'), wx.OK | wx.ICON_ERROR, self)
        self.update_buttons()

    def update_buttons(self):
        self.search_button.Enable(not self.busy and self.base is not None)
        self.compare_button.Enable(not self.busy and bool(self.matches) and bool(self.files.GetCheckedItems()))
        self.save_button.Enable(not self.busy and self.compared and all(c.selected is not None for c in self.conflicts))
        self.files.Enable(not self.busy)
        self.check_all.Enable(not self.busy)
        self.uncheck_all.Enable(not self.busy)
        self.notebook.Enable(not self.busy)

    def on_search(self, event):
        self.compared = False
        self.conflicts = []
        self.matches = []
        self.files.Clear()
        self.source_colors = {}
        self.display_book = None
        self.notebook.DeleteAllPages()
        def done(result):
            self.base, self.matches, skipped = result
            for book, score in self.matches:
                index = self.files.Append(os.path.basename(book.path))
                self.files.Check(index, True)
                color = file_color(index)
                self.source_colors[os.path.basename(book.path)] = color
                self.files.SetItemTextColour(index, wx.Colour(*color))
            if self.matches:
                self.files.Select(0)
                self.files.Focus(0)
            self.show_selected_book()
            self.status.SetLabel(tr('merge_found', count=len(self.matches), skipped=len(skipped)))
            if skipped:
                wx.MessageBox('\n'.join(os.path.basename(p) + ': ' + error_text(e) for p, e in skipped),
                              tr('merge_documents'), wx.OK | wx.ICON_INFORMATION, self)
        self.run_job(lambda: engine.search_books(self.path), done)

    def on_compare(self, event):
        books = [self.matches[i][0] for i in self.files.GetCheckedItems()]
        def task():
            for book in [self.base] + books:
                if engine.fingerprint(book.path) != book.digest:
                    raise engine.MergeError('merge_changed', path=book.path)
            return engine.conflicts_for(self.base, books)
        def done(conflicts):
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
        if book is None:
            return
        self.building_pages = True
        try:
            self.display_book = book
            self.notebook.DeleteAllPages()
            for name in book.sheets:
                page = wx.Panel(self.notebook)
                page.sheet_name = name
                page.grid = None
                self.notebook.AddPage(page, name)
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
        table = SheetTable(sheet, conflicts, source_colors=self.source_colors)
        grid.SetTable(table, takeOwnership=True)
        grid.BeginBatch()
        font = wx.Font(11, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL,
                       wx.FONTWEIGHT_NORMAL, faceName="Calibri")
        grid.SetDefaultCellFont(font)
        grid.SetLabelFont(font)
        grid.SetDefaultCellBackgroundColour(wx.Colour(255, 255, 255))
        grid.SetDefaultCellTextColour(wx.Colour(32, 32, 32))
        grid.SetDefaultCellAlignment(wx.ALIGN_LEFT, wx.ALIGN_CENTER_VERTICAL)
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
        for row, col in set(sheet.styles) | set(sheet.cells) | set(conflicts):
            if row not in sheet.hidden_rows and col not in sheet.hidden_cols:
                grid.SetAttr(row - 1, col - 1, table.build_attr(row - 1, col - 1))
        dpi = grid.GetDPI()
        for row, points in sheet.row_heights.items():
            grid.SetRowSize(row - 1, max(1, round(points * dpi.height / 72)))
        for col, points in sheet.col_widths.items():
            grid.SetColSize(col - 1, max(1, round(points * dpi.width / 72)))
        for row in sheet.hidden_rows:
            if 1 <= row <= table.GetNumberRows():
                grid.HideRow(row - 1)
        for col in sheet.hidden_cols:
            if 1 <= col <= table.GetNumberCols():
                grid.HideCol(col - 1)
        grid.Bind(gridlib.EVT_GRID_CELL_CHANGED, self.on_cell_changed)
        grid.Bind(gridlib.EVT_GRID_CELL_LEFT_CLICK, self.on_cell_click)
        grid.EndBatch()
        page.grid = grid
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(grid, 1, wx.EXPAND)
        page.SetSizer(sizer)
        page.Layout()
        if conflicts:
            row, col = next(iter(conflicts))
            grid.SetGridCursor(row-1, col-1)
            grid.MakeCellVisible(row-1, col-1)

    def select_preview(self, book, target=False):
        if book is not None:
            self.show_book(book, target)

    def on_cell_click(self, event):
        grid = event.GetEventObject()
        row, col = event.GetRow(), event.GetCol()
        if (row+1, col+1) in grid.GetTable().conflicts:
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
        index = self.files.GetSelection()
        if 0 <= index < len(self.matches):
            self.show_book(self.matches[index][0])
        else:
            self.display_book = None
            self.notebook.DeleteAllPages()

    def on_select(self, event):
        if not self.busy:
            self.show_selected_book()

    def set_all_checks(self, checked):
        for index in range(self.files.GetItemCount()):
            self.files.Check(index, checked)
        self.check_all.SetValue(True)
        self.uncheck_all.SetValue(False)
        self.on_checks(None)

    def on_checks(self, event):
        self.compared = False
        self.conflicts = []
        self.show_selected_book()
        self.status.SetLabel(tr('merge_recompare'))
        self.update_buttons()

    def on_save(self, event):
        for i in range(self.notebook.GetPageCount()):
            grid = getattr(self.notebook.GetPage(i), "grid", None)
            if isinstance(grid, gridlib.Grid) and grid.IsCellEditControlEnabled():
                grid.SaveEditControlValue()
                grid.DisableCellEditControl()
        if not self.compared or any(c.selected is None for c in self.conflicts):
            self.update_conflicts()
            return
        self.cancel_button.Disable()
        self.saving = True
        def done(result):
            self.saving = False
            self.EndModal(wx.ID_OK)
        def save():
            try:
                engine.save_merge(self.base, self.conflicts)
            except Exception:
                wx.CallAfter(self.save_failed)
                raise
        self.run_job(save, done)

    def save_failed(self):
        if not self.disposed:
            self.saving = False
            self.cancel_button.Enable()

    def on_cancel(self, event):
        if getattr(self, 'saving', False):
            if hasattr(event, 'Veto'):
                event.Veto()
            return
        if self.busy:
            self.cancel_pending = True
            self.status.SetLabel(tr('merge_cancelling'))
            self.cancel_button.Disable()
            if hasattr(event, 'Veto'):
                event.Veto()
        else:
            self.EndModal(wx.ID_CANCEL)

    def dispose(self):
        self.disposed = True
        self.wait_cursor = None
        self.executor.shutdown(wait=False)
        self.Destroy()
        try:
            self.preview_dir.cleanup()
        except OSError:
            pass


def show_merge_dialog(owner, path):
    if not engine.is_excel(path):
        return
    dialog = MergeDialog(owner, path)
    try:
        if dialog.ShowModal() == wx.ID_OK:
            from controls.filelist import _refresh_after_fs_change
            _refresh_after_fs_change(owner, affected_dirs=[os.path.dirname(path)], preferred_preview_path=path)
    finally:
        dialog.dispose()
