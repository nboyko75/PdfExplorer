import importlib
import os
from typing import Dict

DEFAULT_TRANSLATIONS: Dict[str, str] = {
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
    "scan": "Scan",
    "scan_dialog_title": "Scan documents",
    "scan_scanner_label": "Scanner",
    "scan_default_scanner": "Default scanner",
    "scan_source_label": "Source",
    "scan_source_flatbed": "Flatbed",
    "scan_source_adf_simplex": "ADF (Simplex)",
    "scan_source_adf_duplex": "ADF (Duplex)",
    "scan_color_mode_label": "Color mode",
    "scan_color_mode_color": "Color",
    "scan_color_mode_grayscale": "Grayscale",
    "scan_color_mode_black_white": "Black and white",
    "scan_dpi_label": "Resolution (DPI)",
    "scan_page_size_label": "Page size",
    "scan_page_size_auto": "Auto",
    "scan_page_size_a4": "A4",
    "scan_page_size_letter": "Letter",
    "scan_page_size_legal": "Legal",
    "scan_output_type_label": "Output type",
    "scan_output_type_pdf": "PDF",
    "scan_output_type_jpeg": "JPEG",
    "scan_multiple_pages_label": "Scan multiple pages",
    "scan_output_file_label": "Output file",
    "scan_browse_button": "Browse...",
    "scan_open_after_label": "Open after scan",
    "scan_select_output_file_title": "Select output file",
    "scan_button": "Scan",
    "scan_cancel_button": "Cancel",
    "scan_output_file_required": "Select an output file.",
    "scan_output_folder_not_exists": "Output folder does not exist.",
    "scan_not_available_message": "Scan form is configured. Scanner device integration is not available in this build yet.",
    "this_pc_root": "This PC",
    "tree_expand_placeholder": "...",
    "page_label": "Page {page_no}/{page_count}",
    "showing_first_pages": "Showing first {shown_pages} pages of {page_count}...",
    "page_move_error_title": "PDF page move",
    "unable_move_pdf_page": "Unable to move PDF page.\n{exc}",
    "drop_overlay_label": "Drop on page {page_index}",
    "preview_edit_button": "Open",
    "preview_save_button": "Save",
    "preview_cancel_button": "Cancel",
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
    "preview_auto_rotate_button": "Auto rotate",
    "preview_optimize_button": "Optimize",
    "preview_adjust_page_width_button": "Ajust page width",
    "preview_remove_page_button": "Remove page",
    "preview_move_page_button": "Move page",
    "preview_import_button": "Import",
    "preview_import_from_file_button": "Import from file",
    "preview_import_from_scanner_button": "Import from scanner",
    "preview_export_pages_button": "Export pages",
    "import_pdf_dialog_title": "Import PDF from file",
    "import_pdf_source_label": "From file name",
    "import_pdf_browse_button": "Browse...",
    "import_pdf_file_dialog_title": "Select PDF file",
    "import_pdf_destination_label": "Destination",
    "import_pdf_after_page": "After the page",
    "import_pdf_source_required": "Select a PDF file to import.",
    "export_pdf_pages_dialog_title": "Export pages",
    "export_pdf_page_numbers_label": "Page numbers",
    "export_pdf_file_name_label": "File name",
    "export_pdf_file_name_required": "Enter a file name for export.",
    "export_pdf_page_numbers_invalid": "Enter page numbers like 1,3-5.",
    "export_pdf_save_dialog_title": "Save exported pages",
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

TRANSLATIONS: Dict[str, str] = DEFAULT_TRANSLATIONS.copy()


def tr(key: str, /, **kwargs) -> str:
    value = TRANSLATIONS.get(key, key)
    return value.format(**kwargs)


def load_locale(locale_code: str) -> None:
    module_name = f".localization_{locale_code}"
    TRANSLATIONS.clear()
    TRANSLATIONS.update(DEFAULT_TRANSLATIONS)
    try:
        locale_module = importlib.import_module(module_name, package=__name__)
        if hasattr(locale_module, "TRANSLATIONS"):
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
