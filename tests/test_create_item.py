"""Creation, native menu dispatch, filename safety and localization regression tests."""

import importlib
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import xml.etree.ElementTree as ET
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import wx

from file_operations import create_item
from localization import available_locales, load_locale, tr


class CreateItemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = self.temp.name

    def test_create_folder_text_and_rtf(self):
        folder = create_item.create(self.folder, "folder", "Папка")
        self.assertTrue(os.path.isdir(folder))
        text = create_item.create(folder, "text", "日本語")
        self.assertEqual(Path(text).suffix, ".txt")
        self.assertEqual(Path(text).read_bytes(), b"")
        rich_text = create_item.create(folder, "rich_text", "formatted")
        self.assertTrue(Path(rich_text).read_bytes().startswith(b"{\\rtf1"))

    def test_office_packages_have_valid_xml_and_resolved_relationships(self):
        for kind, part, root in (("word", "word/document.xml", "document"),
                                 ("excel", "xl/workbook.xml", "workbook")):
            with self.subTest(kind=kind):
                path = create_item.create(self.folder, kind, "empty")
                with ZipFile(path) as archive:
                    self.assertIsNone(archive.testzip())
                    for entry in archive.namelist():
                        ET.fromstring(archive.read(entry))
                    self.assertTrue(ET.fromstring(archive.read(part)).tag.endswith("}" + root))
                    rel = ET.fromstring(archive.read("_rels/.rels"))[0]
                    self.assertEqual(rel.attrib["Target"], part)
                    if kind == "word":
                        self.assertIsNotNone(ET.fromstring(archive.read(part)).find(".//{*}p"))
                    else:
                        workbook = ET.fromstring(archive.read(part))
                        self.assertEqual(len(workbook.find("{*}sheets")), 1)
                        rel = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))[0]
                        self.assertIn("xl/" + rel.attrib["Target"], archive.namelist())

    def test_shortcut_round_trip_for_unicode_file_and_folder(self):
        import pythoncom
        from win32com.shell import shell

        target = Path(self.folder) / "дані 日本語.txt"
        target.write_text("keep", encoding="utf-8")
        pythoncom.CoInitialize()
        try:
            for index, destination in enumerate((str(target), self.folder)):
                path = create_item.create(self.folder, "shortcut", f"link{index}", destination)
                link = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None,
                                                 pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink)
                persist = link.QueryInterface(pythoncom.IID_IPersistFile)
                persist.Load(path)
                self.assertTrue(os.path.samefile(link.GetPath(0)[0], destination))
                del persist, link
        finally:
            pythoncom.CoUninitialize()

    def test_shortcut_missing_target_leaves_no_file(self):
        with self.assertRaises(ValueError):
            create_item.create(self.folder, "shortcut", "link", os.path.join(self.folder, "missing"))
        self.assertEqual(os.listdir(self.folder), [])

    def test_collision_never_overwrites_existing_content(self):
        for kind, _label, extension in create_item.ITEM_TYPES:
            with self.subTest(kind=kind):
                destination = Path(self.folder) / (kind + extension)
                destination.write_bytes(b"valuable original")
                with mock.patch.object(create_item, "_shortcut_bytes", return_value=b"link"), \
                     self.assertRaises(FileExistsError):
                    create_item.create(self.folder, kind, kind, self.folder)
                self.assertEqual(destination.read_bytes(), b"valuable original")

    def test_invalid_names_cannot_escape_destination(self):
        for name in ("", ".", "..", "../outside", "C:\\outside", "file:stream",
                     "CON", "nul.txt", "LPT1", "COM².txt", "trailing.", "trailing ",
                     "bad?name", "bad\x00name", "a" * 256):
            with self.subTest(name=name), self.assertRaises(ValueError):
                create_item.create(self.folder, "text", name)
        self.assertEqual(os.listdir(self.folder), [])

    def test_extensions_and_unique_suggestions(self):
        self.assertEqual(create_item.item_name("report.DOCX", "word"), "report.DOCX")
        self.assertEqual(create_item.item_name("report", "word"), "report.docx")
        first = create_item.default_name(self.folder, "word")
        create_item.create(self.folder, "word", first)
        second = create_item.default_name(self.folder, "word")
        self.assertNotEqual(first, second)
        self.assertTrue(second.endswith(" (2).docx"))

    def test_failed_write_removes_only_new_partial_file(self):
        destination = Path(self.folder) / "broken.txt"
        def fail_write(path, mode):
            destination.touch()
            stream = mock.MagicMock()
            stream.write.side_effect = OSError("disk full")
            return stream
        with mock.patch("builtins.open", side_effect=fail_write), self.assertRaises(OSError):
            create_item.create(self.folder, "text", "broken")
        self.assertFalse(destination.exists())

    def test_target_is_tree_context_or_current_folder(self):
        child = Path(self.folder) / "child"
        child.mkdir()
        context = SimpleNamespace(source="tree", new_folder_target=str(child), current_folder=self.folder)
        self.assertEqual(create_item.target_directory(context), str(child))
        context.source = "list"
        self.assertEqual(create_item.target_directory(context), self.folder)
        context.source = "main"
        context.current_folder = "shell:RecycleBinFolder"
        self.assertIsNone(create_item.target_directory(context))

    def test_cancel_either_shortcut_prompt_creates_nothing(self):
        context = SimpleNamespace(source="list", current_folder=self.folder, owner=None)
        for replies in ([None], [self.folder, None]):
            with mock.patch.object(create_item, "_prompt", side_effect=replies), \
                 mock.patch.object(create_item, "create") as create:
                create_item.run(context, "shortcut")
                create.assert_not_called()

    def test_success_refreshes_destination_and_selects_new_item(self):
        from controls import filelist
        owner = SimpleNamespace(path_box=mock.Mock())
        context = SimpleNamespace(source="list", current_folder=self.folder, owner=owner)
        with mock.patch.object(create_item, "_prompt", return_value="new"), \
             mock.patch.object(filelist, "_refresh_after_fs_change") as refresh, \
             mock.patch.object(filelist, "select_list_item_by_path") as select:
            create_item.run(context, "text")
        path = os.path.join(self.folder, "new.txt")
        self.assertTrue(os.path.isfile(path))
        refresh.assert_called_once_with(owner, affected_dirs=[self.folder], current_folder=self.folder)
        select.assert_called_once_with(owner, path)

    def test_all_languages_have_complete_translations(self):
        keys = ("context_create", "create_hint", "create_shortcut", "create_word", "create_excel",
                "create_text", "create_rich_text", "create_name", "create_shortcut_target",
                "create_target_missing", "create_failed")
        for locale in available_locales():
            translations = importlib.import_module("localization.localization_" + locale).TRANSLATIONS
            for key in keys:
                with self.subTest(locale=locale, key=key):
                    self.assertTrue(translations[key].strip())
                    self.assertNotIn("�", translations[key])
            self.assertIn("example", translations["create_failed"].format(error="example"))


class CreateMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.App.Get() or wx.App(False)

    def test_native_submenu_uses_live_context_and_updates_language(self):
        from common import menu_utils
        from file_operations.shell_new import NewItem
        entries = [NewItem(1, "System folder", "NewFolder"),
                   NewItem(2, "System shortcut", "NewLink"),
                   NewItem(3, "Installed document", ".custom", icon=(1, 1, bytes((255, 0, 0, 255))))]
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(create_item.shell_new, "items", return_value=entries):
            context = menu_utils.FileCommandContext(None, "main", folder, [])
            menu = wx.Menu()
            try:
                item = menu_utils.append_command(menu, None, menu_utils.FILE_COMMANDS["create"],
                                                 context_factory=lambda: context)
                self.assertTrue(item.IsEnabled())
                self.assertEqual(item.GetHelp(), tr("create_hint"))
                submenu = item.GetSubMenu()
                self.assertEqual(submenu.GetMenuItemCount(), len(entries))
                self.assertTrue(submenu.GetMenuItems()[2].GetBitmap().IsOk())
                context = menu_utils.FileCommandContext(None, "main", folder, ["changed"])
                with mock.patch.object(create_item, "run_shell") as run:
                    event = wx.CommandEvent(wx.EVT_MENU.typeId, submenu.GetMenuItems()[2].GetId())
                    submenu.ProcessEvent(event)
                    run.assert_called_once_with(context, entries[2])
                load_locale("uk")
                create_item.populate_menu(submenu, lambda: context)
                self.assertEqual(submenu.GetMenuItems()[1].GetItemLabel(), "System shortcut")
                self.assertEqual(submenu.GetMenuItemCount(), len(entries))
            finally:
                load_locale("en")
                menu.Destroy()

    def test_create_disabled_without_a_filesystem_destination(self):
        context = SimpleNamespace(source="list", current_folder="", owner=None)
        menu = wx.Menu()
        try:
            self.assertFalse(create_item.append_menu(menu, lambda: context).IsEnabled())
        finally:
            menu.Destroy()

    def test_application_menus_toolbar_and_language_refresh(self):
        import main
        from common import menu_utils, window_tools
        from controls import filelist

        with tempfile.TemporaryDirectory() as folder:
            settings = Path(folder) / "settings.json"
            settings.write_text('{"preview_enabled": false, "ui_locale": "en"}')
            with mock.patch.object(window_tools, "_get_settings_file_path", return_value=str(settings)):
                frame = main.FileExplorer(initial_path=folder)
                try:
                    owner = frame.active_workspace
                    owner._update_main_menu_state()
                    self.assertTrue(owner.file_create_item.IsEnabled())
                    self.assertTrue(owner.list_create_btn.IsEnabled())
                    buttons = [child.GetWindow() for child in owner.list_toolbar.GetChildren()]
                    self.assertEqual(buttons.index(owner.list_create_btn), buttons.index(owner.list_open_btn) + 1)
                    # Dispatch the real main submenu; exercise refresh and selection too.
                    entries = create_item.shell_new.items(folder)
                    text_index = next((index for index, entry in enumerate(entries) if entry.verb == ".txt"), None)
                    if text_index is None:
                        self.skipTest("Windows has no Text Document New-menu registration")
                    owner.on_main_menu_open(SimpleNamespace(GetMenu=lambda: owner.file_menu, Skip=lambda: None))
                    submenu = owner.file_create_item.GetSubMenu()
                    with mock.patch.object(create_item, "_prompt", return_value="from main"):
                        submenu.ProcessEvent(wx.CommandEvent(wx.EVT_MENU.typeId, submenu.GetMenuItems()[text_index].GetId()))
                    path = os.path.join(folder, "from main.txt")
                    self.assertTrue(os.path.isfile(path))
                    self.assertIn(path, filelist.get_selected_list_paths(owner))
                    # Both pane menus use the same submenu and honor their destination.
                    child = Path(folder) / "child"
                    child.mkdir()
                    for source, destination in (("list", folder), ("tree", str(child))):
                        context = menu_utils.FileCommandContext(owner, source, folder, [], new_folder_target=destination)
                        menu = menu_utils.build_file_operations_menu(context)
                        try:
                            submenu = menu.GetMenuItems()[1].GetSubMenu()
                            with mock.patch.object(create_item, "_prompt", return_value=source):
                                submenu.ProcessEvent(wx.CommandEvent(wx.EVT_MENU.typeId, submenu.GetMenuItems()[text_index].GetId()))
                            self.assertTrue(os.path.isfile(os.path.join(destination, source + ".txt")))
                        finally:
                            menu.Destroy()
                    with mock.patch.object(wx.Button, "PopupMenu", return_value=True) as show:
                        owner.list_create_btn.ProcessEvent(wx.CommandEvent(wx.EVT_BUTTON.typeId, owner.list_create_btn.GetId()))
                        show.assert_called_once()
                    for locale in available_locales():
                        load_locale(locale)
                        owner.refresh_locale()
                        self.assertEqual(owner.file_create_item.GetItemLabel(), tr("context_create"))
                        self.assertEqual(owner.file_create_item.GetHelp(), tr("create_hint"))
                        self.assertEqual(owner.list_create_btn.GetToolTip().GetTip(), tr("create_hint"))
                        self.assertEqual(owner.file_create_item.GetSubMenu().GetMenuItems()[text_index].GetItemLabel(), entries[text_index].label)
                finally:
                    frame.Destroy()
                    load_locale("en")


if __name__ == "__main__":
    unittest.main()
