import os

import wx

from localization import tr
from file_operations.pdf_utils import ajust_page_width, discard_pdf_changes, get_pdf_page_previews, has_unsaved_pdf_changes, is_pdf_file, optimize_pdf, remove_pdf_page, rotate_pdf, rotate_pdf_page, save_pdf
import file_operations.image_utils as image_utils
import file_operations.pdf_dragdrop as pdf_dragdrop


def build_file_preview_pane(owner, file_splitter):
    """Create and configure the file preview pane UI."""
    owner.filePreview = wx.Panel(file_splitter, style=wx.BORDER_SUNKEN)
    owner.preview_toolbar = wx.BoxSizer(wx.HORIZONTAL)

    preview_icon_size = (16, 16)
    preview_button_size = (24, 24)
    icon_manager = owner.icon_manager
    owner.filePreview.icon_manager = icon_manager

    owner.preview_edit_btn = image_utils.create_bitmap_button(owner.filePreview, wx.ART_FIND, tr("preview_edit_button"), icon_size=preview_icon_size, button_size=preview_button_size)
    owner.preview_save_btn = image_utils.create_bitmap_button2(owner.filePreview, icon_manager, "save", tr("preview_save_button"), icon_size=preview_icon_size, button_size=preview_button_size)
    owner.preview_delete_btn = image_utils.create_bitmap_button(owner.filePreview, wx.ART_DELETE, tr("preview_delete_button"), icon_size=preview_icon_size, button_size=preview_button_size)
    owner.preview_zoom_out_btn = image_utils.create_bitmap_button(owner.filePreview, wx.ART_MINUS, tr("preview_zoom_out_button"), icon_size=preview_icon_size, button_size=preview_button_size)
    owner.preview_zoom_in_btn = image_utils.create_bitmap_button(owner.filePreview, wx.ART_PLUS, tr("preview_zoom_in_button"), icon_size=preview_icon_size, button_size=preview_button_size)
    owner.preview_rotate_all_left_btn = image_utils.create_bitmap_button(owner.filePreview, wx.ART_UNDO, tr("preview_rotate_all_left_button"), icon_size=preview_icon_size, button_size=preview_button_size)
    owner.preview_rotate_left_btn = image_utils.create_bitmap_button(owner.filePreview, wx.ART_UNDO, tr("preview_rotate_left_button"), icon_size=preview_icon_size, button_size=preview_button_size)
    owner.preview_rotate_right_btn = image_utils.create_bitmap_button(owner.filePreview, wx.ART_REDO, tr("preview_rotate_right_button"), icon_size=preview_icon_size, button_size=preview_button_size)
    owner.preview_rotate_all_right_btn = image_utils.create_bitmap_button(owner.filePreview, wx.ART_REDO, tr("preview_rotate_all_right_button"), icon_size=preview_icon_size, button_size=preview_button_size)
    owner.preview_remove_page_btn = image_utils.create_bitmap_button2(owner.filePreview, icon_manager, "delete", tr("preview_remove_page_button"), icon_size=preview_icon_size, button_size=preview_button_size)
    owner.preview_optimize_btn = image_utils.create_bitmap_button2(owner.filePreview, icon_manager, "ok", tr("preview_optimize_button"), icon_size=preview_icon_size, button_size=preview_button_size)
    owner.preview_ajust_page_width_btn = image_utils.create_bitmap_button(owner.filePreview, wx.ART_REPORT_VIEW, tr("preview_ajust_page_width_button"), icon_size=preview_icon_size, button_size=preview_button_size)

    joined_toolbar_undo = image_utils.create_joined_art_bitmap(wx.ART_UNDO, client=wx.ART_TOOLBAR, size=(16, 16))
    if joined_toolbar_undo.IsOk():
        owner.preview_rotate_all_left_btn.SetBitmapLabel(joined_toolbar_undo)

    joined_toolbar_redo = image_utils.create_joined_art_bitmap(wx.ART_REDO, client=wx.ART_TOOLBAR, size=(16, 16))
    if joined_toolbar_redo.IsOk():
        owner.preview_rotate_all_right_btn.SetBitmapLabel(joined_toolbar_redo)

    owner.preview_toolbar.Add(owner.preview_edit_btn, 0, wx.RIGHT, 5)
    owner.preview_toolbar.Add(owner.preview_save_btn, 0, wx.RIGHT, 5)
    owner.preview_toolbar.Add(owner.preview_delete_btn, 0, wx.RIGHT, 15)
    owner.preview_toolbar.Add(owner.preview_zoom_out_btn, 0, wx.RIGHT, 5)
    owner.preview_toolbar.Add(owner.preview_zoom_in_btn, 0, wx.RIGHT, 5)
    owner.preview_toolbar.Add(owner.preview_rotate_all_left_btn, 0, wx.RIGHT, 5)
    owner.preview_toolbar.Add(owner.preview_rotate_left_btn, 0, wx.RIGHT, 5)
    owner.preview_toolbar.Add(owner.preview_rotate_right_btn, 0, wx.RIGHT, 5)
    owner.preview_toolbar.Add(owner.preview_rotate_all_right_btn, 0, wx.RIGHT, 5)
    owner.preview_toolbar.Add(owner.preview_remove_page_btn, 0, wx.RIGHT, 15)
    owner.preview_toolbar.Add(owner.preview_optimize_btn, 0, wx.RIGHT, 5)
    owner.preview_toolbar.Add(owner.preview_ajust_page_width_btn, 0)

    owner.preview_save_btn.Enable(False)
    owner.preview_rotate_left_btn.Enable(False)
    owner.preview_rotate_right_btn.Enable(False)
    owner.preview_remove_page_btn.Enable(False)

    owner.preview_text = wx.TextCtrl(
        owner.filePreview,
        style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL | wx.VSCROLL,
    )
    owner.preview_text.SetValue("")
    owner.preview_text.Hide()
    owner.preview_text.Bind(wx.EVT_CONTEXT_MENU, on_preview_right_click)

    owner.pdf_pages_panel = wx.ScrolledWindow(owner.filePreview, style=wx.HSCROLL | wx.VSCROLL)
    owner.pdf_pages_panel.SetScrollRate(10, 0)
    owner.pdf_pages_panel.Hide()
    owner.pdf_pages_panel.Bind(wx.EVT_CONTEXT_MENU, on_preview_right_click)
    owner.pdf_pages_sizer = wx.BoxSizer(wx.HORIZONTAL)
    owner.pdf_pages_panel.SetSizer(owner.pdf_pages_sizer)

    owner.pdf_preview_container = wx.ScrolledWindow(owner.filePreview, style=wx.HSCROLL | wx.VSCROLL)
    owner.pdf_preview_container.Hide()
    owner.pdf_preview_container.SetScrollRate(10, 10)
    owner.pdf_preview_container.Bind(wx.EVT_CONTEXT_MENU, on_preview_right_click)

    owner.pdf_preview = wx.StaticBitmap(owner.pdf_preview_container)
    owner.pdf_preview.SetMinSize((250, 250))
    owner.pdf_preview.Bind(wx.EVT_CONTEXT_MENU, on_preview_right_click)
    owner.filePreview.Bind(wx.EVT_CONTEXT_MENU, on_preview_right_click)

    preview_sizer = wx.BoxSizer(wx.VERTICAL)
    preview_sizer.Add(owner.preview_toolbar, 0, wx.EXPAND | wx.ALL, 5)
    preview_sizer.Add(owner.preview_text, 1, wx.EXPAND | wx.ALL, 5)
    preview_sizer.Add(owner.pdf_pages_panel, 1, wx.EXPAND | wx.ALL, 5)
    preview_sizer.Add(owner.pdf_preview_container, 1, wx.EXPAND | wx.ALL, 5)
    owner.filePreview.SetSizer(preview_sizer)

    file_splitter.SplitHorizontally(owner.list, owner.filePreview, 400)


def bind_preview_events(owner):
    """Bind preview pane event handlers."""
    owner.preview_edit_btn.Bind(wx.EVT_BUTTON, on_preview_edit)
    owner.preview_save_btn.Bind(wx.EVT_BUTTON, on_preview_save)
    owner.preview_delete_btn.Bind(wx.EVT_BUTTON, on_preview_delete)
    owner.preview_zoom_in_btn.Bind(wx.EVT_BUTTON, on_preview_zoom_in)
    owner.preview_zoom_out_btn.Bind(wx.EVT_BUTTON, on_preview_zoom_out)
    owner.preview_rotate_all_left_btn.Bind(wx.EVT_BUTTON, on_preview_rotate_all_left)
    owner.preview_rotate_left_btn.Bind(wx.EVT_BUTTON, on_preview_rotate_left)
    owner.preview_rotate_right_btn.Bind(wx.EVT_BUTTON, on_preview_rotate_right)
    owner.preview_rotate_left_btn.Bind(wx.EVT_MOUSEWHEEL, on_preview_rotate_buttons_wheel)
    owner.preview_rotate_right_btn.Bind(wx.EVT_MOUSEWHEEL, on_preview_rotate_buttons_wheel)
    owner.filePreview.Bind(wx.EVT_MOUSEWHEEL, on_preview_rotate_buttons_wheel)
    owner.preview_text.Bind(wx.EVT_MOUSEWHEEL, on_preview_rotate_buttons_wheel)
    owner.pdf_pages_panel.Bind(wx.EVT_MOUSEWHEEL, on_preview_rotate_buttons_wheel)
    owner.pdf_preview_container.Bind(wx.EVT_MOUSEWHEEL, on_preview_rotate_buttons_wheel)
    owner.pdf_preview.Bind(wx.EVT_MOUSEWHEEL, on_preview_rotate_buttons_wheel)
    owner.preview_rotate_all_right_btn.Bind(wx.EVT_BUTTON, on_preview_rotate_all_right)
    owner.preview_optimize_btn.Bind(wx.EVT_BUTTON, on_preview_optimize)
    owner.preview_ajust_page_width_btn.Bind(wx.EVT_BUTTON, on_preview_ajust_page_width)
    owner.preview_remove_page_btn.Bind(wx.EVT_BUTTON, on_preview_remove_page)


def confirm_preview_change(owner, next_path):
    current_path = getattr(owner, "current_preview_path", None)
    if not is_pdf_file(current_path) or not has_unsaved_pdf_changes(current_path):
        return True

    if next_path and os.path.normpath(next_path) == os.path.normpath(current_path):
        return True

    dialog = wx.MessageDialog(
        owner,
        tr("confirm_save_selected_file"),
        tr("app_title"),
        wx.YES_NO | wx.CANCEL | wx.CANCEL_DEFAULT | wx.ICON_WARNING,
    )
    result = dialog.ShowModal()
    dialog.Destroy()

    if result == wx.ID_CANCEL:
        return False

    try:
        if result == wx.ID_YES:
            save_pdf(current_path)
        else:
            discard_pdf_changes(current_path)
    except Exception as exc:
        wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)
        return False

    return True


def restore_list_selection(owner, path):
    owner._restoring_list_selection = True
    try:
        for index in range(owner.list.GetItemCount()):
            owner.list.SetItemState(index, 0, wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED)

        if not path or os.path.dirname(path) != owner.path_box.GetValue():
            return

        target_name = os.path.basename(path)
        for index in range(owner.list.GetItemCount()):
            if owner.list.GetItemText(index) != target_name:
                continue
            owner.list.SetItemState(
                index,
                wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
                wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
            )
            owner.list.EnsureVisible(index)
            break
    finally:
        wx.CallAfter(_clear_list_selection_restore_flag, owner)


def _clear_list_selection_restore_flag(owner):
    owner._restoring_list_selection = False


def get_pdf_page_panel_from_event(owner, event):
    obj = event.GetEventObject()
    while obj is not None and not hasattr(obj, "page_index"):
        obj = obj.GetParent()
    return obj


def get_selected_pdf_page_index(owner):
    if owner.selected_pdf_page_panel is None:
        return None
    return getattr(owner.selected_pdf_page_panel, "page_index", None)


def update_rotate_page_buttons_state(owner):
    can_select_pdf_page = (
        is_pdf_file(owner.current_preview_path)
        and get_selected_pdf_page_index(owner) is not None
    )
    can_rotate_selected_page = can_select_pdf_page
    can_rotate_image = image_utils.can_preview_image(owner.current_preview_path)
    can_rotate = can_rotate_selected_page or can_rotate_image
    owner.preview_rotate_left_btn.Enable(can_rotate)
    owner.preview_rotate_right_btn.Enable(can_rotate)
    owner.preview_remove_page_btn.Enable(can_select_pdf_page)


def update_pdf_save_button_state(owner):
    can_save = is_pdf_file(owner.current_preview_path) and has_unsaved_pdf_changes(owner.current_preview_path)
    owner.preview_save_btn.Enable(can_save)


def update_preview_toolbar_visibility(owner, is_pdf=False, is_image=False):
    show_pdf_only = is_pdf
    show_pdf_or_image = is_pdf or is_image

    owner.preview_save_btn.Show(show_pdf_only)
    owner.preview_rotate_all_left_btn.Show(show_pdf_only)
    owner.preview_rotate_all_right_btn.Show(show_pdf_only)
    owner.preview_optimize_btn.Show(show_pdf_only)
    owner.preview_ajust_page_width_btn.Show(show_pdf_only)
    owner.preview_remove_page_btn.Show(show_pdf_only)

    owner.preview_rotate_left_btn.Show(show_pdf_or_image)
    owner.preview_rotate_right_btn.Show(show_pdf_or_image)

    owner.preview_toolbar.Layout()
    owner.filePreview.Layout()
    update_pdf_save_button_state(owner)


def select_pdf_page(owner, page_panel):
    if owner.selected_pdf_page_panel is page_panel:
        return

    if owner.selected_pdf_page_panel is not None:
        owner.selected_pdf_page_panel.SetBackgroundColour(wx.NullColour)
        owner.selected_pdf_page_panel.Refresh()

    owner.selected_pdf_page_panel = page_panel
    owner.selected_pdf_page_panel.SetBackgroundColour(wx.Colour(200, 230, 255))
    owner.selected_pdf_page_panel.Refresh()
    update_rotate_page_buttons_state(owner)


def on_pdf_page_select(owner, event):
    page_panel = get_pdf_page_panel_from_event(owner, event)
    if page_panel is None:
        return

    select_pdf_page(owner, page_panel)
    owner._pdf_drag_start_panel = page_panel
    owner._pdf_drag_start_pos = event.GetPosition()
    event.Skip()


def on_pdf_page_drag_motion(owner, event):
    pdf_dragdrop.on_pdf_page_drag_motion(owner, event)


def _start_pdf_page_drag(owner, page_panel):
    pdf_dragdrop.start_pdf_page_drag(owner, page_panel)


def handle_pdf_page_drop(owner, target_index, payload, insert_before=True):
    pdf_dragdrop.handle_pdf_page_drop(owner, target_index, payload, insert_before=insert_before)


def clear_pdf_feed(owner):
    """Clear the PDF feed display."""
    owner.pdf_pages_sizer.Clear(True)
    owner.selected_pdf_page_panel = None
    update_rotate_page_buttons_state(owner)


def show_pdf_feed(owner, path):
    update_preview_toolbar_visibility(owner, is_pdf=True, is_image=False)
    with owner.busy_cursor():
        try:
            owner.current_pdf_path = path
            clear_pdf_feed(owner)
            max_height = max(100, min(1000, int(270 * owner.pdf_preview_zoom)))
            page_count, shown_pages, previews = get_pdf_page_previews(path, max_height=max_height)

            gap_width = 22
            page_height = 180
            if previews:
                first_bitmap = previews[0][1]
                page_height = max(160, first_bitmap.GetSize().y)

            leading_gap = wx.Panel(owner.pdf_pages_panel, size=(gap_width, page_height), style=wx.BORDER_NONE)
            leading_gap.SetMinSize((gap_width, page_height))
            leading_gap.page_index = 0
            leading_gap.Bind(wx.EVT_CONTEXT_MENU, on_preview_right_click)
            leading_gap.SetDropTarget(pdf_dragdrop.PdfPageDropTarget(owner, 0, leading_gap, insert_before=True))
            owner.pdf_pages_sizer.Add(leading_gap, 0, wx.ALL, 0)

            for index, (page_no, bitmap) in enumerate(previews):
                page_panel = wx.Panel(owner.pdf_pages_panel, style=wx.BORDER_SIMPLE)
                page_panel.page_index = index
                page_panel.SetDropTarget(pdf_dragdrop.PdfPageDropTarget(owner, index, page_panel))

                def make_select_handler(owner_ref):
                    return lambda evt: on_pdf_page_select_wrapper(owner_ref, evt)

                def make_motion_handler(owner_ref):
                    return lambda evt: on_pdf_page_drag_motion(owner_ref, evt)

                page_panel.Bind(wx.EVT_LEFT_DOWN, make_select_handler(owner))
                page_panel.Bind(wx.EVT_MOTION, make_motion_handler(owner))
                page_panel.Bind(wx.EVT_CONTEXT_MENU, on_preview_right_click)

                page_sizer = wx.BoxSizer(wx.VERTICAL)
                page_label = wx.StaticText(page_panel, label=tr("page_label", page_no=page_no, page_count=page_count))
                page_bitmap = wx.StaticBitmap(page_panel, bitmap=bitmap)

                page_label.Bind(wx.EVT_LEFT_DOWN, make_select_handler(owner))
                page_label.Bind(wx.EVT_MOTION, make_motion_handler(owner))
                page_label.Bind(wx.EVT_CONTEXT_MENU, on_preview_right_click)
                page_bitmap.Bind(wx.EVT_LEFT_DOWN, make_select_handler(owner))
                page_bitmap.Bind(wx.EVT_MOTION, make_motion_handler(owner))
                page_bitmap.Bind(wx.EVT_CONTEXT_MENU, on_preview_right_click)

                page_sizer.Add(page_label, 0, wx.ALIGN_CENTER | wx.ALL, 3)
                page_sizer.Add(page_bitmap, 0, wx.ALIGN_CENTER | wx.ALL, 3)
                page_panel.SetSizer(page_sizer)

                owner.pdf_pages_sizer.Add(page_panel, 0, wx.ALL, 3)

                gap_panel = wx.Panel(owner.pdf_pages_panel, size=(gap_width, page_height), style=wx.BORDER_NONE)
                gap_panel.SetMinSize((gap_width, page_height))
                gap_panel.page_index = index + 1
                gap_panel.Bind(wx.EVT_CONTEXT_MENU, on_preview_right_click)
                gap_panel.SetDropTarget(pdf_dragdrop.PdfPageDropTarget(owner, index + 1, gap_panel, insert_before=True))
                owner.pdf_pages_sizer.Add(gap_panel, 0, wx.ALL, 0)

            trailing_gap = wx.Panel(owner.pdf_pages_panel, size=(gap_width, page_height), style=wx.BORDER_NONE)
            trailing_gap.SetMinSize((gap_width, page_height))
            trailing_gap.page_index = page_count
            trailing_gap.Bind(wx.EVT_CONTEXT_MENU, on_preview_right_click)
            trailing_gap.SetDropTarget(pdf_dragdrop.PdfPageDropTarget(owner, page_count, trailing_gap, insert_before=False))
            owner.pdf_pages_sizer.Add(trailing_gap, 0, wx.ALL, 0)

            if page_count > shown_pages:
                note = wx.StaticText(
                    owner.pdf_pages_panel,
                    label=tr("showing_first_pages", shown_pages=shown_pages, page_count=page_count),
                )
                owner.pdf_pages_sizer.Add(note, 0, wx.ALIGN_CENTER | wx.ALL, 3)
        except Exception as exc:
            _ = exc
            owner.pdf_pages_panel.Hide()
            owner.filePreview.Layout()
            return

            update_pdf_save_button_state(owner)

    owner.preview_text.Show(False)
    owner.pdf_pages_panel.Show(True)
    owner.pdf_pages_panel.SetVirtualSize((1, 1))
    owner.pdf_pages_panel.Layout()
    owner.filePreview.Layout()


def on_pdf_page_select_wrapper(owner, event):
    """Wrapper to handle PDF page selection with owner context."""
    on_pdf_page_select(owner, event)


def show_file_preview(owner, path):
    owner.current_preview_path = path
    owner.selected_pdf_page_panel = None
    owner.current_image_preview = None
    owner.current_image_zoom = 1.0
    update_rotate_page_buttons_state(owner)
    update_pdf_save_button_state(owner)
    owner.preview_text.Show(False)
    owner.pdf_pages_panel.Hide()
    owner.pdf_preview_container.Hide()

    if not path:
        update_preview_toolbar_visibility(owner, is_pdf=False, is_image=False)
        owner.filePreview.Layout()
        return

    if os.path.isdir(path):
        update_preview_toolbar_visibility(owner, is_pdf=False, is_image=False)
        owner.filePreview.Layout()
        return

    if not os.path.isfile(path):
        update_preview_toolbar_visibility(owner, is_pdf=False, is_image=False)
        owner.filePreview.Layout()
        return

    if is_pdf_file(path):
        update_preview_toolbar_visibility(owner, is_pdf=True, is_image=False)
        show_pdf_feed(owner, path)
        return

    if image_utils.can_preview_image(path):
        update_preview_toolbar_visibility(owner, is_pdf=False, is_image=True)
        image_utils.show_image_preview(owner, path, tr)
        return

    update_preview_toolbar_visibility(owner, is_pdf=False, is_image=False)

    try:
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read(12000)
    except UnicodeDecodeError:
        try:
            with open(path, "r", encoding="latin-1") as handle:
                content = handle.read(12000)
        except Exception as exc:
            _ = exc
            owner.filePreview.Layout()
            return
    except Exception as exc:
        _ = exc
        owner.filePreview.Layout()
        return

    if not content.strip():
        owner.filePreview.Layout()
        return

    if len(content) >= 12000:
        content = content[:12000] + tr("preview_truncated_suffix")

    owner.preview_text.SetValue(content)
    owner.preview_text.Show(True)
    owner.filePreview.Layout()


# Preview action handlers


def _get_preview_owner_from_event(event, fallback_owner=None):
    owner = fallback_owner if fallback_owner is not None else event.GetEventObject()
    while owner is not None and not hasattr(owner, "current_preview_path"):
        owner = owner.GetParent() if hasattr(owner, "GetParent") else None

    # EVT_MENU events may come from menu/menu-item objects that are not in the window tree.
    if owner is None:
        for top_level in wx.GetTopLevelWindows():
            if hasattr(top_level, "current_preview_path"):
                owner = top_level
                break

    return owner

def on_preview_edit(event):
    owner = _get_preview_owner_from_event(event)
    if owner and owner.current_preview_path and os.path.isfile(owner.current_preview_path):
        try:
            os.startfile(owner.current_preview_path)
        except Exception as exc:
            wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)
    else:
        wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)


def on_preview_delete(event):
    owner = _get_preview_owner_from_event(event)
    if not owner or not owner.current_preview_path or not os.path.isfile(owner.current_preview_path):
        wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
        return
    dialog = wx.MessageDialog(
        owner,
        tr("confirm_delete", path=owner.current_preview_path),
        tr("preview_delete_button"),
        wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
    )
    if dialog.ShowModal() == wx.ID_YES:
        try:
            discard_pdf_changes(owner.current_preview_path)
            os.remove(owner.current_preview_path)
            show_file_preview(owner, None)
            owner.load_folder(owner.path_box.GetValue())
        except Exception as exc:
            wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)
    dialog.Destroy()


def on_preview_save(event):
    owner = _get_preview_owner_from_event(event)
    if not owner or not is_pdf_file(owner.current_preview_path):
        wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
        return
    try:
        with owner.busy_cursor():
            save_pdf(owner.current_preview_path)
            update_pdf_save_button_state(owner)
            show_pdf_feed(owner, owner.current_preview_path)
            owner.load_folder(owner.path_box.GetValue())
    except Exception as exc:
        wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)


def on_preview_zoom_in(event):
    owner = _get_preview_owner_from_event(event)
    if owner:
        if is_pdf_file(owner.current_preview_path):
            with owner.busy_cursor():
                owner.pdf_preview_zoom = min(owner.pdf_preview_zoom * 1.25, 3.0)
                show_pdf_feed(owner, owner.current_preview_path)
            return

        if image_utils.can_preview_image(owner.current_preview_path):
            with owner.busy_cursor():
                owner.current_image_zoom = min(getattr(owner, "current_image_zoom", 1.0) * 1.25, 8.0)
                if owner.current_image_preview is None or not owner.current_image_preview.IsOk():
                    image_utils.show_image_preview(owner, owner.current_preview_path, tr)
                else:
                    image_utils.refresh_image_preview_bitmap(owner)
            return

        wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)


def on_preview_zoom_out(event):
    owner = _get_preview_owner_from_event(event)
    if owner:
        if is_pdf_file(owner.current_preview_path):
            with owner.busy_cursor():
                owner.pdf_preview_zoom = max(owner.pdf_preview_zoom / 1.25, 0.4)
                show_pdf_feed(owner, owner.current_preview_path)
            return

        if image_utils.can_preview_image(owner.current_preview_path):
            with owner.busy_cursor():
                owner.current_image_zoom = max(getattr(owner, "current_image_zoom", 1.0) / 1.25, 0.1)
                if owner.current_image_preview is None or not owner.current_image_preview.IsOk():
                    image_utils.show_image_preview(owner, owner.current_preview_path, tr)
                else:
                    image_utils.refresh_image_preview_bitmap(owner)
            return

        wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)


def on_preview_rotate(event):
    owner = _get_preview_owner_from_event(event)
    if owner:
        if not is_pdf_file(owner.current_preview_path):
            wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
            return
        try:
            with owner.busy_cursor():
                rotate_pdf(owner.current_preview_path, 90)
                show_pdf_feed(owner, owner.current_preview_path)
        except Exception as exc:
            wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)


def on_preview_rotate_all_left(event):
    owner = _get_preview_owner_from_event(event)
    if owner:
        if not is_pdf_file(owner.current_preview_path):
            wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
            return
        try:
            with owner.busy_cursor():
                rotate_pdf(owner.current_preview_path, -90)
                show_pdf_feed(owner, owner.current_preview_path)
        except Exception as exc:
            wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)


def on_preview_rotate_left(event):
    owner = _get_preview_owner_from_event(event)
    if owner:
        if is_pdf_file(owner.current_preview_path):
            page_index = get_selected_pdf_page_index(owner)
            if page_index is None:
                wx.MessageBox(tr("select_pdf_page"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
                return
            try:
                with owner.busy_cursor():
                    rotate_pdf_page(owner.current_preview_path, page_index, -90)
                    show_pdf_feed(owner, owner.current_preview_path)
            except Exception as exc:
                wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)
            return

        if image_utils.can_preview_image(owner.current_preview_path):
            try:
                with owner.busy_cursor():
                    image_utils.rotate_image_file(owner.current_preview_path, clockwise=False)
                    image_utils.show_image_preview(owner, owner.current_preview_path, tr)
            except Exception as exc:
                wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)
            return

        if not is_pdf_file(owner.current_preview_path):
            wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
            return


def _wheel_steps(event):
    delta = event.GetWheelDelta() or 120
    return max(1, abs(event.GetWheelRotation()) // delta)


def _is_mouse_over(window):
    if window is None:
        return False
    try:
        if not window.IsShownOnScreen() or not window.IsEnabled():
            return False
        mouse_screen = wx.GetMousePosition()
        mouse_client = window.ScreenToClient(mouse_screen)
        return window.GetClientRect().Contains(mouse_client)
    except Exception:
        return False


def on_preview_rotate_buttons_wheel(event):
    if event.GetWheelRotation() == 0:
        event.Skip()
        return

    owner = event.GetEventObject()
    while owner is not None and not hasattr(owner, "preview_rotate_left_btn"):
        owner = owner.GetParent() if hasattr(owner, "GetParent") else None

    if owner is not None:
        if _is_mouse_over(owner.preview_rotate_left_btn):
            zoom_func = on_preview_zoom_in if event.GetWheelRotation() > 0 else on_preview_zoom_out
            for _ in range(_wheel_steps(event)):
                zoom_func(event)
            return
        if _is_mouse_over(owner.preview_rotate_right_btn):
            zoom_func = on_preview_zoom_in if event.GetWheelRotation() > 0 else on_preview_zoom_out
            for _ in range(_wheel_steps(event)):
                zoom_func(event)
            return

        # Allow wheel-zoom while cursor is over the preview image area.
        if _is_mouse_over(getattr(owner, "pdf_preview", None)) or _is_mouse_over(getattr(owner, "pdf_preview_container", None)):
            zoom_func = on_preview_zoom_in if event.GetWheelRotation() > 0 else on_preview_zoom_out
            for _ in range(_wheel_steps(event)):
                zoom_func(event)
            return

    event.Skip()


def on_preview_rotate_right(event):
    owner = _get_preview_owner_from_event(event)
    if owner:
        if is_pdf_file(owner.current_preview_path):
            page_index = get_selected_pdf_page_index(owner)
            if page_index is None:
                wx.MessageBox(tr("select_pdf_page"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
                return
            try:
                with owner.busy_cursor():
                    rotate_pdf_page(owner.current_preview_path, page_index, 90)
                    show_pdf_feed(owner, owner.current_preview_path)
            except Exception as exc:
                wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)
            return

        if image_utils.can_preview_image(owner.current_preview_path):
            try:
                with owner.busy_cursor():
                    image_utils.rotate_image_file(owner.current_preview_path, clockwise=True)
                    image_utils.show_image_preview(owner, owner.current_preview_path, tr)
            except Exception as exc:
                wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)
            return

        if not is_pdf_file(owner.current_preview_path):
            wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
            return


def on_preview_rotate_all_right(event):
    owner = _get_preview_owner_from_event(event)
    if owner:
        if not is_pdf_file(owner.current_preview_path):
            wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
            return
        try:
            with owner.busy_cursor():
                rotate_pdf(owner.current_preview_path, 90)
                show_pdf_feed(owner, owner.current_preview_path)
        except Exception as exc:
            wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)


def on_preview_remove_page(event, owner=None):
    owner = _get_preview_owner_from_event(event, fallback_owner=owner)
    if owner:
        if not is_pdf_file(owner.current_preview_path):
            wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
            return

        page_index = get_selected_pdf_page_index(owner)
        if page_index is None:
            wx.MessageBox(tr("select_pdf_page"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
            return

        dialog = wx.MessageDialog(
            owner,
            tr("confirm_remove_page", page_no=page_index + 1),
            tr("preview_remove_page_button"),
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
        )
        if dialog.ShowModal() == wx.ID_YES:
            try:
                with owner.busy_cursor():
                    remove_pdf_page(owner.current_preview_path, page_index)
                    ## save_pdf(owner.current_preview_path)
                    ## owner.refresh_list_item_size(owner.current_preview_path)
                    show_pdf_feed(owner, owner.current_preview_path)
                    update_rotate_page_buttons_state(owner)
                    update_pdf_save_button_state(owner)
            except Exception as exc:
                wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)
        dialog.Destroy()


def on_preview_optimize(event):
    owner = _get_preview_owner_from_event(event)
    if owner:
        if not is_pdf_file(owner.current_preview_path):
            wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
            return
        try:
            with owner.busy_cursor():
                optimize_pdf(owner.current_preview_path)
                save_pdf(owner.current_preview_path)
                owner.refresh_list_item_size(owner.current_preview_path)
                update_pdf_save_button_state(owner)
                show_pdf_feed(owner, owner.current_preview_path)
        except Exception as exc:
            wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)


def on_preview_ajust_page_width(event):
    owner = _get_preview_owner_from_event(event)
    if owner:
        if not is_pdf_file(owner.current_preview_path):
            wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
            return
        try:
            with owner.busy_cursor():
                ajust_page_width(owner.current_preview_path)
                save_pdf(owner.current_preview_path)
                owner.refresh_list_item_size(owner.current_preview_path)
                update_pdf_save_button_state(owner)
                show_pdf_feed(owner, owner.current_preview_path)
        except Exception as exc:
            wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)


def on_preview_right_click(event):
    """Context menu for preview pane."""
    owner = event.GetEventObject()
    while owner and not hasattr(owner, 'filePreview'):
        owner = owner.GetParent()
    if not owner:
        return

    icon_manager = getattr(owner, "icon_manager", None)
    menu = wx.Menu()

    def set_menu_icon(item, art_id=None, bitmap=None):
        if bitmap is None:
            bitmap = wx.ArtProvider.GetBitmap(art_id, wx.ART_MENU, (16, 16))
        if bitmap.IsOk():
            item.SetBitmap(bitmap)

    def set_menu_icon2(item, icon_manager, icon_name, bitmap=None):
        if bitmap is None:
            bitmap = icon_manager.get_bitmap(icon_name, size=(16, 16))
        if bitmap.IsOk():
            item.SetBitmap(bitmap)            

    edit_item = menu.Append(-1, tr("preview_edit_button"))
    set_menu_icon(edit_item, wx.ART_FIND)
    save_item = menu.Append(-1, tr("preview_save_button"))
    set_menu_icon2(save_item, icon_manager, "save")
    delete_item = menu.Append(-1, tr("preview_delete_button"))
    set_menu_icon(delete_item, wx.ART_DELETE)
    menu.AppendSeparator()
    zoom_in_item = menu.Append(-1, tr("preview_zoom_in_button"))
    set_menu_icon(zoom_in_item, wx.ART_PLUS)
    zoom_out_item = menu.Append(-1, tr("preview_zoom_out_button"))
    set_menu_icon(zoom_out_item, wx.ART_MINUS)
    menu.AppendSeparator()
    rotate_all_left_item = menu.Append(-1, tr("preview_rotate_all_left_button"))
    joined_menu_undo = image_utils.create_joined_art_bitmap(wx.ART_UNDO, client=wx.ART_MENU, size=(16, 16))
    set_menu_icon(rotate_all_left_item, bitmap=joined_menu_undo)
    rotate_left_item = menu.Append(-1, tr("preview_rotate_left_button"))
    set_menu_icon(rotate_left_item, wx.ART_UNDO)
    rotate_right_item = menu.Append(-1, tr("preview_rotate_right_button"))
    set_menu_icon(rotate_right_item, wx.ART_REDO)
    rotate_all_right_item = menu.Append(-1, tr("preview_rotate_all_right_button"))
    joined_menu_redo = image_utils.create_joined_art_bitmap(wx.ART_REDO, client=wx.ART_MENU, size=(16, 16))
    set_menu_icon(rotate_all_right_item, bitmap=joined_menu_redo)
    remove_page_item = menu.Append(-1, tr("preview_remove_page_button"))
    set_menu_icon2(remove_page_item, icon_manager, "delete")
    menu.AppendSeparator()
    optimize_item = menu.Append(-1, tr("preview_optimize_button"))
    set_menu_icon2(optimize_item, icon_manager, "ok")
    ajust_page_width_item = menu.Append(-1, tr("preview_ajust_page_width_button"))
    set_menu_icon(ajust_page_width_item, wx.ART_REPORT_VIEW)
 
    save_item.Enable(is_pdf_file(owner.current_preview_path) and has_unsaved_pdf_changes(owner.current_preview_path))
    remove_page_item.Enable(is_pdf_file(owner.current_preview_path) and get_selected_pdf_page_index(owner) is not None)

    owner.Bind(wx.EVT_MENU, on_preview_edit, edit_item)
    owner.Bind(wx.EVT_MENU, on_preview_save, save_item)
    owner.Bind(wx.EVT_MENU, on_preview_delete, delete_item)
    owner.Bind(wx.EVT_MENU, on_preview_zoom_in, zoom_in_item)
    owner.Bind(wx.EVT_MENU, on_preview_zoom_out, zoom_out_item)
    owner.Bind(wx.EVT_MENU, on_preview_rotate_all_left, rotate_all_left_item)
    owner.Bind(wx.EVT_MENU, on_preview_rotate_left, rotate_left_item)
    owner.Bind(wx.EVT_MENU, on_preview_rotate_right, rotate_right_item)
    owner.Bind(wx.EVT_MENU, on_preview_rotate_all_right, rotate_all_right_item)
    owner.Bind(wx.EVT_MENU, lambda evt: on_preview_remove_page(evt, owner=owner), remove_page_item)
    owner.Bind(wx.EVT_MENU, on_preview_optimize, optimize_item)
    owner.Bind(wx.EVT_MENU, on_preview_ajust_page_width, ajust_page_width_item)

    popup_window = owner.filePreview
    if event is not None:
        try:
            obj = event.GetEventObject()
            if isinstance(obj, wx.Window):
                popup_window = obj
        except Exception:
            pass

    popup_window.PopupMenu(menu)
    menu.Destroy()
