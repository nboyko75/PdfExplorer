import importlib
import os
import sys
import unittest
from unittest import mock


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


def _import_image_utils_with_mocked_wx():
    fake_wx = mock.MagicMock(name="wx")
    with mock.patch.dict(sys.modules, {"wx": fake_wx}):
        sys.modules.pop("file_operations.image_utils", None)
        return importlib.import_module("file_operations.image_utils")


class ImageUtilsFallbackTests(unittest.TestCase):
    def test_can_preview_image_uses_wx_reader_when_available(self):
        image_utils = _import_image_utils_with_mocked_wx()
        image_utils.wx.Image.CanRead.return_value = True

        with mock.patch("file_operations.image_utils.os.path.isfile", return_value=True), \
             mock.patch.object(image_utils, "_can_read_with_pillow") as fallback_reader:
            self.assertTrue(image_utils.can_preview_image("sample.png"))

        fallback_reader.assert_not_called()

    def test_can_preview_image_falls_back_when_wx_reader_fails(self):
        image_utils = _import_image_utils_with_mocked_wx()
        image_utils.wx.Image.CanRead.side_effect = RuntimeError("libpng warning")

        with mock.patch("file_operations.image_utils.os.path.isfile", return_value=True), \
             mock.patch.object(image_utils, "_can_read_with_pillow", return_value=True) as fallback_reader:
            self.assertTrue(image_utils.can_preview_image("sample.png"))

        fallback_reader.assert_called_once_with("sample.png")


if __name__ == "__main__":
    unittest.main()
