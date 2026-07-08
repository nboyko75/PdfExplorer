import os
import shutil

import wx

from localization import tr
from file_operations.pdf_utils import discard_pdf_changes, is_pdf_file
import controls.file_preview as file_preview


def _get_sort_header_bitmap(direction):
    art_id = wx.ART_GO_UP if direction > 0 else wx.ART_GO_DOWN
    bitmap = wx.ArtProvider.GetBitmap(art_id, wx.ART_MENU, (16, 16))
    if bitmap is not None and bitmap.IsOk():
        return bitmap
    return None


def update_list_sort_header_icons(owner):
    sort_column = getattr(owner, "list_sort_column", None)
    sort_direction = int(getattr(owner, "list_sort_direction", 0) or 0)
    sort_bitmap = _get_sort_header_bitmap(sort_direction) if sort_column is not None and sort_direction in (-1, 1) else None

    for index in range(owner.list.GetColumnCount()):
        column = owner.list.GetColumn(index)
        column.SetMask(wx.LIST_MASK_TEXT)
        if hasattr(column, "SetImage"):
            column.SetImage(-1)

        if index == sort_column and sort_bitmap is not None:
            column.SetMask(wx.LIST_MASK_TEXT | wx.LIST_MASK_IMAGE)
            if hasattr(column, "SetImage"):
                column.SetImage(sort_bitmap)

        owner.list.SetColumn(index, column)


def refresh_list_item_size(owner, path):
    if not isinstance(path, str) or not os.path.isfile(path):
        return False

    current_folder = os.path.normpath(owner.path_box.GetValue())
    item_folder = os.path.normpath(os.path.dirname(path))
    if current_folder != item_folder:
        return False

    target_name = os.path.basename(path)
    try:
        size_text = f"{os.path.getsize(path)//1024} {tr('file_size_unit_kb')}"
    except Exception:
        size_text = ""

    for index in range(owner.list.GetItemCount()):
        if owner.list.GetItemText(index) == target_name:
            owner.list.SetItem(index, 2, size_text)
            return True

    return False


def on_list_select(owner, event):
    if getattr(owner, "_restoring_list_selection", False):
        return

    index = event.GetIndex()
    name = owner.list.GetItemText(index)
    path = os.path.join(owner.path_box.GetValue(), name)

    previous_path = owner.current_preview_path
    if not file_preview.confirm_preview_change(owner, path):
        wx.CallAfter(file_preview.restore_list_selection, owner, previous_path)
        return

    file_preview.show_file_preview(owner, path)


def on_right_click(owner, event):
    hit_index, _ = owner.list.HitTest(event.GetPosition())
    if hit_index != wx.NOT_FOUND:
        owner.list.SetItemState(
            hit_index,
            wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
            wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
        )

    menu = wx.Menu()

    open_item = menu.Append(-1, tr("context_open"))
    rename_item = menu.Append(-1, tr("context_rename"))
    delete_item = menu.Append(-1, tr("context_delete"))

    def set_menu_icon(item, art_id=None):
        bitmap = None
        if art_id is not None:
            bitmap = wx.ArtProvider.GetBitmap(art_id, wx.ART_MENU, (16, 16))
        if bitmap is not None and bitmap.IsOk():
            item.SetBitmap(bitmap)

    set_menu_icon(open_item, art_id=wx.ART_FIND)
    set_menu_icon(rename_item, art_id=wx.ART_EDIT)
    set_menu_icon(delete_item, art_id=wx.ART_DELETE)

    selected_path = get_selected_list_path(owner)
    can_act_on_selection = bool(selected_path)
    open_item.Enable(can_act_on_selection)
    rename_item.Enable(can_act_on_selection)
    delete_item.Enable(can_act_on_selection)

    owner.Bind(wx.EVT_MENU, owner.on_list_open, open_item)
    owner.Bind(wx.EVT_MENU, owner.on_list_rename, rename_item)
    owner.Bind(wx.EVT_MENU, owner.on_list_delete, delete_item)

    owner.list.PopupMenu(menu)
    menu.Destroy()


def get_selected_list_path(owner):
    index = owner.list.GetFirstSelected()
    if index == wx.NOT_FOUND:
        return None

    name = owner.list.GetItemText(index)
    return os.path.join(owner.path_box.GetValue(), name)


def on_list_open(owner, _):
    path = get_selected_list_path(owner)
    if not path:
        return

    if os.path.isdir(path):
        owner.open_path(path)
        return

    if os.path.isfile(path):
        try:
            os.startfile(path)
        except Exception as exc:
            wx.MessageBox(str(exc), tr("app_title"), style=wx.OK | wx.ICON_ERROR)


def on_list_rename(owner, _):
    path = get_selected_list_path(owner)
    if not path:
        return

    current_name = os.path.basename(path)
    dialog = wx.TextEntryDialog(owner, tr("context_rename"), tr("context_rename"), value=current_name)
    result = dialog.ShowModal()
    new_name = dialog.GetValue().strip() if result == wx.ID_OK else ""
    dialog.Destroy()

    if result != wx.ID_OK or not new_name or new_name == current_name:
        return

    new_path = os.path.join(os.path.dirname(path), new_name)
    try:
        os.rename(path, new_path)
        owner.load_folder(owner.path_box.GetValue())
    except Exception as exc:
        wx.MessageBox(str(exc), tr("app_title"), style=wx.OK | wx.ICON_ERROR)


def on_list_delete(owner, _):
    path = get_selected_list_path(owner)
    if not path:
        return

    dialog = wx.MessageDialog(
        owner,
        tr("confirm_delete", path=path),
        tr("context_delete"),
        wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
    )
    should_delete = dialog.ShowModal() == wx.ID_YES
    dialog.Destroy()

    if not should_delete:
        return

    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            if is_pdf_file(path):
                discard_pdf_changes(path)
            os.remove(path)

        if owner.current_preview_path and os.path.normpath(owner.current_preview_path) == os.path.normpath(path):
            file_preview.show_file_preview(owner, None)

        owner.load_folder(owner.path_box.GetValue())
    except Exception as exc:
        wx.MessageBox(str(exc), tr("app_title"), style=wx.OK | wx.ICON_ERROR)


def on_open_item(owner, event):
    name = event.GetText()
    path = os.path.join(owner.path_box.GetValue(), name)

    if os.path.isdir(path):
        owner.open_path(path)


def on_list_column_click(owner, event):
    column = event.GetColumn()

    if owner.list_sort_column != column:
        owner.list_sort_column = column
        owner.list_sort_direction = 1
    elif owner.list_sort_direction == 1:
        owner.list_sort_direction = -1
    elif owner.list_sort_direction == -1:
        owner.list_sort_column = None
        owner.list_sort_direction = 0
    else:
        owner.list_sort_direction = 1

    update_list_sort_header_icons(owner)
    owner.load_folder(owner.path_box.GetValue())
