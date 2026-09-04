import os
import wx

from controls.window_tools import set_column_image_on_left
from localization import tr
import file_operations.image_utils as image_utils


STANDARD_SHORTCUT_DEFINITIONS = (
    {"key": "desktop", "label": "Desktop", "default": True},
    {"key": "documents", "label": "Documents", "default": True},
    {"key": "download", "label": "Downloads", "default": False},
    {"key": "images", "label": "Images", "default": False},
    {"key": "music", "label": "Music", "default": False},
    {"key": "video", "label": "Videos", "default": False},
    {"key": "recycle_bin", "label": "Recycle Bin", "default": True},
)


def _standard_shortcut_path_for_key(key):
    home_dir = os.path.expanduser("~")
    mapping = {
        "desktop": os.path.join(home_dir, "Desktop"),
        "documents": os.path.join(home_dir, "Documents"),
        "download": os.path.join(home_dir, "Downloads"),
        "images": os.path.join(home_dir, "Pictures"),
        "music": os.path.join(home_dir, "Music"),
        "video": os.path.join(home_dir, "Videos"),
        "recycle_bin": os.path.join(home_dir, "Desktop", "Recycle Bin"),
    }
    path = mapping.get(key, "")
    if path and os.path.isdir(path):
        return os.path.normpath(path)
    if key == "recycle_bin":
        try:
            import win32com.client
            shell = win32com.client.Dispatch("WScript.Shell")
            desktop_path = shell.SpecialFolders("Desktop")
            if desktop_path:
                recycle_bin_path = os.path.join(desktop_path, "Recycle Bin")
                if os.path.isdir(recycle_bin_path):
                    return os.path.normpath(recycle_bin_path)
        except Exception:
            pass
    return os.path.normpath(path) if path else ""


def _standard_shortcut_entries(owner):
    shortcuts = []
    for item in STANDARD_SHORTCUT_DEFINITIONS:
        key = item["key"]
        label = item["label"]
        if key == "recycle_bin":
            label = tr("favorite_shortcut_recycle_bin") if tr("favorite_shortcut_recycle_bin") != "favorite_shortcut_recycle_bin" else "Recycle Bin"
        elif key == "desktop":
            label = tr("favorite_shortcut_desktop") if tr("favorite_shortcut_desktop") != "favorite_shortcut_desktop" else "Desktop"
        elif key == "documents":
            label = tr("favorite_shortcut_documents") if tr("favorite_shortcut_documents") != "favorite_shortcut_documents" else "Documents"
        elif key == "download":
            label = tr("favorite_shortcut_downloads") if tr("favorite_shortcut_downloads") != "favorite_shortcut_downloads" else "Downloads"
        elif key == "images":
            label = tr("favorite_shortcut_images") if tr("favorite_shortcut_images") != "favorite_shortcut_images" else "Images"
        elif key == "music":
            label = tr("favorite_shortcut_music") if tr("favorite_shortcut_music") != "favorite_shortcut_music" else "Music"
        elif key == "video":
            label = tr("favorite_shortcut_video") if tr("favorite_shortcut_video") != "favorite_shortcut_video" else "Videos"
        shortcuts.append({
            "key": key,
            "label": label,
            "path": _standard_shortcut_path_for_key(key),
        })
    return shortcuts


def _visible_standard_shortcuts(owner):
    if owner is None:
        return []
    visibility = getattr(owner, "standard_shortcuts_visibility", {})
    visible = []
    for shortcut in _standard_shortcut_entries(owner):
        key = shortcut["key"]
        default_visible = shortcut["label"] in {"Desktop", "Documents", "Recycle Bin"}
        if bool(visibility.get(key, default_visible)):
            visible.append(shortcut)
    return visible


def _sync_standard_shortcuts_toggle_button(owner, button):
    if button is None:
        return
    icon_manager = getattr(owner, "icon_manager", None)
    if icon_manager is None:
        try:
            icon_manager = image_utils.ensure_owner_icon_manager(owner)
        except Exception:
            return
    is_visible = bool(getattr(owner, "standard_shortcuts_visible", False))
    if is_visible:
        tooltip = tr("standard_shortcuts_toggle_hide_tooltip")
        bitmap_name = "standard_shortcuts_pressed"
    else:
        tooltip = tr("standard_shortcuts_toggle_show_tooltip")
        bitmap_name = "standard_shortcuts"

    bitmap = None
    try:
        if icon_manager is not None:
            bitmap = icon_manager.get_bitmap(bitmap_name, size=(16, 16))
    except Exception:
        bitmap = None

    if bitmap is None:
        return
    try:
        button.SetBitmap(bitmap)
        if hasattr(button, "SetToolTip"):
            button.SetToolTip(tooltip)
    except Exception:
        pass


def _build_standard_shortcuts_toggle_button(owner, parent):
    icon_manager = getattr(owner, "icon_manager", None) or image_utils.ensure_owner_icon_manager(owner)
    try:
        bitmap = icon_manager.get_bitmap("standard_shortcuts", size=(16, 16)) if icon_manager is not None else None
        button = wx.BitmapButton(parent, bitmap=bitmap, size=(24, 24)) if bitmap is not None else wx.Button(parent, label=tr("favorite_shortcuts_button"))
        if bitmap is not None:
            button.SetToolTip(tr("favorite_shortcuts_button"))
            _sync_standard_shortcuts_toggle_button(owner, button)
        return button
    except Exception:
        class _FallbackToggleButton:
            def __init__(self):
                self._label = tr("favorite_shortcuts_button")
            def SetLabel(self, label):
                self._label = label
            def Bind(self, *args, **kwargs):
                return None
            def Show(self, *args, **kwargs):
                return None
            def Hide(self, *args, **kwargs):
                return None
        return _FallbackToggleButton()


def build_favorite_panel(owner, parent):
    owner.icon_manager = image_utils.ensure_owner_icon_manager(owner)

    owner.favorite_panel = wx.Panel(parent)
    owner.favorite_move_up_btn = image_utils.create_bitmap_button2(
        owner.favorite_panel,
        owner.icon_manager,
        "double_up",
        tr("favorite_move_up_button"),
        icon_size=(16, 16),
        button_size=(24, 24),
    )
    owner.favorite_move_down_btn = image_utils.create_bitmap_button2(
        owner.favorite_panel,
        owner.icon_manager,
        "double_down",
        tr("favorite_move_down_button"),
        icon_size=(16, 16),
        button_size=(24, 24),
    )
    owner.standard_shortcuts_toggle_btn = _build_standard_shortcuts_toggle_button(owner, owner.favorite_panel)
    owner.favorite_content_splitter = wx.SplitterWindow(owner.favorite_panel)
    owner.favorite_content_splitter.SetMinimumPaneSize(40)

    owner.standard_shortcuts_panel = wx.Panel(owner.favorite_content_splitter)
    owner.standard_shortcuts_panel.SetMinSize((0, 0))
    owner.standard_shortcuts_move_up_btn = image_utils.create_bitmap_button(
        owner.standard_shortcuts_panel,
        wx.ART_GO_UP,
        "",
        icon_size=(16, 16),
        button_size=(24, 24),
    )
    owner.standard_shortcuts_move_down_btn = image_utils.create_bitmap_button(
        owner.standard_shortcuts_panel,
        wx.ART_GO_DOWN,
        "",
        icon_size=(16, 16),
        button_size=(24, 24),
    )
    owner.standard_shortcuts_move_up_btn.Hide()
    owner.standard_shortcuts_move_down_btn.Hide()

    owner.favorite_list = wx.ListCtrl(owner.favorite_content_splitter, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
    owner.favorite_list.SetMinSize((0, 0))
    owner.favorite_image_list = wx.ImageList(16, 16)
    owner.standard_shortcuts_image_list = wx.ImageList(16, 16)

    try:
        owner.standard_shortcuts_list = wx.ListCtrl(owner.standard_shortcuts_panel, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
    except Exception:
        owner.standard_shortcuts_list = getattr(owner, "standard_shortcuts_list", None) or type("_FallbackList", (), {"SetMinSize": lambda self, *args, **kwargs: None, "Hide": lambda self, *args, **kwargs: None, "Show": lambda self, *args, **kwargs: None, "DeleteAllItems": lambda self, *args, **kwargs: None, "InsertItem": lambda self, *args, **kwargs: 0, "SetItemImage": lambda self, *args, **kwargs: None, "Layout": lambda self, *args, **kwargs: None, "SetColumnWidth": lambda self, *args, **kwargs: None, "PopupMenu": lambda self, *args, **kwargs: None, "Bind": lambda self, *args, **kwargs: None, "Select": lambda self, *args, **kwargs: None, "HitTest": lambda self, *args, **kwargs: (wx.NOT_FOUND, wx.DefaultPosition), "GetFirstSelected": lambda self, *args, **kwargs: wx.NOT_FOUND, "GetItemCount": lambda self, *args, **kwargs: 0})()
    owner.standard_shortcuts_list.SetMinSize((0, 0))
    owner.standard_shortcuts_visible = bool(getattr(owner, "standard_shortcuts_visible", False))
    if owner.standard_shortcuts_visible:
        owner.standard_shortcuts_list.Show()
    else:
        owner.standard_shortcuts_list.Hide()

    owner.favorite_row_move_up_btn = image_utils.create_bitmap_button(
        owner.favorite_panel,
        wx.ART_GO_UP,
        "",
        icon_size=(16, 16),
        button_size=(24, 24),
    )
    owner.favorite_row_move_down_btn = image_utils.create_bitmap_button(
        owner.favorite_panel,
        wx.ART_GO_DOWN,
        "",
        icon_size=(16, 16),
        button_size=(24, 24),
    )
    owner.favorite_row_move_up_btn.Hide()
    owner.favorite_row_move_down_btn.Hide()

    owner.icon_manager = image_utils.ensure_owner_icon_manager(owner)
    favorite_header_bitmap = None
    if owner.icon_manager is not None:
        try:
            favorite_header_bitmap = owner.icon_manager.get_bitmap("favorite")
        except (KeyError, AttributeError):
            favorite_header_bitmap = None
    if favorite_header_bitmap is not None:
        owner.favorite_header_icon_index = owner.favorite_image_list.Add(favorite_header_bitmap)
    else:
        owner.favorite_header_icon_index = -1

    standard_shortcuts_bitmap = None
    if owner.icon_manager is not None:
        try:
            standard_shortcuts_bitmap = owner.icon_manager.get_bitmap("standard_shortcuts", size=(16, 16))
        except (KeyError, AttributeError):
            standard_shortcuts_bitmap = None
    if standard_shortcuts_bitmap is not None:
        owner.standard_shortcuts_header_icon_index = owner.standard_shortcuts_image_list.Add(standard_shortcuts_bitmap)
    else:
        owner.standard_shortcuts_header_icon_index = -1

    folder_bitmap = wx.ArtProvider.GetBitmap(wx.ART_FOLDER, wx.ART_OTHER, (16, 16))
    if folder_bitmap.IsOk():
        owner.favorite_folder_icon_index = owner.favorite_image_list.Add(folder_bitmap)
    else:
        owner.favorite_folder_icon_index = -1

    owner.favorite_list.SetImageList(owner.favorite_image_list, wx.IMAGE_LIST_SMALL)
    owner.favorite_list.InsertColumn(0, tr("favorite_column_header"), width=200)
    owner.standard_shortcuts_list.SetImageList(owner.standard_shortcuts_image_list, wx.IMAGE_LIST_SMALL)
    owner.standard_shortcuts_list.InsertColumn(0, tr("favorite_shortcuts_button"), width=200)
    if getattr(owner, "favorite_header_icon_index", -1) >= 0:
        owner.favorite_list.SetColumnImage(0, owner.favorite_header_icon_index)
    if getattr(owner, "standard_shortcuts_header_icon_index", -1) >= 0:
        owner.standard_shortcuts_list.SetColumnImage(0, owner.standard_shortcuts_header_icon_index)
    try:
        if wx.GetApp() is not None:
            wx.CallAfter(set_column_image_on_left, owner.favorite_list, 0)
            wx.CallAfter(set_column_image_on_left, owner.standard_shortcuts_list, 0)
    except Exception:
        pass

    owner.favorite_list.Bind(wx.EVT_LIST_ITEM_SELECTED, owner.on_favorite_list_select)
    owner.favorite_list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, owner.on_favorite_list_activate)
    owner.favorite_list.Bind(wx.EVT_LIST_BEGIN_DRAG, owner.on_favorite_begin_drag)
    owner.favorite_list.Bind(wx.EVT_LEFT_UP, owner.on_favorite_end_drag)
    owner.favorite_list.Bind(wx.EVT_RIGHT_DOWN, owner.on_favorite_right_click)
    owner.favorite_list.Bind(wx.EVT_LIST_ITEM_SELECTED, lambda event: sync_favorite_row_action_buttons(owner))
    owner.favorite_list.Bind(wx.EVT_LIST_ITEM_DESELECTED, lambda event: sync_favorite_row_action_buttons(owner))
    owner.favorite_content_splitter.Bind(wx.EVT_SPLITTER_SASH_POS_CHANGED, lambda event: on_favorite_content_splitter_sash_changed(owner, event))

    favorite_panel_resize_handler = getattr(owner, "on_favorite_panel_resize", None)
    if favorite_panel_resize_handler is None:
        favorite_panel_resize_handler = lambda event: on_favorite_panel_resize(owner, event)
    owner.favorite_panel.Bind(wx.EVT_SIZE, favorite_panel_resize_handler)

    favorite_header = wx.BoxSizer(wx.HORIZONTAL)
    favorite_header.Add(owner.favorite_move_up_btn, 0, wx.RIGHT, 3)
    favorite_header.Add(owner.favorite_move_down_btn, 0, wx.RIGHT, 3)
    favorite_header.Add(owner.favorite_row_move_up_btn, 0, wx.RIGHT, 3)
    favorite_header.Add(owner.favorite_row_move_down_btn, 0, wx.RIGHT, 3)
    favorite_header.AddStretchSpacer(1)
    favorite_header.Add(owner.standard_shortcuts_toggle_btn, 0, wx.LEFT, 3)

    standard_shortcuts_header = wx.BoxSizer(wx.HORIZONTAL)
    standard_shortcuts_header.Add(owner.standard_shortcuts_move_up_btn, 0, wx.RIGHT, 3)
    standard_shortcuts_header.Add(owner.standard_shortcuts_move_down_btn, 0, wx.RIGHT, 3)
    standard_shortcuts_header.AddStretchSpacer(1)

    standard_shortcuts_sizer = wx.BoxSizer(wx.VERTICAL)
    standard_shortcuts_sizer.Add(standard_shortcuts_header, 0, wx.EXPAND | wx.ALL, 4)
    standard_shortcuts_sizer.Add(owner.standard_shortcuts_list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)
    owner.standard_shortcuts_panel.SetSizer(standard_shortcuts_sizer)

    owner.favorite_content_splitter.SplitHorizontally(
        owner.favorite_list,
        owner.standard_shortcuts_panel,
        max(40, min(int(getattr(owner, "favorite_standard_shortcuts_splitter_sash", 120)), 400)),
    )
    if hasattr(owner, "favorite_standard_shortcuts_splitter_sash"):
        owner.favorite_content_splitter.SetSashPosition(max(40, min(int(owner.favorite_standard_shortcuts_splitter_sash), 400)))
    if not owner.standard_shortcuts_visible:
        try:
            if owner.favorite_content_splitter.IsSplit():
                owner.favorite_content_splitter.Unsplit(owner.standard_shortcuts_panel)
        except Exception:
            pass

    favorite_sizer = wx.BoxSizer(wx.VERTICAL)
    favorite_sizer.Add(favorite_header, 0, wx.EXPAND | wx.ALL, 4)
    favorite_sizer.Add(owner.favorite_content_splitter, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)
    owner.favorite_panel.SetSizer(favorite_sizer)

    owner.favorite_move_up_btn.Bind(wx.EVT_BUTTON, owner.on_move_favorite_up)
    owner.favorite_move_down_btn.Bind(wx.EVT_BUTTON, owner.on_move_favorite_down)
    owner.standard_shortcuts_move_up_btn.Bind(wx.EVT_BUTTON, owner.on_move_favorite_up)
    owner.standard_shortcuts_move_down_btn.Bind(wx.EVT_BUTTON, owner.on_move_favorite_down)
    owner.standard_shortcuts_toggle_btn.Bind(wx.EVT_BUTTON, owner.on_toggle_standard_shortcuts)
    owner.standard_shortcuts_list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, owner.on_standard_shortcut_list_activate)
    owner.standard_shortcuts_list.Bind(wx.EVT_RIGHT_DOWN, owner.on_standard_shortcut_right_click)

    row_move_up_handler = getattr(owner, "on_favorite_row_move_up", None)
    if row_move_up_handler is None:
        row_move_up_handler = lambda event: on_favorite_row_move_up(owner, event)
    row_move_down_handler = getattr(owner, "on_favorite_row_move_down", None)
    if row_move_down_handler is None:
        row_move_down_handler = lambda event: on_favorite_row_move_down(owner, event)
    owner.favorite_row_move_up_btn.Bind(wx.EVT_BUTTON, row_move_up_handler)
    owner.favorite_row_move_down_btn.Bind(wx.EVT_BUTTON, row_move_down_handler)

    refresh_favorite_list(owner)
    refresh_standard_shortcuts_list(owner)
    return owner.favorite_panel


def sync_favorite_row_action_buttons(owner):
    if owner.favorite_list is None:
        return
    up_btn = getattr(owner, "favorite_row_move_up_btn", None)
    down_btn = getattr(owner, "favorite_row_move_down_btn", None)
    if up_btn is None or down_btn is None:
        return

    selected_index = owner.favorite_list.GetFirstSelected()
    if selected_index == wx.NOT_FOUND:
        up_btn.Hide()
        down_btn.Hide()
        return

    try:
        raw_item_count = owner.favorite_list.GetItemCount()
        if isinstance(raw_item_count, int):
            item_count = raw_item_count
        else:
            raise TypeError
    except (AttributeError, TypeError, ValueError):
        item_count = len(getattr(owner, "favorite_paths", []))
    if item_count <= 0:
        item_count = max(selected_index + 1, 1)

    up_btn.Show(selected_index > 0)
    down_btn.Show(selected_index < item_count - 1)
    if hasattr(owner.favorite_panel, "GetSizer"):
        owner.favorite_panel.GetSizer().Layout()


def _apply_favorite_list_layout(owner):
    if owner.favorite_list is None or owner.favorite_panel is None:
        return
    panel_size = owner.favorite_panel.GetSize()
    panel_width = panel_size.GetWidth() if hasattr(panel_size, "GetWidth") else 0
    if panel_width > 0:
        owner.favorite_list.SetColumnWidth(0, max(80, panel_width - 16))
    if hasattr(owner.favorite_list, "Layout"):
        owner.favorite_list.Layout()


def on_favorite_panel_resize(owner, event):
    _apply_favorite_list_layout(owner)
    _apply_standard_shortcuts_layout(owner)
    sync_favorite_row_action_buttons(owner)

    if event is not None:
        event.Skip()


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


def _standard_shortcut_icon_index(owner, shortcut):
    if owner is None or not isinstance(shortcut, dict):
        return getattr(owner, "favorite_folder_icon_index", -1)

    shortcut_path = shortcut.get("path", "")
    shortcut_key = shortcut.get("key", "")
    image_list = getattr(owner, "standard_shortcuts_image_list", None)

    if not shortcut_path:
        return getattr(owner, "favorite_folder_icon_index", -1)

    try:
        icon = image_utils.get_shell_bitmap(shortcut_path, 0x00000010)
        if icon is not None and icon.IsOk() and image_list is not None:
            return image_list.Add(icon)
    except Exception:
        pass

    if shortcut_key == "recycle_bin":
        try:
            icon = image_utils.get_shell_bitmap("Recycle Bin", 0x00000010)
            if icon is not None and icon.IsOk() and image_list is not None:
                return image_list.Add(icon)
        except Exception:
            pass

    return getattr(owner, "favorite_folder_icon_index", -1)


def refresh_standard_shortcuts_list(owner):
    if owner is None or getattr(owner, "standard_shortcuts_list", None) is None:
        return

    owner.standard_shortcuts_list.DeleteAllItems()
    visible_shortcuts = _visible_standard_shortcuts(owner)
    for index, shortcut in enumerate(visible_shortcuts):
        item_index = owner.standard_shortcuts_list.InsertItem(index, shortcut["label"])
        icon_index = _standard_shortcut_icon_index(owner, shortcut)
        if icon_index >= 0:
            owner.standard_shortcuts_list.SetItemImage(item_index, icon_index)

    if hasattr(owner.standard_shortcuts_list, "Layout"):
        owner.standard_shortcuts_list.Layout()
    _apply_standard_shortcuts_layout(owner)


def _apply_standard_shortcuts_layout(owner):
    if owner is None or getattr(owner, "standard_shortcuts_list", None) is None:
        return
    panel = getattr(owner, "standard_shortcuts_panel", None)
    if panel is None:
        panel = getattr(owner, "favorite_panel", None)
    if panel is None:
        return
    panel_size = panel.GetSize()
    panel_width = panel_size.GetWidth() if hasattr(panel_size, "GetWidth") else 0
    try:
        panel_width = int(panel_width)
    except (TypeError, ValueError):
        return
    if panel_width > 0:
        owner.standard_shortcuts_list.SetColumnWidth(0, max(80, panel_width - 16))
    if hasattr(owner.standard_shortcuts_list, "Layout"):
        owner.standard_shortcuts_list.Layout()
    if panel is not None and hasattr(panel, "Layout"):
        panel.Layout()
    favorite_panel_obj = getattr(owner, "favorite_panel", None)
    if favorite_panel_obj is not None and hasattr(favorite_panel_obj, "GetSizer"):
        favorite_panel_obj.GetSizer().Layout()


def on_favorite_content_splitter_sash_changed(owner, event):
    splitter = getattr(owner, "favorite_content_splitter", None)
    if splitter is None:
        return

    owner.favorite_standard_shortcuts_splitter_sash = int(
        splitter.GetSashPosition()
    )

    if hasattr(owner, "save_splitter_positions"):
        owner.save_splitter_positions()

    if event is not None:
        event.Skip()


def toggle_standard_shortcuts_panel(owner):
    if owner is None or getattr(owner, "standard_shortcuts_list", None) is None:
        return

    new_visible = not bool(getattr(owner, "standard_shortcuts_visible", False))
    owner.standard_shortcuts_visible = new_visible

    splitter = getattr(owner, "favorite_content_splitter", None)
    standard_shortcuts_pane = getattr(owner, "standard_shortcuts_panel", None)
    if new_visible:
        owner.standard_shortcuts_list.Show(True)
        owner.standard_shortcuts_list.Enable()
        if splitter is not None:
            try:
                if not splitter.IsSplit():
                    splitter.SplitHorizontally(owner.favorite_list, standard_shortcuts_pane or owner.standard_shortcuts_list, getattr(owner, "favorite_standard_shortcuts_splitter_sash", 120))
                    splitter.SetSashPosition(max(40, min(int(getattr(owner, "favorite_standard_shortcuts_splitter_sash", 120)), 400)))
            except Exception:
                pass
    else:
        owner.standard_shortcuts_list.Hide()
        owner.standard_shortcuts_list.Disable()
        if splitter is not None:
            try:
                if splitter.IsSplit():
                    target_pane = standard_shortcuts_pane or owner.standard_shortcuts_list
                    splitter.Unsplit(target_pane)
            except Exception:
                pass

    if splitter is not None:
        try:
            splitter.Layout()
            splitter.Update()
            if splitter.IsSplit():
                owner.favorite_standard_shortcuts_splitter_sash = int(splitter.GetSashPosition())
        except Exception:
            pass

    if hasattr(owner.standard_shortcuts_toggle_btn, "SetLabel"):
        owner.standard_shortcuts_toggle_btn.SetLabel(tr("favorite_shortcuts_button"))
    _sync_standard_shortcuts_toggle_button(owner, getattr(owner, "standard_shortcuts_toggle_btn", None))
    if hasattr(owner.favorite_panel, "GetSizer"):
        owner.favorite_panel.GetSizer().Layout()
    if hasattr(owner, "save_splitter_positions"):
        owner.save_splitter_positions()


def on_standard_shortcut_list_activate(owner, event):
    if owner is None or getattr(owner, "standard_shortcuts_list", None) is None:
        return
    selected_index = owner.standard_shortcuts_list.GetFirstSelected()
    if selected_index == wx.NOT_FOUND:
        return
    shortcuts = _visible_standard_shortcuts(owner)
    if not (0 <= selected_index < len(shortcuts)):
        return
    target_path = shortcuts[selected_index].get("path", "")
    if os.path.isdir(target_path):
        if hasattr(owner, "open_path"):
            owner.open_path(target_path, add_history=True)
        if hasattr(owner, "select_tree_item_by_path"):
            owner.select_tree_item_by_path(target_path)


def on_standard_shortcut_right_click(owner, event):
    if owner is None or getattr(owner, "standard_shortcuts_list", None) is None:
        return
    try:
        index, _ = owner.standard_shortcuts_list.HitTest(event.GetPosition())
        if index != wx.NOT_FOUND:
            owner.standard_shortcuts_list.Select(index)
    except Exception:
        pass

    menu = wx.Menu()
    for shortcut in _standard_shortcut_entries(owner):
        item = menu.AppendCheckItem(-1, shortcut["label"])
        item.Check(bool(owner.standard_shortcuts_visibility.get(shortcut["key"], shortcut["label"] in {"Desktop", "Documents", "Recycle Bin"})))
        owner.Bind(wx.EVT_MENU, lambda _event, key=shortcut["key"]: _toggle_standard_shortcut_visibility(owner, key), item)
    owner.standard_shortcuts_list.PopupMenu(menu)
    menu.Destroy()


def _toggle_standard_shortcut_visibility(owner, key):
    if owner is None:
        return
    visibility = getattr(owner, "standard_shortcuts_visibility", {})
    current = bool(visibility.get(key, True))
    visibility[key] = not current
    owner.standard_shortcuts_visibility = visibility
    refresh_standard_shortcuts_list(owner)


def apply_favorite_panel_position(owner, sash_position=None):
    if owner.favorite_splitter is None:
        return
    if owner.favorite_splitter.IsSplit():
        owner.favorite_splitter.Unsplit()

    if sash_position is None:
        try:
            current_sash = int(owner.favorite_splitter.GetSashPosition())
        except Exception:
            current_sash = 180
        sash_position = current_sash

    if owner.favorite_panel_above_tree:
        owner.favorite_splitter.SplitHorizontally(owner.favorite_panel, owner.tree, int(sash_position))
    else:
        owner.favorite_splitter.SplitHorizontally(owner.tree, owner.favorite_panel, int(sash_position))

    if owner.favorite_panel is not None:
        owner.favorite_move_up_btn.Show(not owner.favorite_panel_above_tree)
        owner.favorite_move_down_btn.Show(owner.favorite_panel_above_tree)
        if hasattr(owner.favorite_panel, "Layout"):
            owner.favorite_panel.Layout()
        _apply_favorite_list_layout(owner)

    if owner.favorite_splitter is not None:
        owner.favorite_splitter.SetSashPosition(int(sash_position))


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
            splitter_size = owner.favorite_splitter.GetSize()
            splitter_height = splitter_size.GetHeight() if hasattr(splitter_size, "GetHeight") else 0
        except Exception:
            splitter_height = 0
        if splitter_height > 0:
            target_sash = max(40, min(splitter_height - current_sash, splitter_height - 40))

    owner.favorite_panel_above_tree = target_above_tree
    apply_favorite_panel_position(owner, sash_position=target_sash)
    if hasattr(owner, "save_splitter_positions"):
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


def on_favorite_key_down(owner, event):
    if owner.favorite_list is None or event is None:
        return

    key_code = event.GetKeyCode()
    if key_code != wx.WXK_DELETE:
        return

    selected_index = owner.favorite_list.GetFirstSelected() if owner.favorite_list is not None else wx.NOT_FOUND
    if selected_index == wx.NOT_FOUND or not (0 <= selected_index < len(owner.favorite_paths)):
        return

    owner._remove_favorite_path(owner.favorite_paths[selected_index])
    event.Skip()


def on_favorite_row_move_up(owner, _):
    if owner.favorite_list is None:
        return
    selected_index = owner.favorite_list.GetFirstSelected()
    if selected_index == wx.NOT_FOUND or selected_index <= 0:
        return
    try:
        raw_item_count = owner.favorite_list.GetItemCount()
        if isinstance(raw_item_count, int):
            item_count = raw_item_count
        else:
            raise TypeError
    except (AttributeError, TypeError, ValueError):
        item_count = len(getattr(owner, "favorite_paths", []))
    if item_count <= 0:
        item_count = selected_index + 1
    if selected_index >= item_count:
        return
    owner._reorder_favorite_paths(selected_index, selected_index - 1)
    sync_favorite_row_action_buttons(owner)


def on_favorite_row_move_down(owner, _):
    if owner.favorite_list is None:
        return
    selected_index = owner.favorite_list.GetFirstSelected()
    if selected_index == wx.NOT_FOUND:
        return
    try:
        raw_item_count = owner.favorite_list.GetItemCount()
        if isinstance(raw_item_count, int):
            item_count = raw_item_count
        else:
            raise TypeError
    except (AttributeError, TypeError, ValueError):
        item_count = len(getattr(owner, "favorite_paths", []))
    if item_count <= 0:
        item_count = selected_index + 1
    if selected_index >= item_count - 1:
        return
    owner._reorder_favorite_paths(selected_index, selected_index + 1)
    sync_favorite_row_action_buttons(owner)


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
    icon_manager = image_utils.ensure_owner_icon_manager(owner)
    if icon_manager is not None:
        icon_manager.set_menu_icon2(remove_item, "remove_from_favorite")
    remove_item.Enable(owner.favorite_list.GetFirstSelected() != wx.NOT_FOUND)
    owner.Bind(wx.EVT_MENU, owner.on_remove_favorite_from_context, remove_item)
    owner.favorite_list.PopupMenu(menu)
    menu.Destroy()


def on_remove_favorite_from_context(owner, _):
    selected_index = owner.favorite_list.GetFirstSelected() if owner.favorite_list is not None else wx.NOT_FOUND
    if selected_index == wx.NOT_FOUND or not (0 <= selected_index < len(owner.favorite_paths)):
        return
    owner._remove_favorite_path(owner.favorite_paths[selected_index])
