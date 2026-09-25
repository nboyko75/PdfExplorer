"""Excel merge review dialog. All workbook I/O runs outside the GUI thread."""
import os
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


class MergeDialog(wx.Dialog):
    def __init__(self, owner, path):
        super().__init__(owner, title=tr('merge_documents'), size=(1150, 750),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.path = os.path.abspath(path)
        self.preview_dir = tempfile.TemporaryDirectory(prefix="docexplorer_merge_")
        self.preview_paths = {}
        self.base = None
        self.matches = []
        self.conflicts = []
        self.compared = False
        self.busy = False
        self.cancel_pending = False
        self.disposed = False
        self.executor = ThreadPoolExecutor(max_workers=1)
        outer = wx.BoxSizer(wx.VERTICAL)
        title = wx.StaticText(self, label=self.path.replace("&", "&&"))
        title.SetToolTip(self.path)
        header = wx.BoxSizer(wx.HORIZONTAL)
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
        self.target_button = wx.Button(left, label=tr('merge_target'))
        left_sizer.Add(self.target_button, 0, wx.EXPAND | wx.BOTTOM, 5)
        self.files = wx.CheckListBox(left)
        left_sizer.Add(self.files, 1, wx.EXPAND)
        left.SetSizer(left_sizer)
        right = wx.Panel(splitter)
        right_sizer = wx.BoxSizer(wx.VERTICAL)
        self.preview_label = wx.StaticText(right, label='')
        right_sizer.Add(self.preview_label, 0, wx.EXPAND | wx.ALL, 5)
        self.notebook = wx.Notebook(right)
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
        self.cancel_button = wx.Button(self, wx.ID_CANCEL, tr('cancel_button'))
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
        self.files.Bind(wx.EVT_LISTBOX, self.on_select)
        self.files.Bind(wx.EVT_CHECKLISTBOX, self.on_checks)
        self.target_button.Bind(wx.EVT_BUTTON, lambda event: self.select_preview(self.base, True))
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
        try:
            html = engine.render_preview(self.path, os.path.join(self.preview_dir.name, book.digest))
        except Exception:
            html = None  # The cell preview still works if HTML export is unavailable.
        return book, html

    def loaded(self, result):
        book, html = result
        if html:
            self.preview_paths[book.digest] = html
        self.base = book
        self.show_book(book, True)
        self.status.SetLabel(tr('merge_ready'))

    def run_job(self, task, done):
        self.busy = True
        self.status.SetLabel(tr('merge_working'))
        self.update_buttons()
        future = self.executor.submit(task)
        def finished(future):
            if not self.disposed:
                wx.CallAfter(self.finish_job, future, done)
        future.add_done_callback(finished)

    def finish_job(self, future, done):
        if self.disposed:
            return
        self.busy = False
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
        self.target_button.Enable(not self.busy and self.base is not None)
        self.notebook.Enable(not self.busy)

    def on_search(self, event):
        self.compared = False
        self.conflicts = []
        self.matches = []
        self.files.Clear()
        self.show_book(self.base, True)
        def done(result):
            self.base, self.matches, skipped = result
            for book, score in self.matches:
                index = self.files.Append(os.path.basename(book.path))
                self.files.Check(index, True)
            self.show_book(self.base, True)
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
            self.show_book(self.base, True)
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
        self.notebook.DeleteAllPages()
        self.preview_label.SetLabel(book.path.replace("&", "&&"))
        self.preview_label.SetToolTip(book.path)
        for name, sheet in book.sheets.items():
            conflicts = {(c.row, c.col): c for c in self.conflicts if target and c.sheet == name}
            grid = gridlib.Grid(self.notebook)
            differences = {(c.row, c.col) for c in self.conflicts if c.sheet == name} if self.compared else None
            table = SheetTable(sheet, conflicts, difference_positions=differences)
            grid.SetTable(table, takeOwnership=True)
            grid.SetDefaultColSize(170)
            grid.SetDefaultRowSize(25)
            for row in sheet.hidden_rows:
                if 1 <= row <= table.GetNumberRows():
                    grid.HideRow(row - 1)
            grid.Bind(gridlib.EVT_GRID_CELL_CHANGED, self.on_cell_changed)
            grid.Bind(gridlib.EVT_GRID_CELL_LEFT_CLICK, self.on_cell_click)
            self.notebook.AddPage(grid, name)
            if conflicts:
                row, col = next(iter(conflicts))
                grid.SetGridCursor(row-1, col-1)
                grid.MakeCellVisible(row-1, col-1)
        html = self.preview_paths.get(book.digest)
        if html and not self.compared and not any(s.hidden_rows for s in book.sheets.values()):
            try:
                backend = getattr(html2, 'WebViewBackendEdge', None)
                if backend and html2.WebView.IsBackendAvailable(backend):
                    view = html2.WebView.New(self.notebook, backend=backend)
                else:
                    view = html2.WebView.New(self.notebook)
                view.LoadURL(Path(html).as_uri())
                self.notebook.InsertPage(0, view, tr('merge_preview'), select=not (target and self.compared))
            except Exception:
                pass  # The cell grid remains available if no web backend is installed.
        self.Layout()

    def select_preview(self, book, target=False):
        if book is None:
            return
        if book.digest in self.preview_paths or self.compared or any(s.hidden_rows for s in book.sheets.values()):
            self.show_book(book, target)
            return
        self.show_book(book, target)
        def done(html):
            self.preview_paths[book.digest] = html
            self.show_book(book, target)
            if self.compared:
                self.update_conflicts()
            else:
                self.status.SetLabel(tr('merge_ready'))
        self.run_job(lambda: engine.render_preview(book.path, os.path.join(self.preview_dir.name, book.digest)), done)

    def on_cell_click(self, event):
        grid = event.GetEventObject()
        row, col = event.GetRow(), event.GetCol()
        event.Skip()
        if (row+1, col+1) in grid.GetTable().conflicts:
            wx.CallAfter(self.edit_cell, grid, row, col)

    def edit_cell(self, grid, row, col):
        if not self.disposed and not self.busy:
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

    def on_select(self, event):
        i = self.files.GetSelection()
        if i != wx.NOT_FOUND:
            self.select_preview(self.matches[i][0])

    def on_checks(self, event):
        self.compared = False
        self.conflicts = []
        self.show_book(self.base, True)
        self.status.SetLabel(tr('merge_recompare'))
        self.update_buttons()

    def on_save(self, event):
        for i in range(self.notebook.GetPageCount()):
            grid = self.notebook.GetPage(i)
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
