"""Exercise tab dragging with native wx controls without showing a window."""
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wx
from controls.explorer_tabs import ExplorerTabs


class Workspace:
    def __init__(self, name):
        self._list_folder_path = 'C:\\' + name


class Host:
    def __init__(self):
        self.workspaces = [Workspace(name) for name in ('A', 'B', 'C', 'D')]
        self.active_workspace = self.workspaces[0]
        self.moves = []

    def activate_tab(self, workspace):
        self.active_workspace = workspace
        self.tabs.mark_active(workspace)

    def move_tab(self, workspace, index):
        self.moves.append((workspace, index))
        self.workspaces.remove(workspace)
        self.workspaces.insert(index, workspace)
        self.tabs.reorder()


class ExplorerTabDragTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.App.Get() or wx.App(False)

    def setUp(self):
        self.frame = wx.Frame(None, size=(1000, 300))
        self.host = Host()
        self.tabs = ExplorerTabs(self.frame, self.host)
        self.host.tabs = self.tabs
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.tabs, 0, wx.EXPAND)
        self.frame.SetSizer(sizer)
        self.frame.Layout()
        self.tabs.rebuild()

    def tearDown(self):
        self.tabs._cancel_drag()
        self.frame.Destroy()
        self.app.ProcessPendingEvents()

    def mouse_event(self, kind, position, source=None):
        event = wx.MouseEvent(kind)
        event.SetEventObject(source or self.tabs)
        event.SetPosition(wx.Point(*position))
        event.SetLeftDown(kind != wx.wxEVT_LEFT_UP)
        return event

    def press(self, workspace, label=True):
        heading = self.tabs.headings[workspace]
        source = heading.label if label else heading
        heading._select(self.mouse_event(wx.wxEVT_LEFT_DOWN, (10, 10), source))

    def drag_to(self, position):
        self.tabs._on_drag_motion(self.mouse_event(wx.wxEVT_MOTION, position))

    def release(self, position):
        self.tabs._on_drag_end(self.mouse_event(wx.wxEVT_LEFT_UP, position))

    def test_drag_first_tab_to_end_preserves_headings(self):
        first, *others = self.host.workspaces
        headings = dict(self.tabs.headings)
        self.press(first)
        end = (self.tabs.add_button.GetPosition().x + 5, 10)
        self.drag_to(end)
        self.assertTrue(self.tabs._drop_marker.IsShown())
        self.assertEqual(self.host.workspaces, [first] + others)
        self.release(end)
        self.assertEqual(self.host.workspaces, others + [first])
        self.assertIs(self.host.active_workspace, first)
        self.assertEqual(self.tabs.headings, headings)
        self.assertEqual([item.GetWindow() for item in self.tabs.row.GetChildren()],
                         [headings[page] for page in self.host.workspaces] + [self.tabs.add_button])
        self.assertFalse(self.tabs.HasCapture())
        self.assertFalse(self.tabs._drop_marker.IsShown())

    def test_drag_last_tab_to_first_from_heading_background(self):
        *others, last = self.host.workspaces
        self.press(last, label=False)
        self.drag_to((1, 10))
        self.release((1, 10))
        self.assertEqual(self.host.workspaces, [last] + others)
        self.assertIs(self.host.active_workspace, last)

    def test_small_mouse_movement_is_only_a_click(self):
        second = self.host.workspaces[1]
        self.press(second)
        position = self.tabs.ScreenToClient(self.tabs._drag_start)
        self.drag_to((position.x + 1, position.y))
        self.release((position.x + 1, position.y))
        self.assertIs(self.host.active_workspace, second)
        self.assertEqual(self.host.moves, [])
        self.assertFalse(self.tabs.HasCapture())

    def test_drop_outside_tab_bar_cancels(self):
        before = list(self.host.workspaces)
        self.press(before[0])
        self.drag_to((400, 10))
        self.release((400, 100))
        self.assertEqual(self.host.workspaces, before)
        self.assertFalse(self.tabs._drop_marker.IsShown())
        self.assertFalse(self.tabs.HasCapture())

    def test_escape_cancels_drag(self):
        self.press(self.host.workspaces[0])
        self.drag_to((400, 10))
        with mock.patch.object(wx, 'GetKeyState', return_value=True):
            self.tabs._on_drag_timer(None)
        self.release((400, 10))
        self.assertEqual(self.host.moves, [])
        self.assertFalse(self.tabs._drag_timer.IsRunning())

    def test_rebuild_during_drag_releases_capture(self):
        self.press(self.host.workspaces[0])
        self.drag_to((400, 10))
        self.tabs.rebuild()
        self.assertFalse(self.tabs.HasCapture())
        self.assertFalse(self.tabs._drag_timer.IsRunning())
        self.assertEqual(self.host.moves, [])

    def test_edge_scroll_reaches_offscreen_tabs(self):
        first = self.host.workspaces[0]
        self.frame.SetSize((400, 300))
        self.frame.Layout()
        self.press(first)
        position = (self.tabs.GetClientSize().width - 2, 10)
        self.drag_to(position)
        with mock.patch.object(wx, 'GetKeyState', return_value=False), \
                mock.patch.object(wx, 'GetMousePosition',
                                  return_value=self.tabs.ClientToScreen(wx.Point(*position))):
            for _ in range(40):
                self.tabs._on_drag_timer(None)
        self.assertGreater(self.tabs.GetViewStart()[0], 0)
        self.release(position)
        self.assertIs(self.host.workspaces[-1], first)


if __name__ == '__main__':
    unittest.main()
