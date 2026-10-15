"""Word bookmark generator; all COM access belongs to one worker thread.

The original document keeps its format. The editor is a native app window;
no VBA project is read or modified.
"""
import gc
import json
import logging
import os
import queue
import re
import shutil
import tempfile
import threading

from localization import tr

logger = logging.getLogger(__name__)
STATE_VARIABLE = 'DEXGeneratorFields'


class GeneratorError(RuntimeError):
    pass


def _same_path(left, right):
    if os.path.normcase(os.path.realpath(left)) == os.path.normcase(os.path.realpath(right)):
        return True
    return os.path.exists(left) and os.path.exists(right) and os.path.samefile(left, right)


class DocumentGenerator:
    """A session used only by its creating COM apartment."""

    def __init__(self, source):
        self.source = os.path.abspath(source)
        self.app = self.document = None
        self.rows = []
        self._window_placement = None

    def open(self):
        from file_operations.word_merge import is_word
        if not is_word(self.source):
            raise GeneratorError(tr('generator_select_file'))
        try:
            import win32com.client
            self.app = win32com.client.DispatchEx('Word.Application')
        except Exception as error:
            raise GeneratorError(tr('generator_word_required')) from error
        security = update_links = None
        try:
            security = self.app.AutomationSecurity
            update_links = self.app.Options.UpdateLinksAtOpen
            self.app.AutomationSecurity = 3
            self.app.Options.UpdateLinksAtOpen = False
            self.document = self.app.Documents.Open(
                FileName=self.source, ReadOnly=False, AddToRecentFiles=True, Visible=False)
            if self.document.ReadOnly or self.document.ProtectionType != -1:
                raise GeneratorError(tr('generator_protected'))
            self.rows = self._load_rows()
            self.app.Visible = True
            self.document.Windows(1).Visible = True
            self.document.Activate()
        except Exception:
            try:
                self.app.Quit(0)
            except Exception:
                logger.debug('Cannot close failed generator session', exc_info=True)
            raise
        finally:
            try:
                if security is not None:
                    self.app.AutomationSecurity = security
                if update_links is not None:
                    self.app.Options.UpdateLinksAtOpen = update_links
            except Exception:
                logger.debug('Cannot restore Word options', exc_info=True)
        return self.snapshot()

    def _state_variable(self):
        variables = self.document.Variables
        for index in range(1, variables.Count + 1):
            variable = variables.Item(index)
            if variable.Name == STATE_VARIABLE:
                return variable
        return None

    def _load_rows(self):
        variable = self._state_variable()
        if variable is None:
            return []
        try:
            rows = json.loads(variable.Value)
            if not isinstance(rows, list) or any(
                    not isinstance(row, dict) or set(row) != {'name', 'value'} or
                    not all(isinstance(value, str) for value in row.values()) for row in rows):
                raise ValueError('Invalid rows')
            self._validate_names(rows)
            return rows
        except (ValueError, TypeError, GeneratorError) as error:
            raise GeneratorError(tr('generator_invalid_state')) from error

    def _store_rows(self):
        value = json.dumps(self.rows, ensure_ascii=False)
        variable = self._state_variable()
        if variable is None:
            self.document.Variables.Add(STATE_VARIABLE, value)
        else:
            variable.Value = value

    def snapshot(self):
        return [dict(row) for row in self.rows]

    @staticmethod
    def _validate_names(rows):
        names = set()
        for row in rows:
            name = row['name']
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,39}', name):
                raise GeneratorError(tr('generator_invalid_name'))
            if name.casefold() in names:
                raise GeneratorError(tr('generator_duplicate_name'))
            names.add(name.casefold())

    def update_rows(self, rows):
        if rows == self.rows:
            return
        if len(rows) != len(self.rows):
            raise GeneratorError(tr('generator_invalid_state'))
        self._validate_names(rows)
        renames = []
        # Validate every rename before changing the document.
        for old, new in zip(self.rows, rows):
            if old['name'] != new['name']:
                if self.document.Bookmarks.Exists(new['name']):
                    raise GeneratorError(tr('generator_duplicate_name'))
                if not self.document.Bookmarks.Exists(old['name']):
                    raise GeneratorError(tr('generator_missing_bookmark', name=old['name']))
                renames.append((old['name'], new['name'],
                                self.document.Bookmarks(old['name']).Range.Duplicate))
        for old, new, area in renames:
            self.document.Bookmarks.Add(new, area)
            self.document.Bookmarks(old).Delete()
        self.rows = [dict(row) for row in rows]
        self._store_rows()

    def add_selection(self):
        if not _same_path(self.app.ActiveDocument.FullName, self.document.FullName):
            raise GeneratorError(tr('generator_select_text'))
        area = self.app.Selection.Range.Duplicate
        if '\x07' in area.Text:
            raise GeneratorError(tr('generator_table_selection'))
        if area.End == area.StoryLength and area.Text.endswith('\r'):
            area.MoveEnd(1, -1)
        if area.Start == area.End:
            raise GeneratorError(tr('generator_select_text'))
        for row in self.rows:
            if self.document.Bookmarks.Exists(row['name']):
                other = self.document.Bookmarks(row['name']).Range
                if area.InStory(other) and area.Start < other.End and other.Start < area.End:
                    raise GeneratorError(tr('generator_overlap'))
        number = len(self.rows) + 1
        used_names = {row['name'].casefold() for row in self.rows}
        while ('bookmark' + str(number)) in used_names or self.document.Bookmarks.Exists('bookmark' + str(number)):
            number += 1
        name = 'bookmark' + str(number)
        self.document.Bookmarks.Add(name, area)
        self.rows.append({'name': name, 'value': area.Text.replace('\r', '\n')})
        self._store_rows()

    def delete_row(self, index):
        name = self.rows[index]['name']
        if self.document.Bookmarks.Exists(name):
            self.document.Bookmarks(name).Delete()
        del self.rows[index]
        self._store_rows()

    def _validate_bookmarks(self):
        areas = []
        for row in self.rows:
            if not self.document.Bookmarks.Exists(row['name']):
                raise GeneratorError(tr('generator_missing_bookmark', name=row['name']))
            area = self.document.Bookmarks(row['name']).Range
            for other in areas:
                if area.InStory(other) and ((area.Start < other.End and other.Start < area.End)
                                            or area.Start == other.Start):
                    raise GeneratorError(tr('generator_overlap'))
            areas.append(area)

    def _fill_output(self, output):
        # Replace backwards and rebuild bookmarks: Word otherwise expands an
        # adjacent bookmark when replacing its neighbour's text.
        snapshots = []
        for row in self.rows:
            area = output.Bookmarks(row['name']).Range.Duplicate
            snapshots.append(dict(row, area=area, start=area.Start, end=area.End))
        for item in snapshots:
            output.Bookmarks(item['name']).Delete()
        for item in sorted(snapshots, key=lambda item: item['start'], reverse=True):
            area = item['area']
            area.SetRange(item['start'], item['end'])
            area.Text = item['value'].replace('\r\n', '\r').replace('\n', '\r')
            item['length'] = area.End - area.Start
        for item in snapshots:
            shift = sum(other['length'] - (other['end'] - other['start'])
                        for other in snapshots if other['start'] < item['start']
                        and item['area'].InStory(other['area']))
            item['area'].SetRange(item['start'] + shift, item['start'] + shift + item['length'])
            output.Bookmarks.Add(item['name'], item['area'])

    def export_document(self, target):
        current_path = self.document.FullName
        target = os.path.abspath(target)
        if _same_path(target, self.source) or _same_path(target, current_path):
            raise GeneratorError(tr('generator_keep_source'))
        extension = os.path.splitext(current_path)[1].lower()
        if os.path.splitext(target)[1].lower() != extension:
            raise GeneratorError(tr('generator_keep_format', extension=extension))
        self._validate_bookmarks()
        self._store_rows()
        self.document.Save()
        security = self.app.AutomationSecurity
        output = None
        with tempfile.TemporaryDirectory(prefix='docexplorer-generator-') as folder:
            temporary = os.path.join(folder, 'output' + extension)
            shutil.copyfile(current_path, temporary)
            try:
                self.app.AutomationSecurity = 3
                output = self.app.Documents.Open(FileName=temporary, ReadOnly=False,
                                                 AddToRecentFiles=False, Visible=False)
                output.TrackRevisions = False
                self._fill_output(output)
                output.Variables(STATE_VARIABLE).Delete()
                output.Save()
                output.Close(False)
                output = None
                # Copy only a fully saved result. Word never converts formats.
                shutil.copyfile(temporary, target)
            finally:
                try:
                    if output is not None:
                        output.Close(False)
                finally:
                    self.app.AutomationSecurity = security
                    self.document.Activate()
        return target

    def arrange_window(self, rectangle):
        """Save the native placement (including maximized state), then tile Word."""
        import win32con
        import win32gui
        window = self.document.Windows(1)
        hwnd = window.Hwnd
        if self._window_placement is None:
            self._window_placement = (hwnd, win32gui.GetWindowPlacement(hwnd))
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        x, y, width, height = rectangle
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, x, y, width, height,
                              win32con.SWP_SHOWWINDOW)
        self.document.Activate()
        self.app.Activate()
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            # Windows may deny foreground focus when another app has user input.
            logger.debug('Windows declined Word foreground activation', exc_info=True)
        return hwnd

    def restore_window(self):
        if self._window_placement is not None:
            import win32gui
            hwnd, placement = self._window_placement
            if win32gui.IsWindow(hwnd):
                win32gui.SetWindowPlacement(hwnd, placement)
            self._window_placement = None

    def needs_save(self):
        return self._document_is_open() and not self.document.Saved

    def _document_is_open(self):
        if self.document is None or self.app is None:
            return False
        if self._window_placement is not None:
            import win32gui
            if not win32gui.IsWindow(self._window_placement[0]):
                return False
        documents = self.app.Documents
        return any(documents.Item(i) == self.document for i in range(1, documents.Count + 1))

    def close_document(self, save_changes=0):
        """Restore before closing our document; keep other Word documents open."""
        document_open = self._document_is_open()
        self.restore_window()
        if self.document is not None:
            if document_open:
                self.document.Close(save_changes)
            self.document = None
        if self.app is not None:
            try:
                count = self.app.Documents.Count
            except Exception:
                # A user may already have closed Word itself. The missing
                # document window lets us finish closing the form in that case.
                if document_open:
                    raise
            else:
                if count == 0:
                    self.app.Quit(0)
            self.app = None

    def detach(self):
        self.restore_window()
        self.document = self.app = None


class GeneratorWorker:
    """Serialize COM operations; only plain Python data reaches the wx thread."""

    def __init__(self, source, dispatch):
        self.source = source
        self.dispatch = dispatch
        self.commands = queue.Queue()
        self.thread = threading.Thread(target=self._run, name='document-generator', daemon=True)
        self.thread.start()

    def submit(self, operation, callback):
        self.commands.put((operation, callback))

    def close(self):
        self.commands.put(None)

    def _run(self):
        session = DocumentGenerator(self.source)
        com = None
        startup_error = None
        try:
            import pythoncom
            pythoncom.CoInitialize()
            com = pythoncom
        except Exception:
            startup_error = tr('generator_word_required')
        try:
            while True:
                try:
                    command = self.commands.get(timeout=0.05)
                except queue.Empty:
                    if com is not None:
                        com.PumpWaitingMessages()
                    continue
                if command is None:
                    break
                operation, callback = command
                try:
                    if startup_error:
                        raise GeneratorError(startup_error)
                    result = operation(session)
                except Exception as error:
                    self.dispatch(callback, None, str(error))
                else:
                    self.dispatch(callback, result, None)
        finally:
            try:
                # Forced parent destruction bypasses the form's close handler.
                # In that case let Word ask about any unsaved document changes.
                session.close_document(save_changes=-2)
            except Exception:
                logger.debug('Could not close generator Word document', exc_info=True)
            try:
                session.detach()
            finally:
                gc.collect()
                if com is not None:
                    com.CoUninitialize()


def show_document_generator(owner, path):
    from controls.document_generator import DocumentGeneratorFrame
    windows = getattr(owner, '_document_generators', None)
    if windows is None:
        owner._document_generators = windows = {}
    key = os.path.normcase(os.path.abspath(path))
    existing = windows.get(key)
    if existing:
        existing.Show()
        existing.Raise()
        return
    frame = DocumentGeneratorFrame(owner, path)
    windows[key] = frame
    frame.Show()
