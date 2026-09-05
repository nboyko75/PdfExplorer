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

import common.system as system
import controls.favorite_panel as favorite_panel
import controls.filelist as filelist
import file_operations.image_utils as image_utils
import main


class HiddenCheckboxToggleTests(unittest.TestCase):
    def test_is_hidden_returns_false_for_missing_paths(self):
        missing_path = os.path.join(tempfile.gettempdir(), "definitely_missing_path_12345")
        self.assertFalse(system.is_hidden(missing_path))

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

    def test_favorite_context_menu_remove_is_disabled_without_selection(self):
        owner = main.FileExplorer.__new__(main.FileExplorer)
        owner.favorite_paths = ["C:/Temp/favorites"]
        owner.favorite_list = mock.MagicMock()
        owner.favorite_list.GetFirstSelected.return_value = wx.NOT_FOUND
        owner.favorite_list.HitTest.return_value = (wx.NOT_FOUND, wx.DefaultPosition)
        owner.favorite_list.PopupMenu = mock.Mock()
        owner.Bind = mock.Mock()

        remove_item = mock.Mock()
        fake_menu = mock.MagicMock()
        fake_menu.Append.return_value = remove_item

        with mock.patch.object(wx, "Menu", return_value=fake_menu):
            owner.on_favorite_right_click(mock.MagicMock())

        remove_item.Enable.assert_called_with(False)

    def test_favorite_delete_key_removes_selected_item(self):
        owner = main.FileExplorer.__new__(main.FileExplorer)
        owner.favorite_paths = ["C:/Temp/one", "C:/Temp/two"]
        owner.favorite_list = mock.MagicMock()
        owner.favorite_list.GetFirstSelected.return_value = 1
        owner._remove_favorite_path = mock.Mock()

        event = mock.MagicMock()
        event.GetKeyCode.return_value = wx.WXK_DELETE

        favorite_panel.on_favorite_key_down(owner, event)

        owner._remove_favorite_path.assert_called_once_with("C:/Temp/two")

    def test_favorite_list_layout_stretches_to_panel(self):
        owner = main.FileExplorer.__new__(main.FileExplorer)
        owner.favorite_list = mock.MagicMock()
        owner.favorite_panel = mock.MagicMock()
        owner.favorite_panel.GetSize.return_value = types.SimpleNamespace(GetWidth=lambda: 400, GetHeight=lambda: 300)

        owner._apply_favorite_list_layout()

        owner.favorite_list.SetColumnWidth.assert_called_with(0, 384)
        owner.favorite_list.Layout.assert_called_once()

    def test_favorite_panel_resize_updates_column_width(self):
        owner = main.FileExplorer.__new__(main.FileExplorer)
        owner.favorite_list = mock.MagicMock()
        owner.favorite_panel = mock.MagicMock()
        owner.favorite_panel.GetSize.return_value = types.SimpleNamespace(GetWidth=lambda: 320, GetHeight=lambda: 200)

        favorite_panel.on_favorite_panel_resize(owner, mock.MagicMock())

        owner.favorite_list.SetColumnWidth.assert_called_with(0, 304)

    def test_standard_shortcuts_column_stretches_to_full_panel_width(self):
        owner = main.FileExplorer.__new__(main.FileExplorer)
        owner.standard_shortcuts_list = mock.MagicMock()
        owner.standard_shortcuts_panel = mock.MagicMock()
        owner.standard_shortcuts_panel.GetSize.return_value = types.SimpleNamespace(GetWidth=lambda: 320, GetHeight=lambda: 200)
        owner.favorite_panel = mock.MagicMock()
        owner.favorite_panel.GetSizer.return_value = mock.MagicMock()

        favorite_panel._apply_standard_shortcuts_layout(owner)

        owner.standard_shortcuts_list.SetColumnWidth.assert_called_with(0, 304)

    def test_favorite_row_move_controls_reorder_selected_item(self):
        owner = main.FileExplorer.__new__(main.FileExplorer)
        owner.favorite_paths = ["C:/Temp/a", "C:/Temp/b", "C:/Temp/c"]
        owner.favorite_list = mock.MagicMock()
        owner.favorite_list.GetFirstSelected.return_value = 1
        owner._reorder_favorite_paths = mock.Mock(return_value=True)

        favorite_panel.on_favorite_row_move_down(owner, None)
        owner._reorder_favorite_paths.assert_called_once_with(1, 2)

        owner._reorder_favorite_paths.reset_mock()
        favorite_panel.on_favorite_row_move_up(owner, None)
        owner._reorder_favorite_paths.assert_called_once_with(1, 0)

    def test_favorite_drag_move_reorders_paths(self):
        owner = main.FileExplorer.__new__(main.FileExplorer)
        owner.favorite_paths = ["C:/Temp/a", "C:/Temp/b", "C:/Temp/c"]
        owner.favorite_list = mock.MagicMock()
        owner._refresh_favorite_list = mock.Mock()
        owner.save_splitter_positions = mock.Mock()

        owner._reorder_favorite_paths(0, 2)

        self.assertEqual(owner.favorite_paths, ["C:/Temp/b", "C:/Temp/c", "C:/Temp/a"])
        owner.favorite_list.Select.assert_called_once_with(2)
        owner.favorite_list.EnsureVisible.assert_called_once_with(2)
        owner.save_splitter_positions.assert_called_once_with()

    def test_favorite_header_uses_favorites_icon(self):
        owner = main.FileExplorer.__new__(main.FileExplorer)
        owner.favorite_paths = []
        owner.favorite_list = None
        owner.favorite_panel = None
        owner.favorite_move_up_btn = None
        owner.favorite_move_down_btn = None
        owner.on_favorite_list_select = mock.Mock()
        owner.on_favorite_list_activate = mock.Mock()
        owner.on_favorite_begin_drag = mock.Mock()
        owner.on_favorite_end_drag = mock.Mock()
        owner.on_favorite_right_click = mock.Mock()
        owner.on_move_favorite_up = mock.Mock()
        owner.on_move_favorite_down = mock.Mock()

        parent = mock.MagicMock()
        fake_button = mock.MagicMock()
        fake_panel = mock.MagicMock()
        fake_panel.GetSize.return_value = types.SimpleNamespace(GetWidth=lambda: 300, GetHeight=lambda: 200)
        fake_image_list = mock.MagicMock()
        fake_image_list.Add.side_effect = [5, 6, 7, 8, 9]
        fake_bitmap = mock.MagicMock()
        fake_bitmap.IsOk.return_value = True
        with mock.patch.object(image_utils, "create_bitmap_button", return_value=fake_button), \
             mock.patch.object(image_utils, "create_bitmap_button2", return_value=fake_button), \
             mock.patch.object(wx, "Panel", return_value=fake_panel), \
             mock.patch.object(wx, "SplitterWindow", return_value=mock.MagicMock()), \
             mock.patch.object(wx, "ListCtrl", return_value=mock.MagicMock()), \
             mock.patch.object(wx, "ImageList", return_value=fake_image_list), \
             mock.patch.object(wx, "BoxSizer", return_value=mock.MagicMock()), \
             mock.patch.object(wx, "ArtProvider") as art_provider, \
             mock.patch.object(image_utils.IconManager, "get_bitmap", return_value=fake_bitmap):
            art_provider.GetBitmap.return_value = mock.MagicMock(IsOk=lambda: True)
            favorite_panel.build_favorite_panel(owner, parent)

        header_calls = owner.favorite_list.SetColumnImage.call_args_list
        self.assertEqual(header_calls[0], mock.call(0, 5))
        self.assertEqual(header_calls[1], mock.call(0, 6))

    def test_favorite_panel_preserves_sash_size_when_toggling_position(self):
        owner = main.FileExplorer.__new__(main.FileExplorer)
        owner.favorite_splitter = mock.MagicMock()
        owner.favorite_splitter.IsSplit.return_value = True
        owner.favorite_splitter.GetSashPosition.return_value = 440
        owner.favorite_splitter.GetSize.return_value = types.SimpleNamespace(GetHeight=lambda: 600)
        owner.favorite_panel = mock.MagicMock()
        owner.favorite_panel.GetSize.return_value = types.SimpleNamespace(GetWidth=lambda: 300, GetHeight=lambda: 200)
        owner.favorite_panel_above_tree = False
        owner.favorite_list = mock.MagicMock()
        owner.favorite_list.GetItemCount.return_value = 0
        owner.favorite_list.Layout = mock.Mock()
        owner.tree = mock.MagicMock()
        owner.save_splitter_positions = mock.Mock()
        owner.favorite_move_up_btn = mock.MagicMock()
        owner.favorite_move_down_btn = mock.MagicMock()

        favorite_panel.toggle_favorite_panel_position(owner, True)

        self.assertEqual(owner.favorite_panel_above_tree, True)
        owner.favorite_splitter.SetSashPosition.assert_called_with(160)

    def test_standard_shortcuts_toggle_uses_visible_state_on_first_press(self):
        owner = main.FileExplorer.__new__(main.FileExplorer)
        owner.standard_shortcuts_visible = False
        owner.standard_shortcuts_list = mock.MagicMock()
        owner.standard_shortcuts_toggle_btn = mock.MagicMock()
        owner.favorite_panel = mock.MagicMock()
        owner.favorite_panel.GetSizer.return_value = mock.MagicMock()
        owner.favorite_content_splitter = mock.MagicMock()
        owner.favorite_content_splitter.IsSplit.return_value = True
        owner.favorite_content_splitter.GetSashPosition.return_value = 120
        owner.save_splitter_positions = mock.Mock()

        favorite_panel.toggle_standard_shortcuts_panel(owner)

        self.assertTrue(owner.standard_shortcuts_visible)
        owner.standard_shortcuts_list.Show.assert_called_once_with(True)

    def test_standard_shortcuts_toggle_hides_list_when_visible(self):
        owner = main.FileExplorer.__new__(main.FileExplorer)
        owner.standard_shortcuts_visible = True
        owner.standard_shortcuts_list = mock.MagicMock()
        owner.standard_shortcuts_toggle_btn = mock.MagicMock()
        owner.favorite_panel = mock.MagicMock()
        owner.favorite_panel.GetSizer.return_value = mock.MagicMock()
        owner.favorite_content_splitter = mock.MagicMock()
        owner.favorite_content_splitter.IsSplit.return_value = True
        owner.favorite_content_splitter.GetSashPosition.return_value = 120
        owner.save_splitter_positions = mock.Mock()

        favorite_panel.toggle_standard_shortcuts_panel(owner)

        self.assertFalse(owner.standard_shortcuts_visible)
        owner.standard_shortcuts_list.Hide.assert_called_once_with()
        owner.standard_shortcuts_list.Disable.assert_called_once_with()
        owner.favorite_content_splitter.Unsplit.assert_called_once_with(owner.standard_shortcuts_list)

    def test_favorite_content_splitter_owns_its_list_panels(self):
        owner = main.FileExplorer.__new__(main.FileExplorer)
        owner.favorite_paths = []
        owner.on_favorite_list_select = mock.Mock()
        owner.on_favorite_list_activate = mock.Mock()
        owner.on_favorite_begin_drag = mock.Mock()
        owner.on_favorite_end_drag = mock.Mock()
        owner.on_favorite_right_click = mock.Mock()
        owner.on_move_favorite_up = mock.Mock()
        owner.on_move_favorite_down = mock.Mock()
        owner.on_standard_shortcut_list_activate = mock.Mock()
        owner.on_standard_shortcut_right_click = mock.Mock()
        panel_mock = mock.MagicMock()
        panel_mock.GetSize.return_value = types.SimpleNamespace(GetWidth=lambda: 300, GetHeight=lambda: 200)
        panel_mock.GetSizer.return_value = mock.MagicMock()
        panel_mock.Bind = mock.Mock()
        owner.favorite_panel = panel_mock
        owner.favorite_move_up_btn = mock.MagicMock()
        owner.favorite_move_down_btn = mock.MagicMock()
        owner.favorite_row_move_up_btn = mock.MagicMock()
        owner.favorite_row_move_down_btn = mock.MagicMock()
        owner.standard_shortcuts_toggle_btn = mock.MagicMock()
        owner.icon_manager = None
        owner.save_splitter_positions = mock.Mock()
        owner.standard_shortcuts_visible = False

        splitter = mock.MagicMock()
        list_ctrls = [mock.MagicMock(), mock.MagicMock()]
        list_ctrl_factory = mock.Mock(side_effect=list_ctrls)
        fake_image_list = mock.MagicMock()
        fake_image_list.Add.side_effect = [5, 6]
        with mock.patch.object(image_utils, "ensure_owner_icon_manager", return_value=mock.MagicMock()), \
             mock.patch.object(wx, "Panel", return_value=panel_mock), \
             mock.patch.object(wx, "SplitterWindow", return_value=splitter), \
             mock.patch.object(wx, "ListCtrl", list_ctrl_factory), \
             mock.patch.object(wx, "ImageList", return_value=fake_image_list), \
             mock.patch.object(wx, "ArtProvider") as art_provider, \
             mock.patch.object(wx, "BoxSizer", return_value=mock.MagicMock()), \
             mock.patch.object(image_utils, "create_bitmap_button2", return_value=mock.MagicMock()), \
             mock.patch.object(image_utils, "create_bitmap_button", return_value=mock.MagicMock()):
            art_provider.GetBitmap.return_value = mock.MagicMock(IsOk=lambda: False)
            favorite_panel.build_favorite_panel(owner, mock.MagicMock())

        self.assertEqual(list_ctrl_factory.call_args_list[0].args[0], splitter)
        self.assertEqual(list_ctrl_factory.call_args_list[1].args[0], panel_mock)

    def test_standard_shortcuts_list_uses_its_own_image_list(self):
        owner = main.FileExplorer.__new__(main.FileExplorer)
        owner.favorite_paths = []
        owner.on_favorite_list_select = mock.Mock()
        owner.on_favorite_list_activate = mock.Mock()
        owner.on_favorite_begin_drag = mock.Mock()
        owner.on_favorite_end_drag = mock.Mock()
        owner.on_favorite_right_click = mock.Mock()
        owner.on_move_favorite_up = mock.Mock()
        owner.on_move_favorite_down = mock.Mock()
        owner.on_standard_shortcut_list_activate = mock.Mock()
        owner.on_standard_shortcut_right_click = mock.Mock()
        owner.favorite_panel = mock.MagicMock()
        owner.favorite_panel.GetSize.return_value = types.SimpleNamespace(GetWidth=lambda: 300, GetHeight=lambda: 200)
        owner.favorite_panel.GetSizer.return_value = mock.MagicMock()
        owner.favorite_move_up_btn = mock.MagicMock()
        owner.favorite_move_down_btn = mock.MagicMock()
        owner.favorite_row_move_up_btn = mock.MagicMock()
        owner.favorite_row_move_down_btn = mock.MagicMock()
        owner.standard_shortcuts_toggle_btn = mock.MagicMock()
        owner.icon_manager = mock.MagicMock()
        owner.icon_manager.get_bitmap.return_value = mock.MagicMock(IsOk=lambda: True)
        owner.standard_shortcuts_visible = False
        owner.standard_shortcuts_visibility = {}
        owner.save_splitter_positions = mock.Mock()

        splitter = mock.MagicMock()
        favorite_list = mock.MagicMock()
        shortcut_list = mock.MagicMock()
        image_list = mock.MagicMock()
        image_list.Add.side_effect = [11, 12, 13]
        fake_panel = mock.MagicMock()
        fake_panel.GetSize.return_value = types.SimpleNamespace(GetWidth=lambda: 300, GetHeight=lambda: 200)

        with mock.patch.object(image_utils, "ensure_owner_icon_manager", return_value=owner.icon_manager), \
             mock.patch.object(wx, "Panel", return_value=fake_panel), \
             mock.patch.object(wx, "SplitterWindow", return_value=splitter), \
             mock.patch.object(wx, "ListCtrl", side_effect=[favorite_list, shortcut_list]), \
             mock.patch.object(wx, "ImageList", return_value=image_list), \
             mock.patch.object(wx, "ArtProvider") as art_provider, \
             mock.patch.object(wx, "BoxSizer", return_value=mock.MagicMock()), \
             mock.patch.object(image_utils, "create_bitmap_button2", return_value=mock.MagicMock()), \
             mock.patch.object(image_utils, "create_bitmap_button", return_value=mock.MagicMock()):
            art_provider.GetBitmap.return_value = mock.MagicMock(IsOk=lambda: False)
            owner.favorite_panel = favorite_panel.build_favorite_panel(owner, mock.MagicMock())

        self.assertIs(owner.standard_shortcuts_image_list, image_list)
        shortcut_list.SetImageList.assert_called_with(image_list, wx.IMAGE_LIST_SMALL)

    def test_standard_shortcuts_splitter_sash_is_saved_to_config(self):
        owner = main.FileExplorer.__new__(main.FileExplorer)
        owner.favorite_content_splitter = mock.MagicMock()
        owner.favorite_content_splitter.GetSashPosition.return_value = 156
        owner.save_splitter_positions = mock.Mock()

        favorite_panel.on_favorite_content_splitter_sash_changed(owner, mock.MagicMock())

        self.assertEqual(owner.favorite_standard_shortcuts_splitter_sash, 156)
        owner.save_splitter_positions.assert_called_once_with()

    def test_restore_splitter_positions_restores_horizontal_sash_on_open(self):
        owner = main.FileExplorer.__new__(main.FileExplorer)
        owner.favorite_content_splitter = mock.MagicMock()
        owner.favorite_content_splitter.IsSplit.return_value = True
        owner.favorite_list = mock.MagicMock()
        owner.standard_shortcuts_panel = mock.MagicMock()
        owner.favorite_panel = mock.MagicMock()
        owner.favorite_panel.GetSizer.return_value = mock.MagicMock()
        owner.standard_shortcuts_visible = True
        owner.favorite_standard_shortcuts_splitter_sash = 120

        main.FileExplorer.restore_splitter_positions(owner, {"favorite_standard_shortcuts_splitter_sash": 178})

        owner.favorite_content_splitter.SetSashPosition.assert_called_with(178)

    def test_standard_shortcuts_default_visible_items_are_loaded(self):
        owner = main.FileExplorer.__new__(main.FileExplorer)
        owner.standard_shortcuts_visibility = {
            "desktop": True,
            "documents": True,
            "downloads": False,
            "images": False,
            "music": False,
            "video": False,
            "recycle_bin": True,
        }
        owner.standard_shortcuts_list = mock.MagicMock()
        owner.standard_shortcuts_image_list = mock.MagicMock()
        owner.standard_shortcuts_panel = mock.MagicMock()

        favorite_panel.refresh_standard_shortcuts_list(owner)

        owner.standard_shortcuts_list.DeleteAllItems.assert_called_once_with()
        self.assertTrue(any(call.args[1] == "Desktop" for call in owner.standard_shortcuts_list.InsertItem.call_args_list))
        self.assertTrue(any(call.args[1] == "Documents" for call in owner.standard_shortcuts_list.InsertItem.call_args_list))
        self.assertTrue(any(call.args[1] == "Recycle Bin" for call in owner.standard_shortcuts_list.InsertItem.call_args_list))
        self.assertFalse(any(call.args[1] == "Downloads" for call in owner.standard_shortcuts_list.InsertItem.call_args_list))

    def test_recycle_bin_standard_shortcut_uses_virtual_shell_path(self):
        self.assertEqual(favorite_panel._standard_shortcut_path_for_key("recycle_bin"), "shell:RecycleBinFolder")

    def test_standard_shortcut_activation_opens_recycle_bin_virtual_folder(self):
        owner = main.FileExplorer.__new__(main.FileExplorer)
        owner.standard_shortcuts_list = mock.MagicMock()
        owner.standard_shortcuts_list.GetFirstSelected.return_value = 0
        owner.open_recycle_bin = mock.MagicMock()

        with mock.patch.object(favorite_panel, "_visible_standard_shortcuts", return_value=[{"key": "recycle_bin", "path": "shell:RecycleBinFolder"}]):
            favorite_panel.on_standard_shortcut_list_activate(owner, mock.MagicMock())

        owner.open_recycle_bin.assert_called_once_with(add_history=True)

    def test_load_folder_handles_virtual_recycle_bin_path(self):
        owner = types.SimpleNamespace(
            list=mock.MagicMock(),
            search_box=types.SimpleNamespace(GetValue=lambda: ""),
            show_hidden=True,
            list_sort_column=None,
            list_sort_direction=0,
            update_list_sort_header_icons=mock.Mock(),
            update_list_toolbar_buttons=mock.Mock(),
        )
        owner.list.GetItemCount.return_value = 0
        owner.list.InsertItem.side_effect = [0]

        recycled_items = [{
            "name": "Deleted file.txt",
            "original_path": "C:/Temp/Deleted file.txt",
            "recycled_path": "shell:RecycleBinFolder",
            "deleted_from": "C:/Temp",
            "deleted_date": None,
            "size": 2048,
            "is_dir": False,
        }]

        with mock.patch("controls.navigation_utils.get_recycle_bin_items", return_value=recycled_items), \
             mock.patch("controls.navigation_utils.os.listdir", side_effect=AssertionError("shell folder should not use os.listdir")):
            main.navigation_utils.load_folder(owner, "shell:RecycleBinFolder")

        owner.list.InsertItem.assert_called_once_with(0, "Deleted file.txt", mock.ANY)

    def test_recycle_bin_context_menu_uses_recycle_bin_only_items(self):
        owner = main.FileExplorer.__new__(main.FileExplorer)
        owner.path_box = types.SimpleNamespace(GetValue=lambda: "shell:RecycleBinFolder")
        owner.list = mock.MagicMock()
        owner.list.HitTest.return_value = (0, mock.MagicMock())
        owner.list.GetItemState.return_value = 0
        owner.list.GetFirstSelected.return_value = 0
        owner.list.GetNextSelected.return_value = wx.NOT_FOUND
        owner.list.GetItemText.return_value = "Deleted file.txt"
        owner.list.GetItemData.return_value = "shell:RecycleBinFolder/Deleted file.txt"
        owner.list.PopupMenu = mock.Mock()
        owner.Bind = mock.Mock()
        owner.load_folder = mock.Mock()

        fake_menu = mock.MagicMock()
        fake_refresh = mock.MagicMock()
        fake_restore = mock.MagicMock()
        fake_delete = mock.MagicMock()
        fake_menu.Append.side_effect = [fake_refresh, fake_restore, fake_delete]

        with mock.patch.object(wx, "Menu", return_value=fake_menu):
            filelist.on_right_click(owner, mock.MagicMock())

        self.assertEqual(fake_menu.Append.call_count, 3)
        fake_refresh.Enable.assert_called_once_with(True)
        fake_restore.Enable.assert_called_once_with(True)
        fake_delete.Enable.assert_called_once_with(True)

    def test_load_folder_uses_standard_folder_and_file_icons_for_recycle_bin_items(self):
        owner = types.SimpleNamespace(
            list=mock.MagicMock(),
            search_box=types.SimpleNamespace(GetValue=lambda: ""),
            show_hidden=True,
            list_sort_column=None,
            list_sort_direction=0,
            update_list_sort_header_icons=mock.Mock(),
            update_list_toolbar_buttons=mock.Mock(),
        )
        owner.list.GetItemCount.return_value = 0
        owner.list.InsertItem.side_effect = [0]

        recycled_items = [{
            "name": "Deleted file.txt",
            "original_path": "C:/Temp/Deleted file.txt",
            "recycled_path": "shell:RecycleBinFolder",
            "deleted_from": "C:/Temp",
            "deleted_date": None,
            "size": 2048,
            "is_dir": False,
        }]

        with mock.patch("controls.navigation_utils.get_recycle_bin_items", return_value=recycled_items), \
             mock.patch("controls.navigation_utils.image_utils.get_list_icon_index", return_value=17) as mock_get_icon:
            main.navigation_utils.load_folder(owner, "shell:RecycleBinFolder")

        mock_get_icon.assert_called_once_with(owner, "C:/Temp/Deleted file.txt", False, False)
        owner.list.InsertItem.assert_called_once_with(0, "Deleted file.txt", 17)

    def test_standard_shortcuts_rows_use_shell_icons_instead_of_folder_icon(self):
        owner = main.FileExplorer.__new__(main.FileExplorer)
        owner.standard_shortcuts_visibility = {
            "desktop": True,
            "documents": True,
            "downloads": False,
            "images": False,
            "music": False,
            "video": False,
            "recycle_bin": True,
        }
        owner.standard_shortcuts_list = mock.MagicMock()
        owner.favorite_image_list = mock.MagicMock()
        owner.favorite_image_list.Add.side_effect = [10, 11]
        owner.standard_shortcuts_image_list = owner.favorite_image_list
        owner.favorite_folder_icon_index = 99

        fake_bitmap = mock.MagicMock()
        fake_bitmap.IsOk.return_value = True
        with mock.patch.object(image_utils, "get_shell_bitmap", return_value=fake_bitmap) as mocked_get_shell_bitmap:
            favorite_panel.refresh_standard_shortcuts_list(owner)

        self.assertGreaterEqual(mocked_get_shell_bitmap.call_count, 2)
        self.assertTrue(any(call.args[1] != 99 for call in owner.standard_shortcuts_list.SetItemImage.call_args_list))

    def test_standard_shortcut_context_menu_toggle_keeps_visibility_state(self):
        owner = main.FileExplorer.__new__(main.FileExplorer)
        owner.standard_shortcuts_visibility = {
            "desktop": True,
            "documents": True,
            "downloads": False,
            "images": False,
            "music": False,
            "video": False,
            "recycle_bin": True,
        }
        owner.standard_shortcuts_list = mock.MagicMock()
        owner.standard_shortcuts_list.GetFirstSelected.return_value = 1
        owner.standard_shortcuts_panel = mock.MagicMock()
        owner.Bind = mock.Mock()
        owner.refresh_standard_shortcuts_list = mock.Mock()
        owner.save_splitter_positions = mock.Mock()
        fake_menu = mock.MagicMock()
        fake_item = mock.MagicMock()
        fake_menu.AppendCheckItem.return_value = fake_item

        with mock.patch.object(wx, "Menu", return_value=fake_menu):
            favorite_panel.on_standard_shortcut_right_click(owner, mock.MagicMock())

        self.assertTrue(fake_menu.AppendCheckItem.called)
        self.assertIn("Documents", "".join(str(call.args[1]) for call in fake_menu.AppendCheckItem.call_args_list))
        self.assertIn("Desktop", "".join(str(call.args[1]) for call in fake_menu.AppendCheckItem.call_args_list))

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

    def test_f5_refresh_reloads_active_folder_in_list_pane(self):
        owner = types.SimpleNamespace(
            tree=mock.MagicMock(),
            path_box=types.SimpleNamespace(GetValue=lambda: "D:/Projects"),
            load_folder=mock.MagicMock(),
            show_file_preview=mock.MagicMock(),
            current_preview_path="D:/Projects/old.txt",
        )
        item = mock.MagicMock()
        item.IsOk.return_value = True
        owner.tree.GetSelection.return_value = item
        owner.tree.GetItemData.return_value = "D:/Projects"

        event = types.SimpleNamespace(
            GetKeyCode=lambda: wx.WXK_F5,
            ControlDown=lambda: False,
            ShiftDown=lambda: False,
            Skip=lambda: None,
        )

        with mock.patch.object(main.tree_utils, "refresh_tree_selection_and_filelist") as mocked_refresh_list:
            main.FileExplorer.on_key(owner, event)

        owner.load_folder.assert_called_once_with("D:/Projects")
        mocked_refresh_list.assert_called_once_with(owner)

    def test_refresh_tree_subtree_only_recurses_expanded_children(self):
        owner = types.SimpleNamespace(tree=mock.MagicMock())
        root = mock.MagicMock()
        root.IsOk.return_value = True
        expanded_child = mock.MagicMock()
        expanded_child.IsOk.return_value = True
        collapsed_child = mock.MagicMock()
        collapsed_child.IsOk.return_value = True
        end_item = mock.MagicMock()
        end_item.IsOk.return_value = False

        owner.tree.GetFirstChild.side_effect = [
            (expanded_child, 0),
            (end_item, None),
        ]
        owner.tree.GetNextChild.side_effect = [
            (collapsed_child, 1),
            (end_item, None),
        ]
        owner.tree.GetItemData.side_effect = [
            "D:/Projects/Expanded",
            "D:/Projects/Collapsed",
        ]
        owner.tree.IsExpanded.side_effect = lambda item: item is expanded_child

        with mock.patch.object(main.tree_utils, "populate_tree_node") as mocked_populate, \
             mock.patch.object(main.tree_utils.os.path, "isdir", return_value=True):
            main.tree_utils.refresh_tree_subtree(owner, root, "D:/Projects")

        self.assertEqual(mocked_populate.call_count, 2)
        self.assertEqual(mocked_populate.call_args_list[0].args[2], os.path.normpath("D:/Projects"))
        self.assertEqual(mocked_populate.call_args_list[1].args[2], os.path.normpath("D:/Projects/Expanded"))

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

    def test_drop_targets_share_common_base_class(self):
        import controls.drag_and_drop as drag_and_drop_module

        self.assertTrue(issubclass(drag_and_drop_module.FileListDropTarget, drag_and_drop_module.BaseFileSystemDropTarget))
        self.assertTrue(issubclass(drag_and_drop_module.TreeDropTarget, drag_and_drop_module.BaseFileSystemDropTarget))

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

    def test_internal_drag_payload_is_persisted_in_text_data(self):
        import controls.drag_and_drop as drag_and_drop_module

        owner = types.SimpleNamespace()
        target = drag_and_drop_module.FileListDropTarget(owner)
        target.text_data.SetText("pdfexplorer_internal_move\nC:/Temp/alpha.txt\nC:/Temp/beta.txt")
        target.file_data.AddFile("C:/Temp/alpha.txt")
        target.file_data.AddFile("C:/Temp/beta.txt")

        marker, filenames = target._read_drag_payload()

        self.assertEqual(marker, "pdfexplorer_internal_move")
        self.assertEqual(filenames, ["C:/Temp/alpha.txt", "C:/Temp/beta.txt"])

    def test_set_clipboard_calls_bound_toolbar_callback_without_double_owner(self):
        import file_operations.copy_and_paste as copy_and_paste

        owner = types.SimpleNamespace()
        owner.file_clipboard_paths = []
        owner.file_clipboard_mode = None
        calls = []

        class FakeOwner:
            def update_list_toolbar_buttons(self):
                calls.append("called")

        fake_owner = FakeOwner()
        fake_owner.file_clipboard_paths = []
        fake_owner.file_clipboard_mode = None

        copy_and_paste._set_clipboard(
            fake_owner,
            ["C:/Temp/example.txt"],
            copy_and_paste.CLIPBOARD_MODE_COPY,
            fake_owner.update_list_toolbar_buttons,
        )

        self.assertEqual(calls, ["called"])
        self.assertEqual(fake_owner.file_clipboard_paths, [os.path.normpath("C:/Temp/example.txt")])
        self.assertEqual(fake_owner.file_clipboard_mode, copy_and_paste.CLIPBOARD_MODE_COPY)

    def test_drop_target_reports_drag_result_without_side_effects(self):
        import controls.drag_and_drop as drag_and_drop_module

        owner = types.SimpleNamespace(
            path_box=types.SimpleNamespace(GetValue=lambda: "D:/Temp"),
            list=mock.MagicMock(),
        )

        target = drag_and_drop_module.FileListDropTarget(owner)
        target.GetData = mock.Mock(return_value=True)
        target._read_drag_payload = mock.Mock(return_value=(drag_and_drop_module.INTERNAL_DRAG_MARKER, ["D:/Temp/source.txt"]))
        target._resolve_drop_target_dir = mock.Mock(return_value="D:/Temp/target_folder")

        result = target.OnData(0, 0, wx.DragCopy)

        self.assertEqual(result, wx.DragCopy)
        target._read_drag_payload.assert_called_once_with()
        target._resolve_drop_target_dir.assert_called_once_with(0, 0)

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

    def test_history_navigation_selects_tree_folder_for_back_and_forward(self):
        nav = __import__("controls.navigation_utils", fromlist=["go_back", "go_forward", "open_path"])

        owner = types.SimpleNamespace(
            history=[r"C:\\A", r"C:\\B", r"C:\\C"],
            history_index=2,
            path_box=types.SimpleNamespace(GetValue=lambda: r"C:\\C", ChangeValue=mock.MagicMock()),
            load_folder=mock.MagicMock(),
            confirm_preview_change=mock.MagicMock(return_value=True),
            select_tree_item_by_path=mock.MagicMock(),
        )

        nav.go_back(owner, None)
        owner.select_tree_item_by_path.assert_called_once_with(r"C:\\B")
        owner.load_folder.assert_called_once_with(r"C:\\B")

        owner.history_index = 0
        owner.load_folder.reset_mock()
        owner.select_tree_item_by_path.reset_mock()

        nav.go_forward(owner, None)
        owner.select_tree_item_by_path.assert_called_once_with(r"C:\\B")
        owner.load_folder.assert_called_once_with(r"C:\\B")

    def test_open_path_syncs_tree_selection_when_directory_changes(self):
        nav = __import__("controls.navigation_utils", fromlist=["open_path"])

        owner = types.SimpleNamespace(
            history=[],
            history_index=-1,
            path_box=types.SimpleNamespace(ChangeValue=mock.MagicMock()),
            load_folder=mock.MagicMock(),
            confirm_preview_change=mock.MagicMock(return_value=True),
            select_tree_item_by_path=mock.MagicMock(),
        )

        result = nav.open_path(owner, r"C:\\Folder", add_history=True)

        self.assertTrue(result)
        owner.select_tree_item_by_path.assert_called_once_with(r"C:\\Folder")
        owner.load_folder.assert_called_once_with(r"C:\\Folder")

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
            fake_word_doc.PrintOut.assert_called_once()
            print_kwargs = fake_word_doc.PrintOut.call_args.kwargs
            self.assertEqual(print_kwargs["Copies"], 1)
            self.assertEqual(print_kwargs["Pages"], "1,3")
            self.assertEqual(print_kwargs["Range"], 4)
            self.assertEqual(print_kwargs["Background"], False)
            mocked_startfile.assert_not_called()


if __name__ == "__main__":
    unittest.main()
