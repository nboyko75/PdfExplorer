"""Headless regression checks: python tests/test_explorer_workspaces.py -v.

Exercise the actual frame controller methods without requiring Windows/wx.
Native rendering still needs a Windows smoke test.
"""
import ast
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from common.workspace_context import (
    pdf_sessions, scoped_callback, set_active_workspace, workspace_scope,
)


class Event:
    def __init__(self, obj=None):
        self.obj = obj
        self.vetoed = False
        self.skipped = False

    def GetEventObject(self):
        return self.obj

    def SetEventObject(self, obj):
        self.obj = obj

    def Skip(self):
        self.skipped = True

    def Veto(self):
        self.vetoed = True


class Control:
    def __init__(self, parent=None):
        self.parent = parent
        self.focused = False

    def GetParent(self):
        return self.parent

    def IsShownOnScreen(self):
        return True

    def SetFocus(self):
        self.focused = True


class Frame:
    def __init__(self):
        self.menus = []
        self.close_requested = False

    def SetMenuBar(self, menu):
        self.menu = menu
        self.menus.append(menu)

    def Layout(self):
        pass

    def Close(self):
        self.close_requested = True


# Compile the real host class, bypassing platform-specific application imports.
source = ast.parse((ROOT / 'main.py').read_text(encoding='utf-8'))
frame_class = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'FileExplorer')
scheduled = []
env = {
    'wx': SimpleNamespace(Frame=Frame, Window=SimpleNamespace(FindFocus=lambda: None),
                          CallAfter=lambda callback: scheduled.append(callback)),
    'workspace_scope': workspace_scope,
    'set_active_workspace': set_active_workspace,
    'save_window_geometry': lambda host: None,
    'update_settings': lambda settings: None,
    'TAB_LAYOUT_KEYS': ('main_splitter_sash', 'preview_splitter_sash', 'favorite_splitter_sash',
                        'favorite_standard_shortcuts_splitter_sash', 'favorite_panel_above_tree',
                        'standard_shortcuts_visible'),
}
exec(compile(ast.Module(body=[frame_class], type_ignores=[]), 'main.py', 'exec'), env)
Host = env['FileExplorer']

# Execute the real PDF session accessors as well.
pdf_source = ast.parse((ROOT / 'file_operations/pdf_utils.py').read_text(encoding='utf-8'))
accessor_names = {'_normalize_pdf_session_path', '_get_pdf_session_bytes', '_set_pdf_session_bytes',
                  'has_unsaved_pdf_changes', 'get_unsaved_pdf_paths', 'discard_pdf_changes'}
pdf_env = {'os': os, 'pdf_sessions': pdf_sessions}
exec(compile(ast.Module(body=[n for n in pdf_source.body if isinstance(n, ast.FunctionDef)
                             and n.name in accessor_names], type_ignores=[]), 'pdf_utils.py', 'exec'), pdf_env)


class Workspace:
    def __init__(self, label):
        self._pdf_session_bytes = {}
        self._restoring_layout = False
        self._closing_workspace = False
        self.refresh_count = 0
        self.label = label
        self.folder = label + '/folder'
        self.selected_file = label + '/file.pdf'
        self.preview_tabs = [{'path': self.selected_file, 'pinned': True}]
        self.history = [self.folder]
        self.zoom = 1.75
        self.scroll = (0, 42)
        self.menu_bar = object()
        self.list = Control(self)
        self.visible = False
        self.disposed = False
        self.allow_close = True
        self.confirm_count = 0
        self.menu_updates = 0
        self.received_events = []

    def Hide(self):
        self.visible = False

    def Show(self):
        self.visible = True

    def Layout(self):
        pass

    def refresh_current_folder_preserving_context(self):
        self.refresh_count += 1

    def on_clipboard_activate(self, event):
        event.Skip()

    def apply_initial_layout(self):
        pass

    def _update_main_menu_state(self):
        self.menu_updates += 1

    def update_list_toolbar_buttons(self):
        pass

    def confirm_close(self):
        self.confirm_count += 1
        return self.allow_close

    def dispose(self):
        self.disposed = True

    def GetEventHandler(self):
        return self

    def ProcessEvent(self, event):
        self.received_events.append(event.GetEventObject())
        pdf_sessions()['menu-action.pdf'] = self.label.encode()

    def save_splitter_positions(self):
        pass

    save_list_view_state = save_splitter_positions
    save_last_folder = save_splitter_positions


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Workspace('A'), Workspace('B')
        self.host = Host.__new__(Host)
        Frame.__init__(self.host)
        h = self.host
        h.workspaces = [self.a, self.b]
        h.active_workspace = None
        h._closing = False
        h._routing_menu = False
        h._switching_tabs = False
        h._geometry_save_timer = None
        h.last_tab_layout = {}
        h.body = SimpleNamespace(Layout=lambda: None)
        h.explorer_tabs = SimpleNamespace(mark_active=lambda w: None, rebuild=lambda: None)
        h.workspace_sizer = SimpleNamespace(Detach=lambda w: None)
        h.activate_tab(self.a)
        scheduled.clear()
        h._folder_refresh_pending = False

    def tearDown(self):
        set_active_workspace(None)

    def test_switch_preserves_complete_workspace_and_native_menu(self):
        preview_list = self.a.preview_tabs
        self.host.activate_tab(self.b)
        self.assertFalse(self.a.visible)
        self.assertTrue(self.b.visible)
        self.assertIs(self.host.menu, self.b.menu_bar)
        self.b.history.append('another-folder')
        self.b.preview_tabs.clear()
        self.host.activate_tab(self.a)
        self.assertIs(self.a.preview_tabs, preview_list)
        self.assertEqual(self.a.preview_tabs, [{'path': 'A/file.pdf', 'pinned': True}])
        self.assertEqual(self.a.selected_file, 'A/file.pdf')
        self.assertEqual(self.a.history, ['A/folder'])
        self.assertEqual((self.a.zoom, self.a.scroll), (1.75, (0, 42)))
        self.assertIs(self.host.menu, self.a.menu_bar)
        self.assertGreater(self.a.menu_updates, 1)
        self.assertEqual(self.a.confirm_count, 0)  # Switching does not close documents.

    def test_menu_event_targets_only_active_workspace(self):
        self.host.activate_tab(self.b)
        event = Event(self.host)
        self.host._route_menu_event(event)
        self.assertEqual(self.a.received_events, [])
        self.assertEqual(self.b.received_events, [self.b])
        self.assertEqual(self.b._pdf_session_bytes['menu-action.pdf'], b'B')
        self.assertEqual(self.a._pdf_session_bytes, {})
        self.assertIs(event.GetEventObject(), self.host)
        self.assertFalse(self.host._routing_menu)

    def test_unhandled_menu_propagation_cannot_recurse(self):
        self.a.ProcessEvent = self.host._route_menu_event
        event = Event(self.host)
        self.host._route_menu_event(event)
        self.assertTrue(event.skipped)
        self.assertFalse(self.host._routing_menu)

    def test_same_pdf_has_independent_unsaved_edits(self):
        path = 'same.pdf'
        with workspace_scope(self.a):
            pdf_env['_set_pdf_session_bytes'](path, b'A edits')
        with workspace_scope(self.b):
            self.assertFalse(pdf_env['has_unsaved_pdf_changes'](path))
            pdf_env['_set_pdf_session_bytes'](path, b'B edits')
            pdf_env['discard_pdf_changes'](path)
        with workspace_scope(self.a):
            self.assertEqual(pdf_env['_get_pdf_session_bytes'](path), b'A edits')
            self.assertEqual(pdf_env['get_unsaved_pdf_paths'](), [path])

    def test_inactive_deferred_owner_callback_uses_its_own_session(self):
        self.host.activate_tab(self.b)
        @scoped_callback
        def render(owner):
            pdf_sessions()['deferred.pdf'] = b'A'
        render(self.a)
        self.assertEqual(self.a._pdf_session_bytes['deferred.pdf'], b'A')
        self.assertNotIn('deferred.pdf', self.b._pdf_session_bytes)
        self.assertIs(pdf_sessions(), self.b._pdf_session_bytes)

    def test_nested_control_event_resolves_workspace(self):
        self.host.activate_tab(self.b)
        @scoped_callback
        def click(event):
            pdf_sessions()['from-child.pdf'] = b'A'
        click(Event(Control(Control(self.a))))
        self.assertIn('from-child.pdf', self.a._pdf_session_bytes)
        self.assertNotIn('from-child.pdf', self.b._pdf_session_bytes)

    def test_cancel_close_keeps_both_tabs(self):
        self.b.allow_close = False
        self.host.close_tab(self.b)
        self.assertEqual(self.host.workspaces, [self.a, self.b])
        self.assertFalse(self.b.disposed)
        self.assertIs(self.host.active_workspace, self.b)
        self.assertEqual(self.a.confirm_count, 0)

    def test_close_one_tab_leaves_other_preview_intact(self):
        self.host.close_tab(self.a)
        self.assertEqual(self.host.workspaces, [self.b])
        self.assertTrue(self.a.disposed)
        self.assertFalse(self.b.disposed)
        self.assertEqual(len(self.b.preview_tabs), 1)
        self.assertIs(self.host.menu, self.b.menu_bar)

    def test_last_tab_close_uses_normal_window_close(self):
        self.host.close_tab(self.b)
        self.host.close_tab(self.a)
        self.assertTrue(self.host.close_requested)
        self.assertFalse(self.a.disposed)

    def test_cancel_exit_destroys_no_workspaces(self):
        self.b.allow_close = False
        event = Event()
        self.host._on_close(event)
        self.assertTrue(event.vetoed)
        self.assertFalse(self.a.disposed or self.b.disposed)
        self.assertEqual(len(self.host.workspaces), 2)

    def test_exit_checks_and_disposes_all_tabs(self):
        event = Event()
        self.host._on_close(event)
        self.assertTrue(event.skipped)
        self.assertTrue(self.a.disposed and self.b.disposed)
        self.assertEqual(self.a.confirm_count, 1)
        self.assertEqual(self.b.confirm_count, 1)
        self.assertIsNone(self.host.menu)
        self.assertEqual(self.host.workspaces, [])

    def test_last_changed_layout_survives_switch_to_older_tab(self):
        older = dict.fromkeys(env['TAB_LAYOUT_KEYS'], 100)
        latest = dict.fromkeys(env['TAB_LAYOUT_KEYS'], 240)
        self.host.remember_tab_layout(self.a, older)
        self.host.activate_tab(self.b)
        self.host.remember_tab_layout(self.b, latest)
        self.host.activate_tab(self.a)
        self.host.remember_tab_layout(self.a, older)
        self.assertEqual(self.host.last_tab_layout, latest)
        self.host.remember_tab_layout(self.a, dict(older, main_splitter_sash=350))
        self.assertEqual(self.host.last_tab_layout['main_splitter_sash'], 350)

    def test_restoring_or_inactive_tab_cannot_replace_layout_defaults(self):
        self.host.last_tab_layout = {'main_splitter_sash': 320}
        self.host.remember_tab_layout(self.b, {'main_splitter_sash': 500})
        self.a._restoring_layout = True
        self.host.remember_tab_layout(self.a, {'main_splitter_sash': 600})
        self.a._restoring_layout = False
        self.host._switching_tabs = True
        self.host.remember_tab_layout(self.a, {'main_splitter_sash': 700})
        self.assertEqual(self.host.last_tab_layout, {'main_splitter_sash': 320})

    def test_latest_layout_survives_closing_its_source_tab(self):
        latest = dict.fromkeys(env['TAB_LAYOUT_KEYS'], 250)
        self.host.remember_tab_layout(self.a, latest)
        self.host.close_tab(self.a)
        self.assertEqual(self.host.last_tab_layout, latest)

    def test_tab_switch_refreshes_only_final_active_tab(self):
        self.host.activate_tab(self.b)
        self.host.activate_tab(self.a)
        self.assertEqual(len(scheduled), 1)
        scheduled.pop()()
        self.assertEqual(self.a.refresh_count, 1)
        self.assertEqual(self.b.refresh_count, 0)

    def test_window_activation_refreshes_but_deactivation_does_not(self):
        event = Event(self.host)
        event.GetActive = lambda: False
        self.host._on_activate(event)
        self.assertEqual(scheduled, [])
        event.GetActive = lambda: True
        self.host._on_activate(event)
        scheduled.pop()()
        self.assertEqual(self.a.refresh_count, 1)

    def test_cycle_in_both_directions(self):
        self.host.cycle_tab()
        self.assertIs(self.host.active_workspace, self.b)
        self.host.cycle_tab(backwards=True)
        self.assertIs(self.host.active_workspace, self.a)


class GeometryTests(unittest.TestCase):
    def setUp(self):
        source = ast.parse((ROOT / 'common/window_tools.py').read_text())
        functions = [n for n in source.body if isinstance(n, ast.FunctionDef)
                     and n.name in ('save_window_geometry', 'restore_window_geometry')]
        self.settings = {'window_position': [10, 20], 'window_size': [1400, 900]}
        self.env = {'update_settings': self.settings.update}
        exec(compile(ast.Module(body=functions, type_ignores=[]), 'window_tools.py', 'exec'), self.env)

    def test_maximize_preserves_normal_bounds(self):
        frame = SimpleNamespace(IsIconized=lambda: False, IsMaximized=lambda: True)
        self.env['save_window_geometry'](frame)
        self.assertEqual(self.settings['window_size'], [1400, 900])
        self.assertEqual(self.settings['window_position'], [10, 20])
        self.assertTrue(self.settings['window_maximized'])

    def test_normal_resize_and_move_are_saved(self):
        frame = SimpleNamespace(IsIconized=lambda: False, IsMaximized=lambda: False,
                                GetPosition=lambda: SimpleNamespace(x=30, y=40),
                                GetSize=lambda: SimpleNamespace(x=1600, y=1000))
        self.env['save_window_geometry'](frame)
        self.assertEqual(self.settings['window_position'], [30, 40])
        self.assertEqual(self.settings['window_size'], [1600, 1000])
        self.assertFalse(self.settings['window_maximized'])

    def test_restore_applies_normal_bounds_before_maximizing(self):
        calls = []
        frame = SimpleNamespace(SetSize=lambda value: calls.append(('size', value)),
                                SetPosition=lambda value: calls.append(('position', value)),
                                Maximize=lambda value: calls.append(('maximized', value)))
        self.settings['window_maximized'] = True
        self.env['restore_window_geometry'](frame, self.settings)
        self.assertEqual(calls, [('size', (1400, 900)), ('position', (10, 20)), ('maximized', True)])


if __name__ == '__main__':
    unittest.main()
