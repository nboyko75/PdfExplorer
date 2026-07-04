import wx

from localization import tr
from pdf_utils import get_pdf_page_count, is_pdf_file, move_pdf_page


class PdfPageDropTarget(wx.DropTarget):
    def __init__(self, owner, page_index, page_panel, insert_before=None):
        super().__init__(wx.TextDataObject())
        self.owner = owner
        self.page_index = page_index
        self.page_panel = page_panel
        self.insert_before = insert_before
        self.data = wx.TextDataObject()
        self.SetDataObject(self.data)

    def OnEnter(self, x, y, d):
        try:
            if self.owner and self.page_panel:
                self.owner.show_drag_overlay(self.page_index, self.page_panel, x, y)
                self.owner.show_drop_frame(self.page_index, self.page_panel, x, y)
        except Exception:
            pass
        return wx.DragCopy

    def OnDragOver(self, x, y, d):
        try:
            if self.owner and self.page_panel:
                self.owner.show_drag_overlay(self.page_index, self.page_panel, x, y)
                self.owner.show_drop_frame(self.page_index, self.page_panel, x, y)
        except Exception:
            pass
        return wx.DragCopy

    def OnLeave(self):
        try:
            self.owner.hide_drag_overlay()
            self.owner.hide_drop_frame()
        except Exception:
            pass
        self.page_panel = None

    def OnDrop(self, x, y):
        try:
            self.owner.hide_drag_overlay()
            self.owner.hide_drop_frame()
        except Exception:
            pass
        return True

    def OnData(self, x, y, default):
        try:
            self.GetData()
            if self.insert_before is not None:
                insert_before = self.insert_before
            else:
                try:
                    size = self.page_panel.GetSize()
                    insert_before = y < (size.y // 2)
                except Exception:
                    insert_before = True

            if self.owner:
                self.owner.handle_pdf_page_drop(self.page_index, self.data.GetText(), insert_before=insert_before)
        except Exception:
            pass
        return wx.DragCopy


def create_drag_overlay(owner):
    if owner.drag_overlay is None:
        owner.drag_overlay = wx.PopupWindow(owner, style=wx.BORDER_SIMPLE)
        panel = wx.Panel(owner.drag_overlay)
        panel.SetBackgroundColour(wx.Colour(255, 255, 255))
        owner.drag_overlay_text = wx.StaticText(panel, label="")
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(owner.drag_overlay_text, 0, wx.ALL, 5)
        panel.SetSizer(sizer)
        panel.Fit()
        owner.drag_overlay.SetSize(panel.GetSize())
    return owner.drag_overlay


def show_drag_overlay(owner, page_index, page_panel, x, y):
    overlay = create_drag_overlay(owner)
    owner.drag_overlay_text.SetLabel(tr("drop_overlay_label", page_index=page_index + 1))
    overlay.Fit()
    position = page_panel.ClientToScreen(wx.Point(x, y))
    overlay.Move(position + wx.Point(16, 16))
    overlay.Show(True)
    overlay.Raise()


def hide_drag_overlay(owner):
    if owner.drag_overlay is not None:
        owner.drag_overlay.Hide()
    if getattr(owner, "drop_frame", None) is not None:
        owner.drop_frame.Hide()
    try:
        if getattr(owner, "_highlighted_panel", None) is not None:
            panel = owner._highlighted_panel
            if getattr(panel, "_orig_bg", None) is not None:
                panel.SetBackgroundColour(panel._orig_bg)
            panel.Refresh()
            owner._highlighted_panel = None
    except Exception:
        pass


def create_drop_frame(owner):
    if getattr(owner, "drop_frame", None) is None:
        owner.drop_frame = wx.PopupWindow(owner, style=wx.BORDER_NONE)
        panel = wx.Panel(owner.drop_frame)
        panel.SetBackgroundColour(wx.Colour(0, 120, 215))
        owner.drop_frame.SetBackgroundColour(wx.Colour(0, 120, 215))
        panel.SetSize((10, 4))
    return owner.drop_frame


def show_drop_frame(owner, page_index, page_panel, x, y):
    frame = create_drop_frame(owner)
    size = page_panel.GetSize()
    half_y = size.y // 2
    insert_before = y < half_y
    width = max(20, size.x - 6)
    height = 4
    frame.SetSize((width, height))

    if insert_before:
        screen_pos = page_panel.ClientToScreen(wx.Point(3, 0))
        frame.Move(screen_pos + wx.Point(0, -2))
        overlay = create_drag_overlay(owner)
        owner.drag_overlay_text.SetLabel(tr("insert_before"))
        overlay.Fit()
    else:
        screen_pos = page_panel.ClientToScreen(wx.Point(3, size.y))
        frame.Move(screen_pos + wx.Point(0, -2))
        overlay = create_drag_overlay(owner)
        owner.drag_overlay_text.SetLabel(tr("insert_after"))
        overlay.Fit()

    try:
        if getattr(page_panel, "_orig_bg", None) is None:
            page_panel._orig_bg = page_panel.GetBackgroundColour()
        page_panel.SetBackgroundColour(wx.Colour(230, 245, 255))
        page_panel.Refresh()
        owner._highlighted_panel = page_panel
    except Exception:
        pass
    frame.Show(True)


def hide_drop_frame(owner):
    if getattr(owner, "drop_frame", None) is not None:
        owner.drop_frame.Hide()


def on_pdf_page_drag_motion(owner, event):
    if not event.Dragging() or not event.LeftIsDown():
        return

    page_panel = owner.get_pdf_page_panel_from_event(event)
    if page_panel is None or page_panel is not getattr(owner, "_pdf_drag_start_panel", None):
        return

    start_pos = getattr(owner, "_pdf_drag_start_pos", None)
    if start_pos is None:
        return

    current_pos = event.GetPosition()
    if abs(current_pos.x - start_pos.x) < 5 and abs(current_pos.y - start_pos.y) < 5:
        return

    owner._pdf_drag_start_pos = None
    start_pdf_page_drag(owner, page_panel)


def start_pdf_page_drag(owner, page_panel):
    page_index = getattr(page_panel, "page_index", None)
    if page_index is None:
        return

    payload = f"{owner.current_pdf_path}\n{page_index}"
    data = wx.TextDataObject(payload)
    source = wx.DropSource(page_panel)
    source.SetData(data)
    source.DoDragDrop(wx.Drag_AllowMove)


def handle_pdf_page_drop(owner, target_index, payload, insert_before=True):
    try:
        with owner.busy_cursor():
            source_path, source_index = payload.split("\n", 1)
            source_index = int(source_index)
            if not is_pdf_file(source_path) or not is_pdf_file(owner.current_pdf_path):
                return
            if source_path != owner.current_pdf_path:
                return

            try:
                page_count = get_pdf_page_count(owner.current_pdf_path)
            except Exception:
                page_count = None

            if insert_before:
                to_index = target_index
            else:
                to_index = target_index + 1

            if page_count is not None:
                to_index = max(0, min(to_index, page_count - 1))

            move_pdf_page(owner.current_pdf_path, source_index, to_index)
            if source_index < to_index:
                result_index = to_index - 1
            else:
                result_index = to_index

            try:
                owner.undo_stack.append((owner.current_pdf_path, source_index, result_index))
            except Exception:
                pass
            owner.show_pdf_feed(owner.current_pdf_path)
    except Exception as exc:
        wx.MessageBox(
            tr("unable_move_pdf_page", exc=exc),
            tr("page_move_error_title"),
            style=wx.OK | wx.ICON_ERROR,
        )
