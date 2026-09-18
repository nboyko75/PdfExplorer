"""Centralized shared constants for the DocExplorer application."""

import os
import tempfile

import wx

# common/system.py
FILE_ATTRIBUTE_HIDDEN = 0x02

# common/date_utils.py
LOCALE_NAME_USER_DEFAULT = None
LOCALE_SSHORTDATE = 0x0000001F

DATE_PICKER_STYLE = 0
for source in (wx, getattr(wx, "adv", None)):
    if source is None:
        continue
    for style_name in ("DP_DROPDOWN", "DP_SHOWCENTURY", "DP_DEFAULT"):
        style_flag = getattr(source, style_name, None)
        if style_flag is not None:
            DATE_PICKER_STYLE |= style_flag

# common/dict_tools.py
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
    "favorite_standard_shortcuts_splitter_sash",
    "favorite_panel_above_tree",
    "favorite_paths",
    "standard_shortcuts_visible",
    "standard_shortcuts_visibility",
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

# common/window_tools.py
KNOWN_FOLDER_IDS = {
    "desktop": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
    "documents": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
    "downloads": "374DE290-123F-4565-9164-39C4925E467B",
    "pictures": "33E28130-4E1E-4676-835A-98395C3BC3BB",
    "music": "4BD8D571-6D19-48D3-BE97-422220080E43",
    "videos": "18989B1D-99B5-455B-841C-AB7C74E4DDFC",
}

# controls/favorite_panel.py
STANDARD_SHORTCUT_DEFINITIONS = (
    {"key": "desktop", "label": "Desktop", "default": True},
    {"key": "documents", "label": "Documents", "default": True},
    {"key": "downloads", "label": "Downloads", "default": False},
    {"key": "images", "label": "Images", "default": False},
    {"key": "music", "label": "Music", "default": False},
    {"key": "video", "label": "Videos", "default": False},
    {"key": "recycle_bin", "label": "Recycle Bin", "default": True},
)

# controls/file_preview.py
PAGE_VIEW_MODE_1_WIDE = "1_page_wide"
PAGE_VIEW_MODE_2_WIDE = "2_pages_wide"
PAGE_VIEW_MODE_1_TALL = "1_page_tall"
PAGE_VIEW_MODE_MANUAL = "manual"
FIXED_PAGE_VIEW_MODES = {PAGE_VIEW_MODE_1_WIDE, PAGE_VIEW_MODE_2_WIDE, PAGE_VIEW_MODE_1_TALL}
VALID_PAGE_VIEW_MODES = FIXED_PAGE_VIEW_MODES | {PAGE_VIEW_MODE_MANUAL}
HTML_EXTENSIONS = {".html", ".htm"}
TEXT_FILE_EXTENSIONS = {
    ".txt", ".text", ".log", ".md", ".markdown", ".rst", ".csv", ".tsv",
    ".py", ".pyw", ".pyx",
    ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp",
    ".cs", ".vb", ".fs", ".fsx",
    ".java", ".kt", ".kts", ".scala",
    ".go", ".rs", ".swift", ".php", ".rb", ".pl", ".pm", ".lua", ".r", ".dart",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".config", ".properties", ".env", ".reg",
    ".bat", ".cmd", ".ps1", ".psm1", ".sh", ".bash", ".zsh", ".fish", ".vbs", ".vbe",
    ".sql", ".ddl", ".dml",
}

# controls/splitter_utils.py
DEFAULT_SHORTCUTS_SASH = 120
MIN_SHORTCUTS_SASH = 40
MAX_SHORTCUTS_SASH = 400

# controls/video_preview.py
VIDEO_EXTENSIONS = frozenset({
    ".mp4", ".m4v", ".avi", ".mkv", ".mov", ".wmv", ".webm",
    ".mpg", ".mpeg", ".mpe", ".ts", ".mts", ".m2ts", ".3gp", ".ogv",
})

# file_operations/archive_helper.py
_ARCHIVE_SUFFIXES = (".tar.gz", ".tar.bz2", ".tar.xz", ".tar.zst", ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".cab")

# file_operations/copy_and_paste.py
CLIPBOARD_MODE_COPY = "copy"
CLIPBOARD_MODE_CUT = "cut"
_OVERWRITE_DECISION = None

# file_operations/document_types.py
WORD_EXTENSIONS = frozenset({".doc", ".docx", ".docm"})
EXCEL_EXTENSIONS = frozenset({".xls", ".xlsx", ".xlsm"})
POWERPOINT_EXTENSIONS = frozenset({".ppt", ".pptx", ".pptm"})
HTML_OFFICE_EXTENSIONS = WORD_EXTENSIONS | EXCEL_EXTENSIONS
OFFICE_EXTENSIONS = HTML_OFFICE_EXTENSIONS | POWERPOINT_EXTENSIONS

# file_operations/image_utils.py
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp", ".jfif"}

# file_operations/office_html_preview.py
_CACHE_ROOT = os.path.join(tempfile.gettempdir(), "docexplorer_office_html")

# file_operations/office_preview.py
_OFFICE_OPEN_CHECK_TIMEOUT = 0.5

# file_operations/pdf_utils.py
DEFAULT_OPTIMIZE_IMAGE_WIDTH = 1000
DEFAULT_OPTIMIZE_IMAGE_QUALITY = 70
DEFAULT_COLOR_TARGET_DPI = 110
DEFAULT_COLOR_THRESHOLD_DPI = 140
DEFAULT_COLOR_COMPRESSION = "jpeg"
DEFAULT_COLOR_QUALITY = "medium"
DEFAULT_MONO_TARGET_DPI = 110
DEFAULT_MONO_THRESHOLD_DPI = 140
DEFAULT_MONO_COMPRESSION = "png"
DEFAULT_COMPRESS_ONLY_IF_RESIZED = False
PDF_PREVIEW_RENDER_QUALITY_MULTIPLIER = 3.5
PDF_PREVIEW_MIN_RENDER_SCALE = 0.75
PDF_PREVIEW_MAX_RENDER_SCALE = 2.5
PDF_PREVIEW_MAX_RENDER_HEIGHT = 1600
DEFAULT_SHOW_PAGES_LIMIT = 10
DEFAULT_PDF_SHOW_PAGES_LIMIT = 50
DEFAULT_WORD_SHOW_PAGES_LIMIT = 10
DEFAULT_EXCEL_SHOW_PAGES_LIMIT = 1
DEFAULT_OTHER_SHOW_PAGES_LIMIT = 10

# file_operations/recycle_bin.py
RECYCLE_BIN_PATH = "shell:RecycleBinFolder"
CSIDL_BITBUCKET = 10

# controls/help_form.py
HELP_RELATIVE_PATH = os.path.join("docs", "help", "index.html")
MANUAL_RELATIVE_PATH = os.path.join("docs", "DocExplorer_User_Manual.pdf")

# main.py
LANGUAGE_CHOICES = [
    ("EN", "en"),
    ("UA", "uk"),
    ("DE", "de"),
    ("FR", "fr"),
    ("ES", "es"),
    ("IT", "it"),
    ("PT-BR", "pt_br"),
    ("JA", "ja"),
    ("KO", "ko"),
    ("ZH-CN", "zh_cn"),
    ("RU", "ru"),
]
LANGUAGE_LABEL_BY_CODE = {code: label for label, code in LANGUAGE_CHOICES}
LANGUAGE_CODE_BY_LABEL = {label: code for label, code in LANGUAGE_CHOICES}
LANGUAGE_CHOICES_SORTED = sorted(LANGUAGE_CHOICES, key=lambda item: item[0])
SUPPORTED_LOCALES = set(LANGUAGE_LABEL_BY_CODE.keys())

__all__ = [
    "FILE_ATTRIBUTE_HIDDEN",
    "LOCALE_NAME_USER_DEFAULT",
    "LOCALE_SSHORTDATE",
    "DATE_PICKER_STYLE",
    "PERSISTED_LAYOUT_KEYS",
    "OPTION_GROUP_ORDER",
    "OPTION_GROUP_TRANSLATION_KEYS",
    "OPTION_FIELDS",
    "KNOWN_FOLDER_IDS",
    "STANDARD_SHORTCUT_DEFINITIONS",
    "PAGE_VIEW_MODE_1_WIDE",
    "PAGE_VIEW_MODE_2_WIDE",
    "PAGE_VIEW_MODE_1_TALL",
    "PAGE_VIEW_MODE_MANUAL",
    "FIXED_PAGE_VIEW_MODES",
    "VALID_PAGE_VIEW_MODES",
    "HTML_EXTENSIONS",
    "TEXT_FILE_EXTENSIONS",
    "DEFAULT_SHORTCUTS_SASH",
    "MIN_SHORTCUTS_SASH",
    "MAX_SHORTCUTS_SASH",
    "VIDEO_EXTENSIONS",
    "_ARCHIVE_SUFFIXES",
    "CLIPBOARD_MODE_COPY",
    "CLIPBOARD_MODE_CUT",
    "_OVERWRITE_DECISION",
    "WORD_EXTENSIONS",
    "EXCEL_EXTENSIONS",
    "POWERPOINT_EXTENSIONS",
    "HTML_OFFICE_EXTENSIONS",
    "OFFICE_EXTENSIONS",
    "IMAGE_EXTENSIONS",
    "_CACHE_ROOT",
    "_OFFICE_OPEN_CHECK_TIMEOUT",
    "DEFAULT_OPTIMIZE_IMAGE_WIDTH",
    "DEFAULT_OPTIMIZE_IMAGE_QUALITY",
    "DEFAULT_COLOR_TARGET_DPI",
    "DEFAULT_COLOR_THRESHOLD_DPI",
    "DEFAULT_COLOR_COMPRESSION",
    "DEFAULT_COLOR_QUALITY",
    "DEFAULT_MONO_TARGET_DPI",
    "DEFAULT_MONO_THRESHOLD_DPI",
    "DEFAULT_MONO_COMPRESSION",
    "DEFAULT_COMPRESS_ONLY_IF_RESIZED",
    "PDF_PREVIEW_RENDER_QUALITY_MULTIPLIER",
    "PDF_PREVIEW_MIN_RENDER_SCALE",
    "PDF_PREVIEW_MAX_RENDER_SCALE",
    "PDF_PREVIEW_MAX_RENDER_HEIGHT",
    "DEFAULT_SHOW_PAGES_LIMIT",
    "DEFAULT_PDF_SHOW_PAGES_LIMIT",
    "DEFAULT_WORD_SHOW_PAGES_LIMIT",
    "DEFAULT_EXCEL_SHOW_PAGES_LIMIT",
    "DEFAULT_OTHER_SHOW_PAGES_LIMIT",
    "RECYCLE_BIN_PATH",
    "CSIDL_BITBUCKET",
    "HELP_RELATIVE_PATH",
    "MANUAL_RELATIVE_PATH",
    "LANGUAGE_CHOICES",
    "LANGUAGE_LABEL_BY_CODE",
    "LANGUAGE_CODE_BY_LABEL",
    "LANGUAGE_CHOICES_SORTED",
    "SUPPORTED_LOCALES",
]
