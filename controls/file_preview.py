import os
import wx

from localization import tr
from file_operations.pdf_utils import adjust_page_width, auto_rotate_pdf, discard_pdf_changes, get_pdf_page_count, get_pdf_page_previews, has_unsaved_pdf_changes, is_pdf_file, move_pdf_page, optimize_pdf, remove_pdf_page, rotate_pdf, rotate_pdf_page, save_pdf, save_pdf_as
import file_operations.image_utils as image_utils
import file_operations.pdf_dragdrop as pdf_dragdrop


PAGE_VIEW_MODE_1_WIDE = "1_page_wide"
PAGE_VIEW_MODE_2_WIDE = "2_pages_wide"
PAGE_VIEW_MODE_1_TALL = "1_page_tall"
PAGE_VIEW_MODE_MANUAL = "manual"
FIXED_PAGE_VIEW_MODES = {PAGE_VIEW_MODE_1_WIDE, PAGE_VIEW_MODE_2_WIDE, PAGE_VIEW_MODE_1_TALL}
VALID_PAGE_VIEW_MODES = FIXED_PAGE_VIEW_MODES | {PAGE_VIEW_MODE_MANUAL}


def build_file_preview_pane(owner, file_splitter):
    """Create and configure the file preview pane UI."""
    owner.filePreview = wx.Panel(file_splitter, style=wx.BORDER_SUNKEN)
    owner.preview_toolbar = wx.BoxSizer(wx.HORIZONTAL)

    preview_icon_size = (16, 16)
    preview_button_size = (24, 24)
    icon_manager = owner.icon_manager
    owner.filePreview.icon_manager = icon_manager

    ## owner.preview_edit_btn = image_utils.create_bitmap_button(owner.filePreview, wx.ART_FIND, tr("preview_edit_button"), icon_size=preview_icon_size, button_size=preview_button_size)
    owner.preview_save_btn = image_utils.create_bitmap_button2(owner.filePreview, icon_manager, "save", tr("preview_save_button"), icon_size=preview_icon_size, button_size=preview_button_size)
    ## owner.preview_delete_btn = image_utils.create_bitmap_button(owner.filePreview, wx.ART_DELETE, tr("preview_delete_button"), icon_size=preview_icon_size, button_size=preview_button_size)
    owner.preview_zoom_out_btn = image_utils.create_bitmap_button(owner.filePreview, wx.ART_MINUS, tr("preview_zoom_out_button"), icon_size=preview_icon_size, button_size=preview_button_size)
    owner.preview_zoom_in_btn = image_utils.create_bitmap_button(owner.filePreview, wx.ART_PLUS, tr("preview_zoom_in_button"), icon_size=preview_icon_size, button_size=preview_button_size)
    owner.preview_page_view_mode_btn = image_utils.create_bitmap_button(owner.filePreview, wx.ART_LIST_VIEW, tr("preview_show_mode"), icon_size=preview_icon_size, button_size=preview_button_size)
    owner.preview_rotate_menu_btn = image_utils.create_bitmap_button2(owner.filePreview, icon_manager, "snow", tr("preview_rotate_button"), icon_size=preview_icon_size, button_size=preview_button_size)
    owner.preview_move_page_btn = image_utils.create_bitmap_button(owner.filePreview, wx.ART_GO_FORWARD, tr("preview_move_page_button"), icon_size=preview_icon_size, button_size=preview_button_size)
    owner.preview_remove_page_btn = image_utils.create_bitmap_button2(owner.filePreview, icon_manager, "delete", tr("preview_remove_page_button"), icon_size=preview_icon_size, button_size=preview_button_size)
    owner.preview_adjust_page_width_btn = image_utils.create_bitmap_button(owner.filePreview, wx.ART_REPORT_VIEW, tr("preview_adjust_page_width_button"), icon_size=preview_icon_size, button_size=preview_button_size)
    owner.preview_optimize_btn = image_utils.create_bitmap_button2(owner.filePreview, icon_manager, "ok", tr("preview_optimize_button"), icon_size=preview_icon_size, button_size=preview_button_size)

    ## owner.preview_toolbar.Add(owner.preview_edit_btn, 0, wx.RIGHT, 3)
    owner.preview_toolbar.Add(owner.preview_save_btn, 0, wx.RIGHT, 10)
    ## owner.preview_toolbar.Add(owner.preview_delete_btn, 0, wx.RIGHT, 10)
    owner.preview_toolbar.Add(owner.preview_zoom_out_btn, 0, wx.RIGHT, 3)
    owner.preview_toolbar.Add(owner.preview_zoom_in_btn, 0, wx.RIGHT, 3)
    owner.preview_toolbar.Add(owner.preview_page_view_mode_btn, 0, wx.RIGHT, 10)
    owner.preview_toolbar.Add(owner.preview_rotate_menu_btn, 0, wx.RIGHT, 3)
    owner.preview_toolbar.Add(owner.preview_move_page_btn, 0, wx.RIGHT, 3)
    owner.preview_toolbar.Add(owner.preview_remove_page_btn, 0, wx.RIGHT, 3)
    owner.preview_toolbar.Add(owner.preview_adjust_page_width_btn, 0, wx.RIGHT, 3)
    owner.preview_toolbar.Add(owner.preview_optimize_btn, 0)

    owner.preview_save_btn.Enable(False)
    owner.preview_rotate_menu_btn.Enable(False)
    owner.preview_remove_page_btn.Enable(False)
    owner.preview_move_page_btn.Enable(False)

    owner.preview_text = wx.TextCtrl(
        owner.filePreview,
        style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL | wx.VSCROLL,
    )
    owner.preview_text.SetValue("")
    owner.preview_text.Hide()
    owner.preview_text.Bind(wx.EVT_CONTEXT_MENU, on_preview_right_click)

    owner.pdf_pages_panel = wx.ScrolledWindow(owner.filePreview, style=wx.HSCROLL | wx.VSCROLL)
    owner.pdf_pages_panel.SetScrollRate(10, 10)
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

    top_pane = getattr(owner, "list_host_panel", owner.list)
    file_splitter.SplitHorizontally(top_pane, owner.filePreview, 400)


def bind_preview_events(owner):
    """Bind preview pane event handlers."""
    ## owner.preview_edit_btn.Bind(wx.EVT_BUTTON, on_preview_edit)
    owner.preview_save_btn.Bind(wx.EVT_BUTTON, on_preview_save_menu)
    ## owner.preview_delete_btn.Bind(wx.EVT_BUTTON, on_preview_delete)
    owner.preview_zoom_in_btn.Bind(wx.EVT_BUTTON, on_preview_zoom_in)
    owner.preview_zoom_out_btn.Bind(wx.EVT_BUTTON, on_preview_zoom_out)
    owner.preview_rotate_menu_btn.Bind(wx.EVT_BUTTON, on_preview_rotate_menu)
    owner.filePreview.Bind(wx.EVT_MOUSEWHEEL, on_preview_rotate_buttons_wheel)
    owner.preview_text.Bind(wx.EVT_MOUSEWHEEL, on_preview_rotate_buttons_wheel)
    owner.pdf_pages_panel.Bind(wx.EVT_MOUSEWHEEL, on_preview_rotate_buttons_wheel)
    owner.pdf_preview_container.Bind(wx.EVT_MOUSEWHEEL, on_preview_rotate_buttons_wheel)
    owner.pdf_preview.Bind(wx.EVT_MOUSEWHEEL, on_preview_rotate_buttons_wheel)
    owner.preview_page_view_mode_btn.Bind(wx.EVT_BUTTON, on_preview_page_view_mode_menu)
    owner.preview_move_page_btn.Bind(wx.EVT_BUTTON, on_preview_move_page)
    owner.preview_optimize_btn.Bind(wx.EVT_BUTTON, on_preview_optimize)
    owner.preview_adjust_page_width_btn.Bind(wx.EVT_BUTTON, on_preview_adjust_page_width)
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


def update_page_buttons_state(owner):
    can_select_pdf_page = (
        is_pdf_file(owner.current_preview_path)
        and get_selected_pdf_page_index(owner) is not None
    )
    can_rotate_selected_page = can_select_pdf_page
    can_rotate_image = image_utils.can_preview_image(owner.current_preview_path)
    can_rotate = can_rotate_selected_page or can_rotate_image
    owner.preview_rotate_menu_btn.Enable(is_pdf_file(owner.current_preview_path) or can_rotate_image)
    owner.preview_move_page_btn.Enable(can_select_pdf_page) 
    owner.preview_remove_page_btn.Enable(can_select_pdf_page)


def update_pdf_save_button_state(owner):
    can_save = is_pdf_file(owner.current_preview_path)
    owner.preview_save_btn.Enable(can_save)


def update_preview_toolbar_visibility(owner, is_pdf=False, is_image=False):
    show_pdf_only = is_pdf
    show_pdf_or_image = is_pdf or is_image

    owner.preview_save_btn.Show(show_pdf_only)
    owner.preview_rotate_menu_btn.Show(show_pdf_or_image)
    owner.preview_optimize_btn.Show(show_pdf_only)
    owner.preview_adjust_page_width_btn.Show(show_pdf_only)
    owner.preview_move_page_btn.Show(show_pdf_only)
    owner.preview_remove_page_btn.Show(show_pdf_only)
    owner.preview_page_view_mode_btn.Show(show_pdf_only)

    owner.preview_toolbar.Layout()
    owner.filePreview.Layout()
    update_pdf_save_button_state(owner)


def _get_preview_layout_mode(owner):
    selected_mode = getattr(owner, "pdf_page_view_selected_mode", None)
    if selected_mode in FIXED_PAGE_VIEW_MODES:
        return selected_mode

    return PAGE_VIEW_MODE_1_TALL


def sync_pdf_page_view_mode_controls(owner):
    current_mode = getattr(owner, "pdf_page_view_mode", PAGE_VIEW_MODE_1_TALL)
    if current_mode in FIXED_PAGE_VIEW_MODES:
        owner.pdf_page_view_selected_mode = current_mode

    selected_mode = getattr(owner, "pdf_page_view_selected_mode", PAGE_VIEW_MODE_1_TALL)
    if selected_mode not in FIXED_PAGE_VIEW_MODES:
        selected_mode = PAGE_VIEW_MODE_1_WIDE

    if current_mode == PAGE_VIEW_MODE_MANUAL:
        tooltip_text = tr("preview_show_manual_scale")
    elif selected_mode == PAGE_VIEW_MODE_1_WIDE:
        tooltip_text = tr("preview_show_1_page_wide")
    elif selected_mode == PAGE_VIEW_MODE_2_WIDE:
        tooltip_text = tr("preview_show_2_pages_wide")
    elif selected_mode == PAGE_VIEW_MODE_1_TALL:
        tooltip_text = tr("preview_show_1_page_tall")
    else:
        tooltip_text = tr("preview_show_1_page_wide")

    owner.preview_page_view_mode_btn.SetToolTip(tooltip_text)

def _set_pdf_page_view_mode(owner, mode):
    if owner is None or not hasattr(owner, "set_pdf_page_view_mode"):
        return
    owner.pdf_page_view_selected_mode = mode
    owner.set_pdf_page_view_mode(mode, refresh_preview=True)


def on_preview_show_1_page_wide(event):
    owner = _get_preview_owner_from_event(event)
    _set_pdf_page_view_mode(owner, PAGE_VIEW_MODE_1_WIDE)


def on_preview_show_2_pages_wide(event):
    owner = _get_preview_owner_from_event(event)
    _set_pdf_page_view_mode(owner, PAGE_VIEW_MODE_2_WIDE)


def on_preview_show_1_page_tall(event):
    owner = _get_preview_owner_from_event(event)
    _set_pdf_page_view_mode(owner, PAGE_VIEW_MODE_1_TALL)


def on_preview_show_manual_scale(event):
    owner = _get_preview_owner_from_event(event)
    _set_pdf_page_view_mode(owner, PAGE_VIEW_MODE_MANUAL)


def build_page_view_mode_menu(owner, menu):
    show_1_page_wide_item = menu.AppendRadioItem(-1, tr("preview_show_1_page_wide"))
    show_2_pages_wide_item = menu.AppendRadioItem(-1, tr("preview_show_2_pages_wide"))
    show_1_page_tall_item = menu.AppendRadioItem(-1, tr("preview_show_1_page_tall"))
    show_manual_scale_item = menu.AppendRadioItem(-1, tr("preview_show_manual_scale"))

    current_mode = getattr(owner, "pdf_page_view_mode", PAGE_VIEW_MODE_1_TALL)
    selected_mode = getattr(owner, "pdf_page_view_selected_mode", PAGE_VIEW_MODE_1_TALL)
    if selected_mode not in FIXED_PAGE_VIEW_MODES:
        selected_mode = PAGE_VIEW_MODE_1_TALL

    show_1_page_wide_item.Check(current_mode != PAGE_VIEW_MODE_MANUAL and selected_mode == PAGE_VIEW_MODE_1_TALL)
    show_2_pages_wide_item.Check(current_mode != PAGE_VIEW_MODE_MANUAL and selected_mode == PAGE_VIEW_MODE_2_WIDE)
    show_1_page_tall_item.Check(current_mode != PAGE_VIEW_MODE_MANUAL and selected_mode == PAGE_VIEW_MODE_1_TALL)
    show_manual_scale_item.Check(current_mode == PAGE_VIEW_MODE_MANUAL)

    is_pdf_preview = is_pdf_file(owner.current_preview_path)
    show_1_page_wide_item.Enable(is_pdf_preview)
    show_2_pages_wide_item.Enable(is_pdf_preview)
    show_1_page_tall_item.Enable(is_pdf_preview)
    show_manual_scale_item.Enable(is_pdf_preview)

    owner.Bind(wx.EVT_MENU, on_preview_show_1_page_wide, show_1_page_wide_item)
    owner.Bind(wx.EVT_MENU, on_preview_show_2_pages_wide, show_2_pages_wide_item)
    owner.Bind(wx.EVT_MENU, on_preview_show_1_page_tall, show_1_page_tall_item)
    owner.Bind(wx.EVT_MENU, on_preview_show_manual_scale, show_manual_scale_item)


def on_preview_page_view_mode_menu(event):
    owner = _get_preview_owner_from_event(event)
    if owner is None:
        return

    menu = wx.Menu()
    build_page_view_mode_menu(owner, menu)
    sync_pdf_page_view_mode_controls(owner)
    anchor = (0, owner.preview_page_view_mode_btn.GetSize().GetHeight())
    owner.preview_page_view_mode_btn.PopupMenu(menu, anchor)
    menu.Destroy()


def build_save_menu(owner, menu):
    icon_manager = getattr(owner, "icon_manager", None)

    save_item = menu.Append(-1, tr("preview_save_button"))
    save_as_item = menu.Append(-1, tr("preview_save_as_button"))

    if icon_manager is not None:
        icon_manager.set_menu_icon2(save_item, "save")

    save_as_art_id = getattr(wx, "ART_FILE_SAVE_AS", wx.ART_FILE_SAVE)
    save_as_bitmap = wx.ArtProvider.GetBitmap(save_as_art_id, wx.ART_MENU, (16, 16))
    if save_as_bitmap.IsOk():
        save_as_item.SetBitmap(save_as_bitmap)

    is_pdf_preview = is_pdf_file(owner.current_preview_path)
    save_item.Enable(is_pdf_preview and has_unsaved_pdf_changes(owner.current_preview_path))
    save_as_item.Enable(is_pdf_preview)

    owner.Bind(wx.EVT_MENU, on_preview_save, save_item)
    owner.Bind(wx.EVT_MENU, on_preview_save_as, save_as_item)

    return {
        "save_item": save_item,
        "save_as_item": save_as_item,
    }


def on_preview_save_menu(event):
    owner = _get_preview_owner_from_event(event)
    if owner is None:
        return

    menu = wx.Menu()
    build_save_menu(owner, menu)
    anchor = (0, owner.preview_save_btn.GetSize().GetHeight())
    owner.preview_save_btn.PopupMenu(menu, anchor)
    menu.Destroy()


def build_rotation_menu(owner, menu):
    ## icon_manager = getattr(owner, "icon_manager", None)

    rotate_all_left_item = menu.Append(-1, tr("preview_rotate_all_left_button"))
    joined_menu_undo = image_utils.create_joined_art_bitmap(wx.ART_UNDO, client=wx.ART_MENU, size=(16, 16))
    if joined_menu_undo.IsOk():
        rotate_all_left_item.SetBitmap(joined_menu_undo)

    rotate_left_item = menu.Append(-1, tr("preview_rotate_left_button"))
    left_bitmap = wx.ArtProvider.GetBitmap(wx.ART_UNDO, wx.ART_MENU, (16, 16))
    if left_bitmap.IsOk():
        rotate_left_item.SetBitmap(left_bitmap)

    rotate_right_item = menu.Append(-1, tr("preview_rotate_right_button"))
    right_bitmap = wx.ArtProvider.GetBitmap(wx.ART_REDO, wx.ART_MENU, (16, 16))
    if right_bitmap.IsOk():
        rotate_right_item.SetBitmap(right_bitmap)

    rotate_all_right_item = menu.Append(-1, tr("preview_rotate_all_right_button"))
    joined_menu_redo = image_utils.create_joined_art_bitmap(wx.ART_REDO, client=wx.ART_MENU, size=(16, 16))
    if joined_menu_redo.IsOk():
        rotate_all_right_item.SetBitmap(joined_menu_redo)

    is_pdf_preview = is_pdf_file(owner.current_preview_path)
    can_rotate_image = image_utils.can_preview_image(owner.current_preview_path)
    can_rotate_single = (is_pdf_preview and get_selected_pdf_page_index(owner) is not None) or can_rotate_image

    rotate_all_left_item.Enable(is_pdf_preview)
    rotate_all_right_item.Enable(is_pdf_preview)
    rotate_left_item.Enable(can_rotate_single)
    rotate_right_item.Enable(can_rotate_single)

    owner.Bind(wx.EVT_MENU, on_preview_rotate_all_left, rotate_all_left_item)
    owner.Bind(wx.EVT_MENU, on_preview_rotate_left, rotate_left_item)
    owner.Bind(wx.EVT_MENU, on_preview_rotate_right, rotate_right_item)
    owner.Bind(wx.EVT_MENU, on_preview_rotate_all_right, rotate_all_right_item)

    return {
        "rotate_all_left_item": rotate_all_left_item,
        "rotate_left_item": rotate_left_item,
        "rotate_right_item": rotate_right_item,
        "rotate_all_right_item": rotate_all_right_item,
    }


def on_preview_rotate_menu(event):
    owner = _get_preview_owner_from_event(event)
    if owner is None:
        return

    menu = wx.Menu()
    build_rotation_menu(owner, menu)
    anchor = (0, owner.preview_rotate_menu_btn.GetSize().GetHeight())
    owner.preview_rotate_menu_btn.PopupMenu(menu, anchor)
    menu.Destroy()


def _compute_pdf_preview_max_height(owner):
    max_bitmap_width, max_bitmap_height = _compute_pdf_page_fit_constraints(owner)
    mode = _get_preview_layout_mode(owner)
    portrait_width_ratio = 0.707
    current_mode = getattr(owner, "pdf_page_view_mode", PAGE_VIEW_MODE_1_TALL)
    zoom_scale = max(0.2, float(getattr(owner, "pdf_preview_zoom", 1.0))) if current_mode == PAGE_VIEW_MODE_MANUAL else 1.0

    if mode == PAGE_VIEW_MODE_1_TALL:
        base_height = max_bitmap_height
    else:
        page_width = max_bitmap_width
        base_height = int(page_width / portrait_width_ratio)
    max_height = int(base_height * zoom_scale)

    return max(80, min(6000, max_height))


def _compute_pdf_page_fit_constraints(owner):
    panel_size = owner.pdf_pages_panel.GetClientSize()
    preview_size = owner.filePreview.GetClientSize()

    client_width = max(panel_size.x, preview_size.x - 24, 320)
    client_height = max(panel_size.y, preview_size.y - 24, 220)
    mode = _get_preview_layout_mode(owner)

    # Keep in sync with show_pdf_feed layout chrome.
    gap_width = 22
    page_panel_outer_margin = 6  # wx.ALL, 3 on page panel in parent sizer.
    page_panel_inner_margin = 6  # wx.ALL, 3 on bitmap in page panel sizer.
    page_panel_border = 4        # wx.BORDER_SIMPLE around page panel.
    label_height = max(20, int(owner.pdf_pages_panel.GetCharHeight()) + 8)
    fit_safety_margin = 24

    vscroll_width = wx.SystemSettings.GetMetric(wx.SYS_VSCROLL_X)
    if vscroll_width < 0:
        vscroll_width = 16
    hscroll_height = wx.SystemSettings.GetMetric(wx.SYS_HSCROLL_Y)
    if hscroll_height < 0:
        hscroll_height = 16

    per_page_horizontal = page_panel_outer_margin + page_panel_inner_margin + page_panel_border
    per_page_vertical = page_panel_inner_margin + page_panel_border + label_height + hscroll_height

    if mode == PAGE_VIEW_MODE_2_WIDE:
        available_width = client_width - (gap_width * 3) - (per_page_horizontal * 2) - vscroll_width + fit_safety_margin
        max_bitmap_width = max(80, available_width // 2)
    else:
        available_width = client_width - (gap_width * 2) - per_page_horizontal - vscroll_width + fit_safety_margin
        max_bitmap_width = max(80, available_width)

    if mode == PAGE_VIEW_MODE_1_TALL:
        available_height = client_height - per_page_vertical - fit_safety_margin
        max_bitmap_height = max(80, available_height)
    else:
        max_bitmap_height = 2000

    return max_bitmap_width, max_bitmap_height


def _get_dominant_page_width(previews):
    widths = []
    for _, bitmap in previews:
        if bitmap is not None and bitmap.IsOk():
            width = bitmap.GetSize().x
            if width > 0:
                widths.append(width)

    if not widths:
        return None

    counts = {}
    for width in widths:
        counts[width] = counts.get(width, 0) + 1

    dominant_width, dominant_count = max(counts.items(), key=lambda item: item[1])
    if dominant_count > 1:
        return dominant_width

    sorted_widths = sorted(widths)
    return sorted_widths[len(sorted_widths) // 2]


def _scale_bitmap_to_fit(bitmap, max_width, max_height, preferred_scale=None):
    if bitmap is None or not bitmap.IsOk():
        return bitmap

    width, height = bitmap.GetSize()
    if width <= 0 or height <= 0:
        return bitmap

    width_scale = float(max_width) / float(width) if max_width else 1.0
    height_scale = float(max_height) / float(height) if max_height else 1.0
    scale = min(width_scale, height_scale)
    if preferred_scale is not None:
        scale = min(scale, float(preferred_scale))
    if scale <= 0:
        return bitmap

    new_width = max(1, int(round(width * scale)))
    new_height = max(1, int(round(height * scale)))
    if new_width == width and new_height == height:
        return bitmap

    image = bitmap.ConvertToImage()
    if image is None or not image.IsOk():
        return bitmap

    scaled_image = image.Scale(new_width, new_height, wx.IMAGE_QUALITY_HIGH)
    if scaled_image is None or not scaled_image.IsOk():
        return bitmap

    return wx.Bitmap(scaled_image)


def select_pdf_page(owner, page_panel):
    if owner.selected_pdf_page_panel is page_panel:
        return

    if owner.selected_pdf_page_panel is not None:
        owner.selected_pdf_page_panel.SetBackgroundColour(wx.NullColour)
        owner.selected_pdf_page_panel.Refresh()

    owner.selected_pdf_page_panel = page_panel
    owner.selected_pdf_page_panel.SetBackgroundColour(wx.Colour(200, 230, 255))
    owner.selected_pdf_page_panel.Refresh()
    update_page_buttons_state(owner)


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
    update_page_buttons_state(owner)


def show_pdf_feed(owner, path):
    update_preview_toolbar_visibility(owner, is_pdf=True, is_image=False)
    sync_pdf_page_view_mode_controls(owner)
    with owner.busy_cursor():
        try:
            owner.current_pdf_path = path
            clear_pdf_feed(owner)
            max_height = _compute_pdf_preview_max_height(owner)
            page_count, shown_pages, previews = get_pdf_page_previews(path, max_height=max_height)
            max_bitmap_width, max_bitmap_height = _compute_pdf_page_fit_constraints(owner)
            mode = _get_preview_layout_mode(owner)
            current_mode = getattr(owner, "pdf_page_view_mode", PAGE_VIEW_MODE_1_TALL)
            zoom_scale = max(0.2, float(getattr(owner, "pdf_preview_zoom", 1.0))) if current_mode == PAGE_VIEW_MODE_MANUAL else 1.0

            max_bitmap_width = max(80, int(round(max_bitmap_width * zoom_scale)))
            max_bitmap_height = max(80, min(6000, int(round(max_bitmap_height * zoom_scale))))

            preferred_scale = None
            if mode in (PAGE_VIEW_MODE_1_WIDE, PAGE_VIEW_MODE_2_WIDE):
                dominant_width = _get_dominant_page_width(previews)
                if dominant_width and dominant_width > 0:
                    preferred_scale = float(max_bitmap_width) / float(dominant_width)

            gap_width = 22
            page_height = 180
            if previews:
                previews = [
                    (
                        page_no,
                        _scale_bitmap_to_fit(
                            bitmap,
                            max_bitmap_width,
                            max_bitmap_height,
                            preferred_scale=preferred_scale,
                        ),
                    )
                    for page_no, bitmap in previews
                ]
                tallest_preview_height = max(bitmap.GetSize().y for _, bitmap in previews if bitmap and bitmap.IsOk())
                page_height = max(160, tallest_preview_height)

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
    owner.pdf_pages_panel.Layout()
    owner.pdf_pages_panel.FitInside()
    owner.filePreview.Layout()


def on_pdf_page_select_wrapper(owner, event):
    """Wrapper to handle PDF page selection with owner context."""
    on_pdf_page_select(owner, event)


def show_file_preview(owner, path):
    owner.current_preview_path = path
    owner.selected_pdf_page_panel = None
    owner.current_image_preview = None
    owner.current_image_zoom = 1.0
    update_page_buttons_state(owner)
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


def _refresh_preview_after_pdf_save(owner, saved_path):
    owner.load_folder(owner.path_box.GetValue())
    show_file_preview(owner, saved_path)

    current_folder = os.path.normpath(owner.path_box.GetValue())
    saved_folder = os.path.normpath(os.path.dirname(saved_path))
    if current_folder != saved_folder:
        return

    target_name = os.path.basename(saved_path)
    for index in range(owner.list.GetItemCount()):
        state_mask = wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED
        owner.list.SetItemState(index, 0, state_mask)
        if owner.list.GetItemText(index) != target_name:
            continue
        owner.list.SetItemState(index, state_mask, state_mask)
        owner.list.EnsureVisible(index)
        break


def on_preview_save(event):
    owner = _get_preview_owner_from_event(event)
    if not owner or not is_pdf_file(owner.current_preview_path):
        wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
        return
    try:
        with owner.busy_cursor():
            save_pdf(owner.current_preview_path)
            update_pdf_save_button_state(owner)
            _refresh_preview_after_pdf_save(owner, owner.current_preview_path)
    except Exception as exc:
        wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)


def _prompt_preview_save_as_path(owner):
    current_path = getattr(owner, "current_preview_path", None)
    if not is_pdf_file(current_path):
        return None

    current_name = os.path.basename(current_path)
    dialog = wx.TextEntryDialog(owner, "Enter new file name:", tr("preview_save_as_button"), value=current_name)
    result = dialog.ShowModal()
    new_name = dialog.GetValue().strip() if result == wx.ID_OK else ""
    dialog.Destroy()

    if result != wx.ID_OK or not new_name:
        return None

    original_ext = os.path.splitext(current_name)[1]
    if original_ext and not os.path.splitext(new_name)[1]:
        new_name += original_ext

    new_path = os.path.join(os.path.dirname(current_path), new_name)
    if os.path.normpath(new_path) == os.path.normpath(current_path):
        return new_path

    if os.path.exists(new_path):
        dialog = wx.MessageDialog(
            owner,
            f"{new_name} already exists. Overwrite it?",
            tr("preview_save_as_button"),
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
        )
        should_overwrite = dialog.ShowModal() == wx.ID_YES
        dialog.Destroy()
        if not should_overwrite:
            return None

    return new_path


def on_preview_save_as(event):
    owner = _get_preview_owner_from_event(event)
    if not owner or not is_pdf_file(owner.current_preview_path):
        wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
        return

    new_path = _prompt_preview_save_as_path(owner)
    if not new_path:
        return

    try:
        with owner.busy_cursor():
            saved_path = save_pdf_as(owner.current_preview_path, new_path)
            update_pdf_save_button_state(owner)
            _refresh_preview_after_pdf_save(owner, saved_path)
    except Exception as exc:
        wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)


def on_preview_zoom_in(event):
    owner = _get_preview_owner_from_event(event)
    if owner:
        if is_pdf_file(owner.current_preview_path):
            with owner.busy_cursor():
                owner.pdf_preview_zoom = min(owner.pdf_preview_zoom * 1.25, 3.0)
                owner.pdf_page_view_mode = PAGE_VIEW_MODE_MANUAL
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
                owner.pdf_page_view_mode = PAGE_VIEW_MODE_MANUAL
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
    while owner is not None and not hasattr(owner, "preview_rotate_menu_btn"):
        owner = owner.GetParent() if hasattr(owner, "GetParent") else None

    if owner is not None:

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


def on_preview_auto_rotate(event):
    owner = _get_preview_owner_from_event(event)
    if owner:
        if not is_pdf_file(owner.current_preview_path):
            wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
            return
        try:
            with owner.busy_cursor():
                auto_rotate_pdf(owner.current_preview_path)
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
                    update_page_buttons_state(owner)
                    update_pdf_save_button_state(owner)
            except Exception as exc:
                wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)
        dialog.Destroy()


def _show_move_page_dialog(owner, page_count, default_source_page_no):
    dialog = wx.Dialog(owner, title=tr("move_page_dialog_title"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
    panel = wx.Panel(dialog)

    source_label = wx.StaticText(panel, label=tr("move_page_source_label"))
    source_spin = wx.SpinCtrl(panel, min=1, max=page_count, initial=default_source_page_no)

    destination_label = wx.StaticText(panel, label=tr("move_page_destination_label"))
    destination_choice = wx.Choice(
        panel,
        choices=[
            tr("move_page_at_begin"),
            tr("move_page_before"),
            tr("move_page_after"),
            tr("move_page_at_end"),
        ],
    )
    destination_choice.SetSelection(3)

    destination_page_label = wx.StaticText(panel, label=tr("move_page_destination_page_label"))
    destination_page_spin = wx.SpinCtrl(panel, min=1, max=page_count, initial=default_source_page_no)

    def update_destination_page_state(_):
        mode = destination_choice.GetSelection()
        needs_page_number = mode in (1, 2)
        destination_page_label.Enable(needs_page_number)
        destination_page_spin.Enable(needs_page_number)

    destination_choice.Bind(wx.EVT_CHOICE, update_destination_page_state)
    update_destination_page_state(None)

    fields = wx.FlexGridSizer(cols=2, hgap=8, vgap=8)
    fields.Add(source_label, 0, wx.ALIGN_CENTER_VERTICAL)
    fields.Add(source_spin, 1, wx.EXPAND)
    fields.Add(destination_label, 0, wx.ALIGN_CENTER_VERTICAL)
    fields.Add(destination_choice, 1, wx.EXPAND)
    fields.Add(destination_page_label, 0, wx.ALIGN_CENTER_VERTICAL)
    fields.Add(destination_page_spin, 1, wx.EXPAND)
    fields.AddGrowableCol(1, 1)

    ok_btn = wx.Button(panel, wx.ID_OK)
    cancel_btn = wx.Button(panel, wx.ID_CANCEL)
    button_sizer = wx.BoxSizer(wx.HORIZONTAL)
    button_sizer.AddStretchSpacer()
    button_sizer.Add(ok_btn, 0, wx.RIGHT, 8)
    button_sizer.Add(cancel_btn, 0)

    root_sizer = wx.BoxSizer(wx.VERTICAL)
    root_sizer.Add(fields, 1, wx.EXPAND | wx.ALL, 12)
    root_sizer.Add(button_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
    panel.SetSizer(root_sizer)

    dialog_sizer = wx.BoxSizer(wx.VERTICAL)
    dialog_sizer.Add(panel, 1, wx.EXPAND)
    dialog.SetSizerAndFit(dialog_sizer)

    if dialog.ShowModal() != wx.ID_OK:
        dialog.Destroy()
        return None

    result = {
        "source_page_no": source_spin.GetValue(),
        "destination_mode": destination_choice.GetSelection(),
        "destination_page_no": destination_page_spin.GetValue(),
    }
    dialog.Destroy()
    return result


def _resolve_move_destination_index(page_count, destination_mode, destination_page_no):
    if destination_mode == 0:
        return 0
    if destination_mode == 1:
        return max(0, min(page_count - 1, destination_page_no - 1))
    if destination_mode == 2:
        return max(0, min(page_count - 1, destination_page_no))
    return page_count - 1


def on_preview_move_page(event):
    owner = _get_preview_owner_from_event(event)
    if owner is None or not is_pdf_file(owner.current_preview_path):
        wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
        return

    try:
        page_count = get_pdf_page_count(owner.current_preview_path)
    except Exception as exc:
        wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)
        return

    if page_count <= 0:
        return

    selected_index = get_selected_pdf_page_index(owner)
    default_source_page_no = (selected_index + 1) if selected_index is not None else 1
    dialog_result = _show_move_page_dialog(owner, page_count, default_source_page_no)
    if dialog_result is None:
        return

    source_index = dialog_result["source_page_no"] - 1
    destination_index = _resolve_move_destination_index(
        page_count,
        dialog_result["destination_mode"],
        dialog_result["destination_page_no"],
    )

    if source_index == destination_index:
        return

    try:
        with owner.busy_cursor():
            move_pdf_page(owner.current_preview_path, source_index, destination_index)
            show_pdf_feed(owner, owner.current_preview_path)
            update_page_buttons_state(owner)
            update_pdf_save_button_state(owner)
    except Exception as exc:
        wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)


def on_preview_optimize(event):
    ## Auto-rotate the PDF before optimizing to avoid cutting page.
    on_preview_auto_rotate(event)

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


def on_preview_adjust_page_width(event):
    owner = _get_preview_owner_from_event(event)
    if owner:
        if not is_pdf_file(owner.current_preview_path):
            wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
            return
        try:
            with owner.busy_cursor():
                adjust_page_width(owner.current_preview_path)
                ## save_pdf(owner.current_preview_path)
                ## owner.refresh_list_item_size(owner.current_preview_path)
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

    build_save_menu(owner, menu)
    menu.AppendSeparator()
    zoom_in_item = menu.Append(-1, tr("preview_zoom_in_button"))
    icon_manager.set_menu_icon(zoom_in_item, wx.ART_PLUS)
    zoom_out_item = menu.Append(-1, tr("preview_zoom_out_button"))
    icon_manager.set_menu_icon(zoom_out_item, wx.ART_MINUS)
    menu.AppendSeparator()
    build_page_view_mode_menu(owner, menu)
    menu.AppendSeparator()
    rotation_menu_items = build_rotation_menu(owner, menu)
    menu.AppendSeparator()
    move_page_item = menu.Append(-1, tr("preview_move_page_button"))
    icon_manager.set_menu_icon(move_page_item, wx.ART_GO_FORWARD)
    remove_page_item = menu.Append(-1, tr("preview_remove_page_button"))
    icon_manager.set_menu_icon2(remove_page_item, "delete")
    menu.AppendSeparator()
    adjust_page_width_item = menu.Append(-1, tr("preview_adjust_page_width_button"))
    icon_manager.set_menu_icon(adjust_page_width_item, wx.ART_REPORT_VIEW)
    optimize_item = menu.Append(-1, tr("preview_optimize_button"))
    icon_manager.set_menu_icon2(optimize_item, "ok")
 
    remove_page_item.Enable(is_pdf_file(owner.current_preview_path) and get_selected_pdf_page_index(owner) is not None)
    move_page_item.Enable(is_pdf_file(owner.current_preview_path))

    ## owner.Bind(wx.EVT_MENU, on_preview_edit, edit_item)
    ## owner.Bind(wx.EVT_MENU, on_preview_delete, delete_item)
    owner.Bind(wx.EVT_MENU, on_preview_zoom_in, zoom_in_item)
    owner.Bind(wx.EVT_MENU, on_preview_zoom_out, zoom_out_item)
    owner.Bind(wx.EVT_MENU, on_preview_move_page, move_page_item)
    owner.Bind(wx.EVT_MENU, lambda evt: on_preview_remove_page(evt, owner=owner), remove_page_item)
    owner.Bind(wx.EVT_MENU, on_preview_optimize, optimize_item)
    owner.Bind(wx.EVT_MENU, on_preview_adjust_page_width, adjust_page_width_item)

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
