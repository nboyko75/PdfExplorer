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

    def test_icon_manager_accepts_favorite_icon_aliases(self):
        image_utils = _import_image_utils_with_mocked_wx()
        with mock.patch("file_operations.image_utils.os.path.isfile", return_value=True):
            manager = image_utils.IconManager(images_dir="/tmp/icons")

        self.assertIn("add_to_favorites", manager.icon_files)
        self.assertIn("remove_from_favorites", manager.icon_files)
        self.assertEqual(manager.icon_files["add_to_favorites"], os.path.join("/tmp/icons", "add_to_favorite.bmp"))
        self.assertEqual(manager.icon_files["remove_from_favorites"], os.path.join("/tmp/icons", "remove_from_favorite.bmp"))

    def test_real_shortcut_folder_uses_path_without_file_attribute_flag(self):
        import controls.favorite_panel as favorite_panel

        owner = mock.Mock()
        owner.standard_shortcuts_image_list = mock.Mock()
        owner.standard_shortcuts_icon_indexes = {}
        owner.favorite_folder_icon_index = -1
        shortcut = {"path": "C:/Temp/folder.lnk", "key": "custom"}

        with mock.patch.object(favorite_panel.image_utils, "get_shell_bitmap", return_value=mock.Mock(IsOk=mock.Mock(return_value=True))) as mocked_get:
            favorite_panel._standard_shortcut_icon_index(owner, shortcut)

        mocked_get.assert_called_once_with("C:/Temp/folder.lnk")

    def test_real_shell_icon_uses_existing_path_without_file_attribute_flag(self):
        image_utils = _import_image_utils_with_mocked_wx()
        fake_windll = mock.Mock()

        def fake_shgetfileinfo(path, attributes, info_ptr, info_size, flags):
            info_ptr._obj.hIcon = 123
            return 1

        fake_windll.shell32.SHGetFileInfoW.side_effect = fake_shgetfileinfo
        fake_windll.user32.DestroyIcon.return_value = None

        with mock.patch.object(image_utils, "hicon_to_bitmap", return_value=mock.Mock(IsOk=mock.Mock(return_value=True))) as mocked_hicon, \
             mock.patch.object(image_utils.os.path, "exists", return_value=True), \
             mock.patch.object(image_utils.ctypes, "windll", fake_windll):
            result = image_utils.get_real_shell_bitmap(r"C:\\Temp\\app.lnk")

        self.assertIsNotNone(result)
        self.assertEqual(fake_windll.shell32.SHGetFileInfoW.call_args[0][0], r"C:\\Temp\\app.lnk")
        self.assertFalse(fake_windll.shell32.SHGetFileInfoW.call_args[0][4] & 0x00000010)
        mocked_hicon.assert_called_once()

    def test_shell_icon_cache_is_unique_per_image_list(self):
        image_utils = _import_image_utils_with_mocked_wx()
        owner = mock.Mock()
        owner.list_images = mock.Mock()
        owner.list_images.Add.side_effect = [21, 22]
        owner.tree_images = mock.Mock()
        owner.tree_images.Add.side_effect = [31, 32]
        owner.list_shell_icon_indexes = {}
        owner.tree_shell_icon_indexes = {}

        with mock.patch.object(image_utils, "get_real_shell_bitmap", return_value=mock.Mock(IsOk=mock.Mock(return_value=True))), \
             mock.patch.object(image_utils.os.path, "exists", return_value=True), \
             mock.patch.object(image_utils.os.path, "abspath", side_effect=lambda value: value), \
             mock.patch.object(image_utils.os.path, "normcase", side_effect=lambda value: value):
            first_list = image_utils.get_file_list_shell_icon_index(owner, r"C:\Temp\app.lnk")
            second_tree = image_utils.get_tree_shell_icon_index(owner, r"C:\Temp\app.lnk")
            third_list = image_utils.get_file_list_shell_icon_index(owner, r"C:\Temp\app.lnk")

        self.assertEqual(first_list, 21)
        self.assertEqual(second_tree, 31)
        self.assertEqual(third_list, 21)
        self.assertEqual(owner.list_images.Add.call_count, 1)
        self.assertEqual(owner.tree_images.Add.call_count, 1)

    def test_generic_folder_icon_requests_file_attributes_flag(self):
        image_utils = _import_image_utils_with_mocked_wx()
        fake_windll = mock.Mock()
        fake_windll.shell32.SHGetFileInfoW.return_value = 1
        fake_windll.user32.DestroyIcon.return_value = None

        with mock.patch.object(image_utils.ctypes, "windll", fake_windll), \
             mock.patch.object(image_utils, "hicon_to_bitmap", return_value=mock.Mock(IsOk=mock.Mock(return_value=True))):
            image_utils.get_shell_bitmap("folder", 0x00000010, use_file_attributes=True)

        flags = fake_windll.shell32.SHGetFileInfoW.call_args[0][4]
        self.assertTrue(flags & 0x00000010)

    def test_recycle_bin_uses_stock_icon_not_desktop_path(self):
        import controls.favorite_panel as favorite_panel

        owner = mock.Mock()
        owner.standard_shortcuts_image_list = mock.Mock()
        owner.standard_shortcuts_folder_icon_index = -1
        owner.standard_shortcuts_icon_indexes = {}
        shortcut = {"path": "C:/Users/User/Desktop/Recycle Bin", "key": "recycle_bin"}

        with mock.patch.object(favorite_panel.image_utils, "get_recycle_bin_icon_bitmap", return_value=mock.Mock(IsOk=mock.Mock(return_value=True))) as mocked_get:
            favorite_panel._standard_shortcut_icon_index(owner, shortcut)

        mocked_get.assert_called_once_with()

    def test_standard_shortcut_icon_cache_reuses_existing_index(self):
        import controls.favorite_panel as favorite_panel

        owner = mock.Mock()
        owner.standard_shortcuts_image_list = mock.Mock()
        owner.standard_shortcuts_image_list.Add.side_effect = [11, 12]
        owner.standard_shortcuts_icon_indexes = {}
        shortcut = {"path": "C:/Temp/desktop.lnk", "key": "desktop"}

        with mock.patch.object(favorite_panel.image_utils, "get_shell_bitmap", return_value=mock.Mock(IsOk=mock.Mock(return_value=True))):
            first = favorite_panel._standard_shortcut_icon_index(owner, shortcut)
            second = favorite_panel._standard_shortcut_icon_index(owner, shortcut)

        self.assertEqual(first, 11)
        self.assertEqual(second, 11)
        owner.standard_shortcuts_image_list.Add.assert_called_once_with(mock.ANY)

    def test_shortcut_link_uses_shell_icon_in_list_and_tree(self):
        import controls.tree_utils as tree_utils

        owner = mock.Mock()
        owner.tree_images = mock.Mock()
        owner.tree_icon_cache = {}
        owner.tree_icon_file = 7
        owner.tree_shell_icon_indexes = {}
        owner.tree_images.Add.side_effect = [11]

        shortcut_path = r"C:\Users\User\Desktop\App.lnk"
        with mock.patch.object(tree_utils.image_utils, "get_real_shell_bitmap", return_value=mock.Mock(IsOk=mock.Mock(return_value=True))), \
             mock.patch.object(tree_utils.image_utils, "create_extension_icon_bitmap") as mocked_create:
            result = tree_utils.get_tree_icon_index(owner, shortcut_path, is_dir=False)

        self.assertEqual(result, 11)
        mocked_create.assert_not_called()

        owner.list_images = mock.Mock()
        owner.list_icon_cache = {}
        owner.list_shell_icon_indexes = {}
        owner.list_images.Add.side_effect = [12]

        with mock.patch.object(tree_utils.image_utils, "get_real_shell_bitmap", return_value=mock.Mock(IsOk=mock.Mock(return_value=True))), \
             mock.patch.object(tree_utils.image_utils, "create_extension_icon_bitmap") as mocked_create_list:
            result = tree_utils.image_utils.get_file_list_shell_icon_index(owner, shortcut_path)

        self.assertEqual(result, 12)
        mocked_create_list.assert_not_called()


if __name__ == "__main__":
    unittest.main()
