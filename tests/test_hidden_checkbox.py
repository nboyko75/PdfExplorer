import inspect
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import wx

import controls.filelist as filelist
import main


class HiddenCheckboxToggleTests(unittest.TestCase):
    def test_toggling_hidden_checkbox_refreshes_tree_and_list(self):
        owner = types.SimpleNamespace(
            show_hidden=False,
            hidden_chk=types.SimpleNamespace(GetValue=lambda: True),
            refresh=mock.MagicMock(),
            tree=object(),
        )

        with mock.patch.object(main.tree_utils, "refresh_tree_selection_and_filelist") as mocked_refresh_tree:
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

    def test_main_menu_and_manual_cover_context_actions(self):
        import controls.help_form as help_form

        main_menu_source = inspect.getsource(main.FileExplorer._build_main_menu_bar)
        help_source = inspect.getsource(help_form.show_app_manual_form)

        self.assertIn("self.file_print_item", main_menu_source)
        self.assertIn("self.file_archive_item", main_menu_source)
        self.assertIn("self.file_extract_archive_item", main_menu_source)
        self.assertIn("self.doc_optimize_all_item", main_menu_source)
        self.assertIn("self.doc_adjust_all_page_width_item", main_menu_source)

        self.assertIn("Print - print the selected file.", help_source)
        self.assertIn("Add to archive / Extract from archive - package or unpack selected files.", help_source)
        self.assertIn("Optimize all PDF / Adjust page width all - batch-process PDFs in a folder or file.", help_source)

    def test_folder_up_action_uses_parent_directory(self):
        owner = types.SimpleNamespace(
            path_box=types.SimpleNamespace(GetValue=lambda: r"D:\Projects\Current\Child"),
            open_path=mock.MagicMock(return_value=True),
            select_tree_item_by_path=mock.MagicMock(),
        )

        self.assertTrue(hasattr(main.FileExplorer, "on_folder_up"))
        main.FileExplorer.on_folder_up(owner, None)

        owner.open_path.assert_called_once_with(r"D:\Projects\Current", add_history=True)
        owner.select_tree_item_by_path.assert_called_once_with(r"D:\Projects\Current")

    def test_double_click_expands_selected_folder_in_tree_and_list(self):
        tree = mock.MagicMock()
        tree.IsExpanded.return_value = False
        owner = types.SimpleNamespace(tree=tree, open_path=mock.MagicMock(), select_tree_item_by_path=mock.MagicMock())
        item = mock.MagicMock()
        item.IsOk.return_value = True
        item_path = r"D:\Projects\Folder"
        owner.tree.GetItemData.return_value = item_path
        owner.tree.GetSelection.return_value = item

        event = types.SimpleNamespace(GetItem=lambda: item)
        tree_utils = __import__("controls.tree_utils", fromlist=["on_tree_activated"])
        tree_utils.on_tree_activated(owner, event)

        owner.tree.Expand.assert_called_once_with(item)
        owner.open_path.assert_called_once_with(item_path)

        owner_list = types.SimpleNamespace(select_tree_item_by_path=mock.MagicMock(), path_box=types.SimpleNamespace(GetValue=lambda: ""))
        with mock.patch.object(filelist, "open_path_or_file") as mocked_open:
            filelist.on_list_open(owner_list, None, path=r"D:\Projects\Folder")

        owner_list.select_tree_item_by_path.assert_called_once_with(r"D:\Projects\Folder")
        mocked_open.assert_called_once_with(owner_list, r"D:\Projects\Folder")

    def test_build_office_page_range_accepts_range_strings(self):
        import controls.print_form as print_form

        self.assertEqual(print_form._build_office_page_range("2-3"), "2-3")
        self.assertEqual(print_form._build_office_page_range([1, 2]), "2-3")

    def test_selected_printer_setup_uses_windows_properties_dialog(self):
        import controls.print_form as print_form

        fake_printer = mock.MagicMock()
        fake_devmode = mock.MagicMock()
        fake_win32print = mock.MagicMock()
        fake_win32con = types.SimpleNamespace(DM_IN_PROMPT=4, DM_OUT_BUFFER=2)
        fake_win32print.OpenPrinter.return_value = fake_printer
        fake_win32print.GetPrinter.return_value = (None, None, None, fake_devmode)

        with mock.patch.object(print_form, "win32print", fake_win32print), \
             mock.patch.object(print_form, "win32con", fake_win32con):
            print_form._show_printer_properties("Printer One")

        fake_win32print.OpenPrinter.assert_called_once_with("Printer One")
        fake_win32print.DocumentProperties.assert_called_once_with(
            0,
            fake_printer,
            "Printer One",
            fake_devmode,
            fake_devmode,
            fake_win32con.DM_IN_PROMPT | fake_win32con.DM_OUT_BUFFER,
        )

    def test_print_with_selected_printer_supports_office_subset_pages(self):
        import controls.print_form as print_form

        fake_win32print = mock.MagicMock()
        fake_win32print.GetDefaultPrinter.return_value = "Printer One"
        fake_win32print.SetDefaultPrinter.return_value = None
        fake_win32print.OpenPrinter.return_value = mock.MagicMock()
        fake_win32print.GetPrinter.return_value = (None, None, None, mock.MagicMock(Copies=1))

        fake_word_app = mock.MagicMock()
        fake_word_doc = mock.MagicMock()
        fake_win32_client = mock.MagicMock()
        fake_win32_client.GetActiveObject.side_effect = Exception("no active office")
        fake_win32_client.DispatchEx.return_value = fake_word_app
        fake_word_app.Documents.Open.return_value = fake_word_doc

        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = os.path.join(temp_dir, "doc.docx")
            with open(source_path, "w", encoding="utf-8") as handle:
                handle.write("office")

            with mock.patch.object(print_form, "win32print", fake_win32print), \
                 mock.patch.object(print_form, "win32api", object()), \
                 mock.patch.object(print_form, "fitz", None), \
                 mock.patch.object(print_form, "win32_client", fake_win32_client), \
                 mock.patch.object(print_form, "pythoncom", None), \
                 mock.patch.object(print_form.office_preview, "can_preview_office", return_value=True), \
                 mock.patch.object(print_form.os, "startfile") as mocked_startfile:
                result = print_form._print_with_selected_printer(source_path, "Printer One", page_numbers=[0, 2])

            self.assertEqual(result, "Printer One")
            fake_win32_client.DispatchEx.assert_called_once_with("Word.Application")
            fake_word_doc.PrintOut.assert_called_once_with(Copies=1, Pages="1,3", Range=4, Background=False)
            mocked_startfile.assert_not_called()


if __name__ == "__main__":
    unittest.main()
