"""Shared Office extension groups for preview routing."""

WORD_EXTENSIONS = frozenset({".doc", ".docx", ".docm"})
EXCEL_EXTENSIONS = frozenset({".xls", ".xlsx", ".xlsm"})
POWERPOINT_EXTENSIONS = frozenset({".ppt", ".pptx", ".pptm"})
HTML_OFFICE_EXTENSIONS = WORD_EXTENSIONS | EXCEL_EXTENSIONS
OFFICE_EXTENSIONS = HTML_OFFICE_EXTENSIONS | POWERPOINT_EXTENSIONS
