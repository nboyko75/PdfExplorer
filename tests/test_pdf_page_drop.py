"""Exercise production drop handlers without requiring a Windows wx installation."""
import ast
from contextlib import nullcontext
from pathlib import Path
import os
import sys
import types
import unittest
from unittest.mock import Mock, patch

SOURCE = Path(__file__).resolve().parents[1] / 'common' / 'drag_and_drop.py'


class PdfDropTests(unittest.TestCase):
    def setUp(self):
        self.order = list(range(5))
        self.preview = types.ModuleType('controls.file_preview')
        for name in ('show_pdf_feed', '_paint_pdf_page_selection', 'update_pdf_save_button_state'):
            setattr(self.preview, name, Mock())
        controls = types.ModuleType('controls')
        controls.file_preview = self.preview
        self.modules = patch.dict(sys.modules, {'controls': controls, 'controls.file_preview': self.preview})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.wx = types.SimpleNamespace(DropTarget=object, DragMove=2, DragNone=0,
                                        OK=1, ICON_ERROR=2, MessageBox=Mock(), CallAfter=Mock())
        self.owner = types.SimpleNamespace(current_pdf_path='test.pdf', busy_cursor=nullcontext,
                                           hide_drag_overlay=Mock(), hide_drop_frame=Mock())
        def move(path, indices, boundary):
            source = indices[0]
            value = self.order.pop(source)
            destination = boundary - (source < boundary)
            self.order.insert(destination, value)
            return [destination]
        tree = ast.parse(SOURCE.read_text())
        nodes = [n for n in tree.body if getattr(n, 'name', '') in ('handle_pdf_page_drop', 'PdfPageDropTarget')]
        self.ns = dict(wx=self.wx, os=os, tr=lambda key:key, is_pdf_file=lambda path:path.endswith('.pdf'),
                       get_pdf_page_count=lambda path:5, move_pdf_pages=move)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), self.ns)

    def drop(self, source, target, before):
        return self.ns['handle_pdf_page_drop'](self.owner, target, f'test.pdf\n{source}', before)

    def test_moves_in_both_directions_before_and_after(self):
        for source,target,before,expected in [
            (0,1,False,[1,0,2,3,4]), (0,4,False,[1,2,3,4,0]),
            (0,3,True,[1,2,0,3,4]), (4,1,False,[0,1,4,2,3]),
            (4,0,True,[4,0,1,2,3])]:
            with self.subTest(source=source,target=target,before=before):
                self.order=list(range(5))
                self.assertTrue(self.drop(source,target,before))
                self.assertEqual(self.order,expected)
                self.assertEqual(self.owner.selected_pdf_page_indices,{expected.index(source)})
                self.preview.show_pdf_feed.assert_called_with(self.owner,'test.pdf',force_all_pages=True)
                self.preview.update_pdf_save_button_state.assert_called_with(self.owner)

    def test_adjacent_and_self_drops_are_noops(self):
        for target,before in [(2,True),(2,False),(3,True),(1,False)]:
            self.assertFalse(self.drop(2,target,before))
        self.assertEqual(self.order,list(range(5)))
        self.preview.show_pdf_feed.assert_not_called()

    def test_other_document_is_rejected(self):
        self.assertFalse(self.ns['handle_pdf_page_drop'](self.owner,0,'other.pdf\n2'))
        self.assertEqual(self.order,list(range(5)))

    def test_move_error_is_reported(self):
        self.ns['move_pdf_pages']=Mock(side_effect=RuntimeError('Cannot move'))
        self.assertFalse(self.drop(0,4,False))
        self.wx.MessageBox.assert_called_once()
        self.preview.show_pdf_feed.assert_not_called()

    def test_leaving_target_keeps_panel_and_drop_is_deferred(self):
        target=object.__new__(self.ns['PdfPageDropTarget'])
        panel=types.SimpleNamespace(GetSize=lambda:types.SimpleNamespace(y=100))
        target.owner=self.owner
        target.page_panel=panel
        target.page_index=3
        target.insert_before=None
        target.GetData=lambda:True
        target.data=types.SimpleNamespace(GetText=lambda:'test.pdf\n0')
        target.OnLeave()
        self.assertIs(target.page_panel,panel)
        self.assertEqual(target.OnData(0,90,2),2)
        self.wx.CallAfter.assert_called_once_with(self.ns['handle_pdf_page_drop'],self.owner,3,'test.pdf\n0',insert_before=False)
        self.assertEqual(self.order,list(range(5)))
        target.GetData=lambda:False
        self.assertEqual(target.OnData(0,90,2),0)


if __name__ == '__main__':
    unittest.main()
