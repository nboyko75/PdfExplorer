import importlib
import os
from typing import Dict

TRANSLATIONS: Dict[str, str] = {
    "app_title": "Python Explorer Pro",
    "back_button": "Back",
    "forward_button": "Forward",
    "search_hint": "Search...",
    "show_hidden_checkbox": "Show hidden",
    "name_column": "Name",
    "type_column": "Type",
    "size_column": "Size",
    "preview_select_file": "Select a file to preview.",
    "folder_selected": "Folder selected:\n{path}",
    "no_preview_available": "No preview available for this item.",
    "unable_preview_pdf": "Unable to preview PDF.\n{exc}",
    "unable_preview_file": "Unable to preview file.\n{exc}",
    "empty_file": "This file is empty.",
    "preview_truncated_suffix": "\n\n... preview truncated ...",
    "context_open": "Open",
    "context_rename": "Rename",
    "context_delete": "Delete",
    "this_pc_root": "This PC",
    "tree_expand_placeholder": "...",
    "page_label": "Page {page_no}/{page_count}",
    "showing_first_pages": "Showing first {shown_pages} pages of {page_count}...",
    "page_move_error_title": "PDF page move",
    "unable_move_pdf_page": "Unable to move PDF page.\n{exc}",
    "drop_overlay_label": "Drop on page {page_index}",
    "preview_edit_button": "Open",
    "preview_save_button": "Save",
    "preview_delete_button": "Delete file",
    "preview_zoom_in_button": "Zoom In",
    "preview_zoom_out_button": "Zoom Out",
    "preview_show_mode": "Show mode",
    "preview_show_1_page_wide": "Show 1 page wide",
    "preview_show_2_pages_wide": "Show 2 pages wide",
    "preview_show_1_page_tall": "Show 1 page tall",
    "preview_show_manual_scale": "Manual scale",
    "preview_rotate_button": "Rotate",
    "preview_rotate_all_left_button": "Rotate All Left",
    "preview_rotate_left_button": "Rotate Left",
    "preview_rotate_right_button": "Rotate Right",
    "preview_rotate_all_right_button": "Rotate All Right",
    "preview_optimize_button": "Optimize",
    "preview_adjust_page_width_button": "Ajust page width",
    "preview_remove_page_button": "Remove page",
    "select_pdf_page": "Select a page first.",
    "confirm_remove_page": "Remove page {page_no}?",
    "confirm_save_selected_file": "Save changes to selected file?",
    "confirm_save_before_exit": "You have unsaved changes in {count} PDF file(s). Save before exit?",
    "confirm_delete": "Delete {path}?",
    "insert_before": "Insert before",
    "insert_after": "Insert after",
    "undo_no_action": "Nothing to undo",
    "undo_done": "Undo successful",
    "undo_title": "Undo",
    "file_type_folder": "Folder",
    "file_type_file": "File",
    "file_size_unit_kb": "KB",
    "tree_optimize_all_pdf": "Optimize all PDF",
    "tree_adjust_page_width_all_pdf": "Adjust page width all",
    "tree_no_folder_selected": "Select a folder in the tree first.",
    "tree_no_folder_or_pdf_selected": "Select a folder or PDF file in the tree first.",
    "tree_optimize_all_done": "Optimized: {optimized_count}\nFailed: {failed_count}",
    "tree_adjust_page_width_all_done": "Adjusted: {adjusted_count}\nFailed: {failed_count}",
}


def tr(key: str, /, **kwargs) -> str:
    value = TRANSLATIONS.get(key, key)
    return value.format(**kwargs)


def load_locale(locale_code: str) -> None:
    module_name = f".localization_{locale_code}"
    try:
        locale_module = importlib.import_module(module_name, package=__name__)
        if hasattr(locale_module, "TRANSLATIONS"):
            TRANSLATIONS.clear()
            TRANSLATIONS.update(locale_module.TRANSLATIONS)
    except ModuleNotFoundError:
        pass


def available_locales() -> list[str]:
    locales = []
    current_dir = os.path.dirname(__file__)
    for filename in os.listdir(current_dir):
        if filename.startswith("localization_") and filename.endswith(".py"):
            locale_code = filename[len("localization_"):-3]
            locales.append(locale_code)
    return sorted(locales)
