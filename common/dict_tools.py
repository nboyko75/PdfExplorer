"""Shared dictionary metadata and key configuration for settings and option dialogs."""

PERSISTED_LAYOUT_KEYS = {
    "window_position",
    "window_size",
    "options_form_position",
    "options_form_size",
    "search_form_position",
    "search_form_size",
    "scan_dialog_size",
    "main_splitter_sash",
    "preview_splitter_sash",
    "favorite_splitter_sash",
    "favorite_panel_above_tree",
    "favorite_paths",
    "list_column_widths",
    "list_sort_column",
    "list_sort_direction",
}

OPTION_GROUP_ORDER = ["main", "optimization", "preview"]
OPTION_GROUP_TRANSLATION_KEYS = {
    "main": "options_group_main",
    "optimization": "options_group_optimization",
    "preview": "options_group_preview",
}
OPTION_FIELDS = [
    {"key": "ui_locale", "group": "main", "label_key": "settings_ui_locale", "kind": "locale_choice", "default": "uk"},
    {"key": "optimize_pdf_image_width", "group": "optimization", "label_key": "settings_optimize_pdf_image_width", "kind": "int", "default": 1000},
    {"key": "optimize_pdf_image_quality", "group": "optimization", "label_key": "settings_optimize_pdf_image_quality", "kind": "int", "default": 70},
    {"key": "optimize_pdf_color_target_dpi", "group": "optimization", "label_key": "settings_optimize_pdf_color_target_dpi", "kind": "int", "default": 110},
    {"key": "optimize_pdf_color_threshold_dpi", "group": "optimization", "label_key": "settings_optimize_pdf_color_threshold_dpi", "kind": "int", "default": 140},
    {"key": "optimize_pdf_color_compression", "group": "optimization", "label_key": "settings_optimize_pdf_color_compression", "kind": "choice", "choices": ["jpeg", "png"], "default": "jpeg"},
    {"key": "optimize_pdf_color_quality", "group": "optimization", "label_key": "settings_optimize_pdf_color_quality", "kind": "int", "default": 35},
    {"key": "optimize_pdf_mono_target_dpi", "group": "optimization", "label_key": "settings_optimize_pdf_mono_target_dpi", "kind": "int", "default": 110},
    {"key": "optimize_pdf_mono_threshold_dpi", "group": "optimization", "label_key": "settings_optimize_pdf_mono_threshold_dpi", "kind": "int", "default": 140},
    {"key": "optimize_pdf_mono_compression", "group": "optimization", "label_key": "settings_optimize_pdf_mono_compression", "kind": "choice", "choices": ["ccitt_group3", "ccitt_group4", "png"], "default": "png"},
    {"key": "optimize_pdf_compress_only_if_resized", "group": "optimization", "label_key": "settings_optimize_pdf_compress_only_if_resized", "kind": "bool", "default": False},
    {"key": "pdf_show_pages_limit", "group": "preview", "label_key": "settings_pdf_show_pages_limit", "kind": "int", "default": 50},
    {"key": "word_show_pages_limit", "group": "preview", "label_key": "settings_word_show_pages_limit", "kind": "int", "default": 10},
    {"key": "excel_show_pages_limit", "group": "preview", "label_key": "settings_excel_show_pages_limit", "kind": "int", "default": 1},
    {"key": "other_show_pages_limit", "group": "preview", "label_key": "settings_other_show_pages_limit", "kind": "int", "default": 10},
]
