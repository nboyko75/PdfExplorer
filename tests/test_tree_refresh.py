"""Expanded branch refresh without native GUI dependencies."""
import ast
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


class Node:
    def __init__(self, path=None, expanded=False):
        self.path, self.expanded = path, expanded
        self.children = []
        self.valid = True

    def IsOk(self):
        return self.valid


class Tree:
    def __init__(self):
        self.root = Node()
        self.missing = Node()
        self.missing.valid = False

    def GetRootItem(self): return self.root
    def GetItemData(self, item): return item.path
    def IsExpanded(self, item): return item.expanded
    def ItemHasChildren(self, item): return bool(item.children)
    def SetItemData(self, item, path): item.path = path
    def SetItemImage(self, item, image): pass
    def GetFirstChild(self, item): return self.GetNextChild(item, 0)
    def GetNextChild(self, item, cookie):
        return (item.children[cookie] if cookie < len(item.children) else self.missing, cookie + 1)

    def InsertItem(self, parent, previous, name):
        child = Node()
        child.parent = parent
        parent.children.insert(parent.children.index(previous) + 1 if previous else 0, child)
        return child

    def PrependItem(self, parent, name): return self.InsertItem(parent, None, name)
    def AppendItem(self, parent, name):
        return self.InsertItem(parent, parent.children[-1] if parent.children else None, name)

    def Delete(self, item):
        item.parent.children.remove(item)
        item.valid = False

    def DeleteChildren(self, item):
        for child in list(item.children): self.Delete(child)


class TreeRefreshTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        source = ast.parse((root / 'controls/tree_control.py').read_text(encoding='utf-8'))
        names = {'_tree_children', 'refresh_tree_node', 'refresh_expanded_tree_nodes'}
        self.scope = {'os': os, 'normalize_tree_path': os.path.normpath,
                      'is_hidden': lambda path: Path(path).name == 'hidden.txt',
                      'get_tree_icon_index': lambda *a, **k: 0, 'tr': lambda key: key}
        exec(compile(ast.Module(body=[n for n in source.body if isinstance(n, ast.FunctionDef)
                                      and n.name in names], type_ignores=[]),
                     'tree_refresh', 'exec'), self.scope)

    def test_folder_reload_syncs_external_changes_without_replacing_tree_items(self):
        root = Path(__file__).resolve().parents[1]
        source = ast.parse((root / 'controls/filelist.py').read_text(encoding='utf-8'))
        scope = {'os': os, 'tree_control': SimpleNamespace(**self.scope)}
        names = {'_refresh_tree_node', '_find_tree_item_without_expanding'}
        exec(compile(ast.Module(body=[n for n in source.body if isinstance(n, ast.FunctionDef)
                                      and n.name in names], type_ignores=[]),
                     'filelist', 'exec'), scope)

        def load_list(owner, path):
            owner.list_paths = {str(p) for p in Path(path).iterdir()
                                if owner.show_hidden or p.name != 'hidden.txt'}

        source = ast.parse((root / 'main.py').read_text(encoding='utf-8'))
        workspace = next(n for n in source.body if isinstance(n, ast.ClassDef)
                         and n.name == 'ExplorerWorkspace')
        function = next(n for n in workspace.body if isinstance(n, ast.FunctionDef)
                        and n.name == 'load_folder')
        scope.update(filelist=SimpleNamespace(**scope),
                     navigation_utils=SimpleNamespace(load_folder=load_list))
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'main', 'exec'), scope)

        for expanded in (True, False):
            with self.subTest(expanded=expanded), tempfile.TemporaryDirectory() as folder:
                base = Path(folder)
                (base / 'nested').mkdir()
                (base / 'nested' / 'keep.txt').write_text('keep')
                (base / 'removed.txt').write_text('remove')
                tree = Tree()
                item = tree.AppendItem(tree.root, 'current')
                item.path, item.expanded = folder, expanded
                owner = SimpleNamespace(tree=tree, show_hidden=False, updating_tree=False,
                                        host=SimpleNamespace(explorer_tabs=SimpleNamespace(
                                            location_changed=mock.Mock())))
                scope['load_folder'](owner, folder)
                nested = next(child for child in item.children if child.path == str(base / 'nested'))
                nested.expanded = True
                self.scope['refresh_tree_node'](owner, nested)
                selected = nested.children[0]
                removed = next(child for child in item.children if child.path == str(base / 'removed.txt'))

                # Simulate another application's writes, then the normal list reload.
                (base / 'external.txt').write_text('new')
                (base / 'new_folder').mkdir()
                (base / 'hidden.txt').write_text('hidden')
                (base / 'removed.txt').unlink()
                scope['load_folder'](owner, folder)

                self.assertEqual({child.path for child in item.children}, owner.list_paths)
                self.assertIn(str(base / 'external.txt'), owner.list_paths)
                self.assertNotIn(str(base / 'hidden.txt'), owner.list_paths)
                self.assertIn(nested, item.children)
                self.assertEqual(nested.children, [selected])
                self.assertTrue(selected.valid)
                self.assertTrue(nested.expanded)
                self.assertEqual(item.expanded, expanded)
                self.assertFalse(removed.valid)
                self.assertFalse(owner.updating_tree)

                owner.show_hidden = True
                owner.updating_tree = True
                scope['load_folder'](owner, folder)
                self.assertIn(str(base / 'hidden.txt'), {child.path for child in item.children})
                self.assertTrue(owner.updating_tree)

    def test_f5_refreshes_the_focused_pane(self):
        source = ast.parse((Path(__file__).resolve().parents[1] / 'main.py').read_text(encoding='utf-8'))
        function = next(n for n in ast.walk(source) if isinstance(n, ast.FunctionDef)
                        and n.name == 'on_key')
        tree_control = SimpleNamespace(refresh_tree_selection_and_filelist=mock.Mock())
        wx = SimpleNamespace(WXK_F1=1, WXK_F5=5, WXK_DELETE=127,
                             Window=SimpleNamespace(FindFocus=mock.Mock()))
        scope = {'wx': wx, 'tree_control': tree_control}
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'main.py', 'exec'), scope)
        owner = SimpleNamespace(tree=object(), on_refresh_menu=mock.Mock())
        event = SimpleNamespace(GetKeyCode=lambda: wx.WXK_F5,
                                ControlDown=lambda: False, ShiftDown=lambda: False,
                                Skip=mock.Mock())
        for focus in (owner.tree, object()):
            with self.subTest(tree_focused=focus is owner.tree):
                wx.Window.FindFocus.return_value = focus
                tree_control.refresh_tree_selection_and_filelist.reset_mock()
                owner.on_refresh_menu.reset_mock()
                scope['on_key'](owner, event)
                if focus is owner.tree:
                    tree_control.refresh_tree_selection_and_filelist.assert_called_once_with(owner)
                    owner.on_refresh_menu.assert_not_called()
                else:
                    tree_control.refresh_tree_selection_and_filelist.assert_not_called()
                    owner.on_refresh_menu.assert_called_once_with(event)
                event.Skip.assert_not_called()

    def test_refreshes_sibling_and_nested_branches_preserving_nodes(self):
        scope = self.scope
        tree = Tree()
        owner = SimpleNamespace(tree=tree, show_hidden=False, updating_tree=False)
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            def branch(parent, path, expanded=True):
                path.mkdir(exist_ok=True)
                item = tree.AppendItem(parent, path.name)
                item.path, item.expanded = str(path), expanded
                return item
            left = branch(tree.root, base / 'left')
            nested = branch(left, base / 'left' / 'nested')
            right = branch(tree.root, base / 'right')
            collapsed = branch(tree.root, base / 'collapsed', False)
            unavailable = tree.PrependItem(tree.root, 'unavailable')
            unavailable.path, unavailable.expanded = str(base / 'missing'), True
            removed = tree.AppendItem(left, 'removed.txt')
            removed.path = str(base / 'left' / 'removed.txt')
            for path in (base / 'left', base / 'left' / 'nested', base / 'right', base / 'collapsed'):
                (path / 'new.txt').write_text('new')
            scope['refresh_expanded_tree_nodes'](owner)
            self.assertIn(nested, left.children)
            self.assertTrue(nested.expanded)
            self.assertFalse(removed.valid)
            for item in (left, nested, right):
                self.assertIn(str(Path(item.path) / 'new.txt'), [child.path for child in item.children])
            self.assertEqual(collapsed.children, [])
            self.assertFalse(owner.updating_tree)


if __name__ == '__main__':
    unittest.main()
