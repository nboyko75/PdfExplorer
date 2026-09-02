import os
import wx

from controls.window_tools import set_column_image_on_left
from localization import tr
import file_operations.image_utils as image_utils


def build_favorite_panel(owner, parent):
    owner.favorite_panel = wx.Panel(parent)
    owner.favorite_move_up_btn = image_utils.create_bitmap_button(
        owner.favorite_panel,
        wx.ART_GO_UP,
        tr("favorite_move_up_button"),
        icon_size=(16, 16),
        button_size=(24, 24),
    )
    owner.favorite_move_down_btn = image_utils.create_bitmap_button(
        owner.favorite_panel,
        wx.ART_GO_DOWN,
        tr("favorite_move_down_button"),
        icon_size=(16, 16),
        button_size=(24, 24),
    )
    owner.favorite_list = wx.ListCtrl(owner.favorite_panel, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
    owner.favorite_list.SetMinSize((0, 0))
    owner.favorite_image_list = wx.ImageList(16, 16)

    favorite_header_bitmap = owner.icon_manager.get_bitmap("favorite")
    if favorite_header_bitmap is not None:
        owner.favorite_header_icon_index = owner.favorite_image_list.Add(favorite_header_bitmap)
    else:
        owner.favorite_header_icon_index = -1

    folder_bitmap = wx.ArtProvider.GetBitmap(wx.ART_FOLDER, wx.ART_OTHER, (16, 16))
    if folder_bitmap.IsOk():
        owner.favorite_folder_icon_index = owner.favorite_image_list.Add(folder_bitmap)
    else:
        owner.favorite_folder_icon_index = -1

    owner.favorite_list.SetImageList(owner.favorite_image_list, wx.IMAGE_LIST_SMALL)
    owner.favorite_list.InsertColumn(0, tr("favorite_column_header"), width=200)
    if getattr(owner, "favorite_header_icon_index", -1) >= 0:
        owner.favorite_list.SetColumnImage(0, owner.favorite_header_icon_index)
    wx.CallAfter(set_column_image_on_left, owner.favorite_list, 0)
    
    owner.favorite_list.Bind(wx.EVT_LIST_ITEM_SELECTED, owner.on_favorite_list_select)
    owner.favorite_list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, owner.on_favorite_list_activate)
    owner.favorite_list.Bind(wx.EVT_LIST_BEGIN_DRAG, owner.on_favorite_begin_drag)
    owner.favorite_list.Bind(wx.EVT_LEFT_UP, owner.on_favorite_end_drag)
    owner.favorite_list.Bind(wx.EVT_RIGHT_DOWN, owner.on_favorite_right_click)

    favorite_header = wx.BoxSizer(wx.HORIZONTAL)
    favorite_header.Add(owner.favorite_move_up_btn, 0, wx.RIGHT, 3)
    favorite_header.Add(owner.favorite_move_down_btn, 0, wx.RIGHT, 3)

    favorite_sizer = wx.BoxSizer(wx.VERTICAL)
    favorite_sizer.Add(favorite_header, 0, wx.EXPAND | wx.ALL, 4)
    favorite_sizer.Add(owner.favorite_list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)
    owner.favorite_panel.SetSizer(favorite_sizer)

    owner.favorite_move_up_btn.Bind(wx.EVT_BUTTON, owner.on_move_favorite_up)
    owner.favorite_move_down_btn.Bind(wx.EVT_BUTTON, owner.on_move_favorite_down)

    refresh_favorite_list(owner)
    return owner.favorite_panel


def _apply_favorite_list_layout(owner):
    if owner.favorite_list is None or owner.favorite_panel is None:
        return
    panel_size = owner.favorite_panel.GetSize()
    panel_width = panel_size.GetWidth() if hasattr(panel_size, "GetWidth") else 0
    if panel_width > 0:
        owner.favorite_list.SetColumnWidth(0, max(80, panel_width - 16))
    if hasattr(owner.favorite_list, "Layout"):
        owner.favorite_list.Layout()


def refresh_favorite_list(owner):
    if owner.favorite_list is None:
        return
    owner.favorite_list.DeleteAllItems()
    if not owner.favorite_paths:
        _apply_favorite_list_layout(owner)
        return

    for index, favorite_path in enumerate(owner.favorite_paths):
        display_name = os.path.basename(favorite_path) or favorite_path
        item_index = owner.favorite_list.InsertItem(index, display_name)
        if getattr(owner, "favorite_folder_icon_index", -1) >= 0:
            owner.favorite_list.SetItemImage(item_index, owner.favorite_folder_icon_index)

    _apply_favorite_list_layout(owner)


def apply_favorite_panel_position(owner, sash_position=None):
    if owner.favorite_splitter is None:
        return
    if owner.favorite_splitter.IsSplit():
        owner.favorite_splitter.Unsplit()

    if sash_position is None:
        try:
            current_sash = owner.favorite_splitter.GetSashPosition()
        except Exception:
            current_sash = 180
        sash_position = current_sash

    if owner.favorite_panel_above_tree:
        owner.favorite_splitter.SplitHorizontally(owner.favorite_panel, owner.tree, sash_position)
    else:
        owner.favorite_splitter.SplitHorizontally(owner.tree, owner.favorite_panel, sash_position)

    if owner.favorite_panel is not None:
        owner.favorite_move_up_btn.Show(not owner.favorite_panel_above_tree)
        owner.favorite_move_down_btn.Show(owner.favorite_panel_above_tree)
        if hasattr(owner.favorite_panel, "Layout"):
            owner.favorite_panel.Layout()
        _apply_favorite_list_layout(owner)

    if owner.favorite_splitter is not None:
        owner.favorite_splitter.SetSashPosition(sash_position)


def toggle_favorite_panel_position(owner, panel_above_tree):
    if owner.favorite_splitter is None:
        return

    previous_above_tree = bool(getattr(owner, "favorite_panel_above_tree", False))
    current_sash = 180
    try:
        current_sash = int(owner.favorite_splitter.GetSashPosition())
    except Exception:
        current_sash = 180

    target_sash = current_sash
    target_above_tree = bool(panel_above_tree)
    if previous_above_tree != target_above_tree:
        try:
            splitter_height = int(owner.favorite_splitter.GetSize().GetHeight())
        except Exception:
            splitter_height = 0
        if splitter_height > 0:
            target_sash = max(0, splitter_height - current_sash)

    owner.favorite_panel_above_tree = target_above_tree
    apply_favorite_panel_position(owner, sash_position=target_sash)
    owner.save_splitter_positions()


def on_favorite_begin_drag(owner, event):
    owner._favorite_drag_source_index = event.GetIndex()


def on_favorite_end_drag(owner, event):
    if not hasattr(owner, "_favorite_drag_source_index"):
        return

    from_index = owner._favorite_drag_source_index
    target_index = wx.NOT_FOUND
    if owner.favorite_list is not None:
        try:
            target_index, _ = owner.favorite_list.HitTest(event.GetPosition())
        except Exception:
            target_index = wx.NOT_FOUND

    if target_index == wx.NOT_FOUND:
        target_index = owner.favorite_list.GetItemCount() - 1 if owner.favorite_list is not None else -1

    if owner.favorite_list is not None and hasattr(owner.favorite_list, "GetItemCount"):
        target_index = max(0, min(target_index, owner.favorite_list.GetItemCount() - 1))

    owner._reorder_favorite_paths(from_index, target_index)
    if hasattr(owner, "_favorite_drag_source_index"):
        del owner._favorite_drag_source_index


def on_favorite_right_click(owner, event):
    if owner.favorite_list is None:
        return
    try:
        index, _ = owner.favorite_list.HitTest(event.GetPosition())
        if index != wx.NOT_FOUND:
            owner.favorite_list.Select(index)
    except Exception:
        pass
    menu = wx.Menu()
    remove_item = menu.Append(-1, f"{tr('favorite_remove_menu_item')}\tDel")
    owner.icon_manager.set_menu_icon2(remove_item, "remove_from_favorites")
    remove_item.Enable(owner.favorite_list.GetFirstSelected() != wx.NOT_FOUND)
    owner.Bind(wx.EVT_MENU, owner.on_remove_favorite_from_context, remove_item)
    owner.favorite_list.PopupMenu(menu)
    menu.Destroy()


def on_remove_favorite_from_context(owner, _):
    selected_index = owner.favorite_list.GetFirstSelected() if owner.favorite_list is not None else wx.NOT_FOUND
    if selected_index == wx.NOT_FOUND or not (0 <= selected_index < len(owner.favorite_paths)):
        return
    owner._remove_favorite_path(owner.favorite_paths[selected_index])
