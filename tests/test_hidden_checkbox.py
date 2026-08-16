import os
import sys
import types
import unittest
from unittest import mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

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


if __name__ == "__main__":
    unittest.main()
