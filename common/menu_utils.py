import os
from dataclasses import dataclass
from typing import Callable

import wx

import file_operations.archive_helper as archive_helper
from file_operations.copy_and_paste import _can_paste_into_directory
from localization import tr


@dataclass(frozen=True)
class MenuCommand:
    key: str
    label_key: str
    handler: Callable
    shortcut: str = ""
    art_id: str | None = None
    custom_icon: str | None = None
    can_execute: Callable | None = None


@dataclass
class FileCommandContext:
    owner: wx.Window
    source: str
    current_folder: str
    selected_paths: list[str]
    target_path: str | None = None
    new_folder_target: str | None = None


MenuCommandContext = FileCommandContext


def _build_menu_command_context(owner, source="list", current_folder=None, selected_paths=None, target_path=None, new_folder_target=None):
    if current_folder is None:
        path_box = getattr(owner, "path_box", None)
        current_folder = path_box.GetValue() if path_box is not None else ""
    paths = [path for path in list(selected_paths or []) if isinstance(path, str) and path]
    return FileCommandContext(owner, source, current_folder or "", paths, target_path, new_folder_target)


def _tree_target(context):
    return context.target_path or (context.selected_paths[0] if context.selected_paths else context.current_folder)


def _invoke_owner_list_handler(context, action_name, event):
    handler = getattr(context.owner, f"on_list_{action_name}", None)
    return handler(event) if callable(handler) else None


def _dispatch_file_action(context, action_name, event):
    """Canonical operation handler used by toolbar, main menu and popup menus."""
    if context.source != "tree":
        return _invoke_owner_list_handler(context, action_name, event)
    import controls.tree_control as tree_control
    handler = {
        "copy": tree_control.on_tree_copy,
        "cut": tree_control.on_tree_cut,
        "paste": tree_control.on_tree_paste,
        "rename": tree_control.on_tree_rename,
        "delete": tree_control.on_tree_delete,
        "delete_permanent": tree_control.on_tree_delete_permanent,
    }.get(action_name)
    return handler(context.owner, _tree_target(context)) if handler else None


def _handle_scan(context, event):
    return _invoke_owner_list_handler(context, "scan", event)


def _handle_open(context, event):
    if context.source == "tree":
        from controls import filelist
        target = _tree_target(context)
        return filelist.open_path_or_file(context.owner, target) if target else None
    return _invoke_owner_list_handler(context, "open", event)


def _handle_new_folder(context, event):
    if context.source == "tree":
        from controls import filelist
        return filelist.create_new_folder(context.owner, context.new_folder_target) if context.new_folder_target else None
    return _invoke_owner_list_handler(context, "new_folder", event)


def _handle_refresh(context, event):
    if context.source == "tree":
        from controls import tree_control
        return tree_control.refresh_tree_selection_and_filelist(context.owner)
    handler = getattr(context.owner, "on_refresh_menu", None)
    return handler(event) if callable(handler) else None


def _handle_print(context, event):
    if context.source == "tree":
        target = _tree_target(context)
        if target and os.path.isfile(target):
            import controls.print_form as print_form
            return print_form.show_print_form(context.owner, target)
        return None
    return _invoke_owner_list_handler(context, "print", event)


def _handle_folder_up(context, event):
    if context.source != "tree":
        handler = getattr(context.owner, "on_folder_up", None)
        return handler(event) if callable(handler) else None
    target = _tree_target(context)
    parent = os.path.dirname(target) if target else ""
    if not parent or not os.path.isdir(parent):
        return None
    owner = context.owner
    if hasattr(owner, "select_tree_item_by_path"):
        owner.select_tree_item_by_path(parent)
    return owner.open_path(parent, add_history=True) if hasattr(owner, "open_path") else None


def _handle_archive(context, _event):
    target = _tree_target(context) if context.source == "tree" else context.selected_paths
    return archive_helper._archive_selected_path(context.owner, target)


def _handle_extract(context, into):
    target = _tree_target(context) if context.source == "tree" else (context.selected_paths[0] if context.selected_paths else None)
    if not target:
        return None
    method = archive_helper._extract_selected_archive_into if into else archive_helper._extract_selected_archive_here
    return method(context.owner, target)


def _handle_favorite(context, event, add):
    owner = context.owner
    if context.source != "tree":
        handler = getattr(owner, "on_nav_add_to_favourite" if add else "on_nav_remove_from_favourite", None)
        return handler(event) if callable(handler) else None
    target = _tree_target(context)
    method = getattr(owner, "_add_favorite_path" if add else "_remove_favorite_path", None)
    if target and callable(method):
        method(target)
        if hasattr(owner, "_update_main_menu_state"):
            owner._update_main_menu_state()
    return None


def _handle_optimize_all(context, _event):
    from controls import tree_control
    return tree_control.optimize_all_pdf_in_path(context.owner, _tree_target(context))


def _handle_adjust_all(context, _event):
    from controls import tree_control
    return tree_control.adjust_page_width_all_pdf_in_path(context.owner, _tree_target(context))


def _can_select(context):
    return bool(context.selected_paths)


def _can_select_one(context):
    return len(context.selected_paths) == 1


def _can_go_up(context):
    target = _tree_target(context) if context.source == "tree" else context.current_folder
    return bool(target and os.path.isdir(target) and os.path.dirname(target))


def _can_create_folder(context):
    target = context.new_folder_target if context.source == "tree" else context.current_folder
    return bool(target and os.path.isdir(target))


def _can_print(context):
    return len(context.selected_paths) == 1 and os.path.isfile(context.selected_paths[0])


def _can_add_archive(context):
    return bool(context.selected_paths) and all(os.path.exists(path) and not archive_helper._is_archive_file(path) for path in context.selected_paths)


def _can_extract(context):
    return len(context.selected_paths) == 1 and archive_helper._is_archive_file(context.selected_paths[0])


def _paste_directory(context):
    if context.source != "tree":
        return context.current_folder
    from controls import filelist
    return filelist._resolve_paste_target_directory(_tree_target(context))


def _can_manage_favorite(context, add):
    target = _tree_target(context)
    if not target or not os.path.isdir(target):
        return False
    checker = getattr(context.owner, "_is_favorite_path", None)
    is_favorite = bool(callable(checker) and checker(target))
    return not is_favorite if add else is_favorite


def _can_process_pdf_path(context):
    from controls import tree_control
    target = _tree_target(context)
    return bool(target and tree_control._is_folder_or_single_pdf(target))


FILE_COMMANDS = {
    "scan": MenuCommand("scan", "scan", _handle_scan, custom_icon="scan"),
    "open": MenuCommand("open", "context_open", _handle_open, custom_icon="file_view", can_execute=_can_select_one),
    "folder_up": MenuCommand("folder_up", "folder_up_button", _handle_folder_up, art_id=wx.ART_GO_UP, can_execute=_can_go_up),
    "new_folder": MenuCommand("new_folder", "context_new_folder", _handle_new_folder, art_id=wx.ART_FOLDER, can_execute=_can_create_folder),
    "refresh": MenuCommand("refresh", "context_refresh", _handle_refresh, shortcut="F5", art_id=wx.ART_REDO),
    "print": MenuCommand("print", "context_print", _handle_print, shortcut="Ctrl+P", art_id=wx.ART_PRINT, can_execute=_can_print),
    "favorite_add": MenuCommand("favorite_add", "favorite_add_menu_item", lambda c, e: _handle_favorite(c, e, True), custom_icon="add_to_favorites", can_execute=lambda c: _can_manage_favorite(c, True)),
    "favorite_remove": MenuCommand("favorite_remove", "favorite_remove_menu_item", lambda c, e: _handle_favorite(c, e, False), custom_icon="remove_from_favorites", can_execute=lambda c: _can_manage_favorite(c, False)),
    "copy": MenuCommand("copy", "context_copy", lambda c, e: _dispatch_file_action(c, "copy", e), shortcut="Ctrl+C", custom_icon="copy", can_execute=_can_select),
    "cut": MenuCommand("cut", "context_cut", lambda c, e: _dispatch_file_action(c, "cut", e), shortcut="Ctrl+X", art_id=wx.ART_CUT, can_execute=_can_select),
    "paste": MenuCommand("paste", "context_paste", lambda c, e: _dispatch_file_action(c, "paste", e), shortcut="Ctrl+V", art_id=wx.ART_PASTE, can_execute=lambda c: _can_paste_into_directory(c.owner, _paste_directory(c))),
    "rename": MenuCommand("rename", "context_rename", lambda c, e: _dispatch_file_action(c, "rename", e), art_id=wx.ART_EDIT, can_execute=_can_select_one),
    "delete": MenuCommand("delete", "context_remove_to_recycle_bin", lambda c, e: _dispatch_file_action(c, "delete", e), shortcut="Ctrl+D", custom_icon="recycle_bin", can_execute=_can_select),
    "delete_permanent": MenuCommand("delete_permanent", "context_delete", lambda c, e: _dispatch_file_action(c, "delete_permanent", e), shortcut="Shift+Del", art_id=wx.ART_DELETE, can_execute=_can_select),
    "archive": MenuCommand("archive", "context_add_to_archive", _handle_archive, custom_icon="add_to_archive", can_execute=_can_add_archive),
    "extract_here": MenuCommand("extract_here", "context_extract_from_archive_here", lambda c, e: _handle_extract(c, False), custom_icon="extract_from_archive", can_execute=_can_extract),
    "extract_into": MenuCommand("extract_into", "context_extract_from_archive_into", lambda c, e: _handle_extract(c, True), custom_icon="extract_from_archive", can_execute=_can_extract),
    "optimize_all": MenuCommand("optimize_all", "tree_optimize_all_pdf", _handle_optimize_all, custom_icon="ok", can_execute=_can_process_pdf_path),
    "adjust_all": MenuCommand("adjust_all", "tree_adjust_page_width_all_pdf", _handle_adjust_all, art_id=wx.ART_REPORT_VIEW, can_execute=_can_process_pdf_path),
}


def apply_command_icon(owner, item, command):
    icon_manager = getattr(owner, "icon_manager", None)
    if command.art_id:
        if icon_manager is not None and hasattr(icon_manager, "set_menu_icon"):
            icon_manager.set_menu_icon(item, art_id=command.art_id)
        else:
            bitmap = wx.ArtProvider.GetBitmap(command.art_id, wx.ART_MENU, (16, 16))
            if bitmap.IsOk():
                item.SetBitmap(bitmap)
    elif command.custom_icon and icon_manager is not None and hasattr(icon_manager, "set_menu_icon2"):
        icon_manager.set_menu_icon2(item, command.custom_icon)
    return item


def _invoke_menu_command(command, context, event):
    return command.handler(context, event)


def bind_command(control, owner, command, event_type, context_factory):
    def handle(event):
        return _invoke_menu_command(command, context_factory(), event)
    control.Bind(event_type, handle)
    return handle


def append_command(menu, owner, command, context=None, context_factory=None):
    if context_factory is None:
        fixed_context = context or _build_menu_command_context(owner)
        context_factory = lambda: fixed_context
    initial_context = context_factory()
    label = tr(command.label_key)
    if command.shortcut:
        label = f"{label}\t{command.shortcut}"
    item = menu.Append(wx.ID_ANY, label)
    apply_command_icon(owner, item, command)
    if command.can_execute is not None:
        item.Enable(bool(command.can_execute(initial_context)))
    owner.Bind(wx.EVT_MENU, lambda event: _invoke_menu_command(command, context_factory(), event), item)
    return item


append_menu_command = append_command


def build_file_operations_menu(context):
    menu = wx.Menu()
    owner = context.owner
    for key in ("scan", "open", "folder_up", "new_folder", "refresh", "print"):
        append_command(menu, owner, FILE_COMMANDS[key], context)
    if context.source == "tree":
        menu.AppendSeparator()
        append_command(menu, owner, FILE_COMMANDS["favorite_add"], context)
        append_command(menu, owner, FILE_COMMANDS["favorite_remove"], context)
    menu.AppendSeparator()
    for key in ("copy", "cut", "paste", "rename", "delete", "delete_permanent"):
        append_command(menu, owner, FILE_COMMANDS[key], context)
    menu.AppendSeparator()
    for key in ("archive", "extract_here", "extract_into"):
        append_command(menu, owner, FILE_COMMANDS[key], context)
    if context.source == "tree":
        menu.AppendSeparator()
        append_command(menu, owner, FILE_COMMANDS["optimize_all"], context)
        append_command(menu, owner, FILE_COMMANDS["adjust_all"], context)
    return menu
