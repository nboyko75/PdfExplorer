import os
from dataclasses import dataclass
from typing import Callable

import wx

from file_operations.copy_and_paste import _can_paste_into_directory
from localization import tr


@dataclass
class MenuCommand:
    key: str
    label_key: str
    handler: Callable | None = None
    shortcut: str = ""
    art_id: str | None = None
    custom_icon: str | None = None
    can_execute: Callable | None = None


@dataclass
class MenuCommandContext:
    owner: object
    source: str = "list"
    current_folder: str = ""
    selected_paths: list[str] | None = None
    target_path: str | None = None


def _build_menu_command_context(owner, source="list", current_folder=None, selected_paths=None, target_path=None):
    if current_folder is None:
        current_folder = owner.path_box.GetValue() if hasattr(owner, "path_box") and owner.path_box is not None else ""
    if selected_paths is None:
        selected_paths = []
    return MenuCommandContext(owner=owner, source=source, current_folder=current_folder, selected_paths=list(selected_paths), target_path=target_path)


def _resolve_context_action_name(context, action_name):
    if context.source == "tree":
        tree_handler = getattr(context.owner, f"on_tree_{action_name}", None)
        if callable(tree_handler):
            return tree_handler, "tree"
    list_handler = getattr(context.owner, f"on_list_{action_name}", None)
    if callable(list_handler):
        return list_handler, "list"
    direct = getattr(context.owner, action_name, None)
    if callable(direct):
        return direct, "direct"
    return None, None


def _invoke_menu_command(command, context, event):
    if command is None or command.handler is None:
        return None
    try:
        return command.handler(context, event)
    except TypeError:
        return command.handler(context.owner, event)


def apply_command_icon(owner, item, command):
    icon_manager = getattr(owner, "icon_manager", None)
    if command.art_id:
        if icon_manager is not None and hasattr(icon_manager, "set_menu_icon"):
            icon_manager.set_menu_icon(item, art_id=command.art_id)
        else:
            bmp = wx.ArtProvider.GetBitmap(command.art_id, wx.ART_MENU, (16, 16))
            if bmp.IsOk():
                item.SetBitmap(bmp)
    elif command.custom_icon:
        if icon_manager is not None and hasattr(icon_manager, "set_menu_icon2"):
            icon_manager.set_menu_icon2(item, command.custom_icon)
    return item


def append_command(menu, owner, command, context=None):
    if context is None:
        context = _build_menu_command_context(owner)

    label = tr(command.label_key)
    if command.shortcut:
        label = f"{label}\t{command.shortcut}"

    item = menu.Append(wx.ID_ANY, label)
    apply_command_icon(owner, item, command)

    enabled = True
    if command.can_execute is not None:
        try:
            enabled = bool(command.can_execute(context))
        except TypeError:
            enabled = bool(command.can_execute(context.owner, context))
    item.Enable(enabled)

    if hasattr(owner, "Bind") and command.handler is not None:
        owner.Bind(wx.EVT_MENU, lambda event, command_ref=command, context_ref=context: _invoke_menu_command(command_ref, context_ref, event), item)
    return item


def append_menu_command(menu, owner, command, context=None):
    return append_command(menu, owner, command, context)


def _dispatch_context_action(context, action_name, event):
    handler, mode = _resolve_context_action_name(context, action_name)
    if handler is None:
        return None

    if mode == "tree":
        return handler(context.target_path or context.current_folder)
    if mode == "list":
        return handler(event)
    return handler(event)


FILE_COMMANDS = {
    "scan": MenuCommand(
        "scan",
        "scan",
        handler=lambda context, event: _dispatch_context_action(context, "scan", event),
        shortcut="",
        custom_icon="scan",
        can_execute=lambda context: True,
    ),
    "open": MenuCommand(
        "open",
        "context_open",
        handler=lambda context, event: _dispatch_context_action(context, "open", event),
        shortcut="",
        custom_icon="file_view",
        can_execute=lambda context: bool(context.selected_paths and len(context.selected_paths) == 1),
    ),
    "new_folder": MenuCommand(
        "new_folder",
        "context_new_folder",
        handler=lambda context, event: _dispatch_context_action(context, "new_folder", event),
        shortcut="",
        art_id=wx.ART_FOLDER,
        can_execute=lambda context: bool(context.current_folder and os.path.isdir(context.current_folder)),
    ),
    "refresh": MenuCommand(
        "refresh",
        "context_refresh",
        handler=lambda context, event: getattr(context.owner, "on_refresh_menu", lambda *_: None)(event),
        shortcut="F5",
        art_id=wx.ART_REDO,
        can_execute=lambda context: True,
    ),
    "print": MenuCommand(
        "print",
        "context_print",
        handler=lambda context, event: _dispatch_context_action(context, "print", event),
        shortcut="Ctrl+P",
        art_id=wx.ART_PRINT,
        can_execute=lambda context: bool(context.selected_paths and len(context.selected_paths) == 1),
    ),
    "copy": MenuCommand(
        "copy",
        "context_copy",
        handler=lambda context, event: _dispatch_context_action(context, "copy", event),
        shortcut="Ctrl+C",
        custom_icon="copy",
        can_execute=lambda context: bool(context.selected_paths),
    ),
    "cut": MenuCommand(
        "cut",
        "context_cut",
        handler=lambda context, event: _dispatch_context_action(context, "cut", event),
        shortcut="Ctrl+X",
        art_id=wx.ART_CUT,
        can_execute=lambda context: bool(context.selected_paths),
    ),
    "paste": MenuCommand(
        "paste",
        "context_paste",
        handler=lambda context, event: _dispatch_context_action(context, "paste", event),
        shortcut="Ctrl+V",
        art_id=wx.ART_PASTE,
        can_execute=lambda context: _can_paste_into_directory(context.owner, context.current_folder),
    ),
    "rename": MenuCommand(
        "rename",
        "context_rename",
        handler=lambda context, event: _dispatch_context_action(context, "rename", event),
        shortcut="",
        art_id=wx.ART_EDIT,
        can_execute=lambda context: bool(context.selected_paths and len(context.selected_paths) == 1),
    ),
    "delete": MenuCommand(
        "delete",
        "context_remove_to_recycle_bin",
        handler=lambda context, event: _dispatch_context_action(context, "delete", event),
        shortcut="Ctrl+D",
        custom_icon="recycle_bin",
        can_execute=lambda context: bool(context.selected_paths),
    ),
    "delete_permanent": MenuCommand(
        "delete_permanent",
        "context_delete",
        handler=lambda context, event: _dispatch_context_action(context, "delete_permanent", event),
        shortcut="Shift+Del",
        art_id=wx.ART_DELETE,
        can_execute=lambda context: bool(context.selected_paths),
    ),
}
