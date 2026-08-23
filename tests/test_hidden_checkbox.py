import os
import sys
import tempfile
import types
import unittest
from unittest import mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import wx

import main


class HiddenCheckboxToggleTests(unittest.TestCase):
    def test_toggling_hidden_checkbox_refreshes_tree_and_list(self):
        owner = types.SimpleNamespace(
            show_hidden=False,
            hidden_chk=types.SimpleNamespace(GetValue=lambda: True),
            refresh=mock.MagicMock(),
            tree=object(),
        )

        with mock.patch.object(main.tree_utils, "refresh_tree_selection") as mocked_refresh_tree:
            main.FileExplorer.on_toggle_hidden(owner, None)

        self.assertTrue(owner.show_hidden)
        owner.refresh.assert_called_once_with()
        mocked_refresh_tree.assert_called_once_with(owner)

    def test_tree_refresh_menu_refreshes_filelist_for_current_folder(self):
        owner = types.SimpleNamespace(
            tree=mock.MagicMock(),
            path_box=types.SimpleNamespace(GetValue=lambda: "D:/Projects"),
            load_folder=mock.MagicMock(),
        )
        item = mock.MagicMock()
        item.IsOk.return_value = True
        owner.tree.GetSelection.return_value = item
        owner.tree.GetItemData.return_value = "D:/Projects"

        with mock.patch.object(main.tree_utils, "refresh_tree_subtree") as mocked_refresh_tree_subtree:
            main.tree_utils.refresh_tree_selection_and_filelist(owner)

        owner.load_folder.assert_called_once_with("D:\\Projects")
        mocked_refresh_tree_subtree.assert_called_once_with(owner, item, "D:\\Projects")

    def test_load_folder_uses_file_extension_in_type_column(self):
        owner = types.SimpleNamespace(
            show_hidden=False,
            search_box=types.SimpleNamespace(GetValue=lambda: ""),
            list=mock.MagicMock(),
            update_list_sort_header_icons=mock.MagicMock(),
            update_list_toolbar_buttons=mock.MagicMock(),
        )
        owner.list.InsertItem.return_value = 0

        with mock.patch("file_operations.image_utils.get_list_icon_index", return_value=0):
            with tempfile.TemporaryDirectory() as temp_dir:
                file_path = os.path.join(temp_dir, "sample.pdf")
                with open(file_path, "w", encoding="utf-8") as handle:
                    handle.write("content")

                main.navigation_utils.load_folder(owner, temp_dir)

        owner.list.SetItem.assert_any_call(0, 1, "pdf")

    def test_drag_and_drop_refresh_delegates_to_filelist_refresh(self):
        import controls.drag_and_drop as drag_and_drop_module

        owner = object()
        called = {}

        def fake_refresh(target_owner, affected_dirs=None, preferred_preview_path=None):
            called["owner"] = target_owner
            called["dirs"] = affected_dirs
            called["preview"] = preferred_preview_path
            return "ok"

        fake_filelist = types.SimpleNamespace(_refresh_after_fs_change=fake_refresh)
        with mock.patch.dict(sys.modules, {"controls.filelist": fake_filelist}, clear=False):
            result = drag_and_drop_module._refresh_after_fs_change(owner, affected_dirs=["D:/Temp"], preferred_preview_path="D:/Temp/file.txt")

        self.assertEqual(result, "ok")
        self.assertIs(called["owner"], owner)
        self.assertEqual(called["dirs"], ["D:/Temp"])
        self.assertEqual(called["preview"], "D:/Temp/file.txt")

    def test_non_conflicting_path_helper_is_single_shared_implementation(self):
        import file_operations.copy_and_paste as copy_and_paste_module
        import controls.drag_and_drop as drag_and_drop_module

        self.assertIs(drag_and_drop_module._build_non_conflicting_path, copy_and_paste_module._build_non_conflicting_path)

        with tempfile.TemporaryDirectory() as temp_dir:
            target_path = os.path.join(temp_dir, "report.txt")
            with open(target_path, "w", encoding="utf-8") as handle:
                handle.write("first")

            candidate = copy_and_paste_module._build_non_conflicting_path(target_path)
            self.assertTrue(candidate.startswith(os.path.join(temp_dir, "report - Copy")))
            self.assertNotEqual(candidate, target_path)

    def test_hidden_image_makes_bitmap_dimmer(self):
        import file_operations.image_utils as image_utils

        original = wx.Image(2, 2)
        original.SetRGB(0, 0, 255, 0, 0)
        original.SetRGB(0, 1, 0, 255, 0)
        original.SetRGB(1, 0, 0, 0, 255)
        original.SetRGB(1, 1, 200, 200, 200)

        dimmed = image_utils.Hidden_Image(original)
        self.assertTrue(dimmed.IsOk())
        self.assertLess(dimmed.GetRed(0, 0), original.GetRed(0, 0))
        self.assertLess(dimmed.GetGreen(0, 1), original.GetGreen(0, 1))

    def test_hidden_image_works_for_images_without_alpha(self):
        import file_operations.image_utils as image_utils

        image = wx.Image(2, 2)
        image.SetRGB(0, 0, 100, 80, 60)
        image.SetRGB(1, 1, 10, 20, 30)

        dimmed = image_utils.Hidden_Image(image)
        self.assertTrue(dimmed.IsOk())
        self.assertTrue(dimmed.HasAlpha())
        self.assertLess(dimmed.GetRed(0, 0), image.GetRed(0, 0))

    def test_print_button_and_print_translation_are_available(self):
        import localization
        import controls.filelist as filelist

        self.assertIn("context_print", localization.TRANSLATIONS)
        self.assertIn("print_dialog_title", localization.TRANSLATIONS)
        self.assertIn("print_button", localization.TRANSLATIONS)
        self.assertTrue(hasattr(filelist, "on_list_print"))
        self.assertTrue(callable(filelist.on_list_print))


if __name__ == "__main__":
    unittest.main()
