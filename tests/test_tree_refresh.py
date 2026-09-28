"""Expanded branch refresh without native GUI dependencies."""
import ast
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest


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
    def test_refreshes_sibling_and_nested_branches_preserving_nodes(self):
        source = ast.parse((Path(__file__).resolve().parents[1] / 'controls/tree_control.py').read_text())
        function = next(n for n in source.body if isinstance(n, ast.FunctionDef)
                        and n.name == 'refresh_expanded_tree_nodes')
        scope = {'os': os, 'normalize_tree_path': os.path.normpath,
                 'is_hidden': lambda path: False, 'get_tree_icon_index': lambda *a, **k: 0,
                 'tr': lambda key: key}
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'tree_refresh', 'exec'), scope)
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
