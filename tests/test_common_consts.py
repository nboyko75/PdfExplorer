from common import consts
from common.system import FILE_ATTRIBUTE_HIDDEN
from file_operations.pdf_utils import DEFAULT_OPTIMIZE_IMAGE_WIDTH, DEFAULT_PDF_SHOW_PAGES_LIMIT


def test_common_consts_exports_expected_values():
    assert consts.FILE_ATTRIBUTE_HIDDEN == FILE_ATTRIBUTE_HIDDEN
    assert consts.DEFAULT_OPTIMIZE_IMAGE_WIDTH == DEFAULT_OPTIMIZE_IMAGE_WIDTH
    assert consts.DEFAULT_PDF_SHOW_PAGES_LIMIT == DEFAULT_PDF_SHOW_PAGES_LIMIT
    assert consts.VIDEO_EXTENSIONS == frozenset({
        ".mp4", ".m4v", ".avi", ".mkv", ".mov", ".wmv", ".webm",
        ".mpg", ".mpeg", ".mpe", ".ts", ".mts", ".m2ts", ".3gp", ".ogv",
    })
