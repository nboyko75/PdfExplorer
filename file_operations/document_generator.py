"""Word bookmark generator; all COM access belongs to one worker thread.

The original document keeps its format. The editor is a native app window;
no VBA project is read or modified.
"""
import gc
from copy import deepcopy
import json
import logging
import os
import queue
import re
import shutil
import tempfile
import threading
import uuid

from localization import tr

logger = logging.getLogger(__name__)
STATE_VARIABLE = 'DEXGeneratorFields'
TABLE_STATE_VARIABLE = 'DEXGeneratorTables'


class GeneratorError(RuntimeError):
    pass


class WordDisconnected(str):
    """A plain-text worker result identifying a lost Word connection."""


def _word_disconnected(error):
    codes = {0x80010108, 0x800401FD, 0x80010006, 0x80010007,
             0x80010012, 0x800706BA, 0x800706BE}
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        hresults = [getattr(error, 'hresult', None)]
        details = getattr(error, 'excepinfo', None)
        if isinstance(details, tuple) and len(details) > 5:
            hresults.append(details[5])
        if any(isinstance(code, int) and code & 0xFFFFFFFF in codes for code in hresults):
            return True
        error = error.__cause__ or error.__context__
    return False


def _same_path(left, right):
    if os.path.normcase(os.path.realpath(left)) == os.path.normcase(os.path.realpath(right)):
        return True
    return os.path.exists(left) and os.path.exists(right) and os.path.samefile(left, right)


def check_document_available(path):
    """Check editable access without launching Word or changing the file."""
    from file_operations.word_merge import is_word
    if not is_word(path):
        raise GeneratorError(tr('generator_select_file'))
    try:
        if os.name == 'nt':
            import pywintypes
            import win32con
            import win32file
            # Exclusive access detects files already in use, including Word's
            # sharing locks. OPEN_EXISTING never creates or truncates the file.
            try:
                handle = win32file.CreateFile(
                    path, win32con.GENERIC_READ | win32con.GENERIC_WRITE, 0,
                    None, win32con.OPEN_EXISTING, win32con.FILE_ATTRIBUTE_NORMAL, None)
            except pywintypes.error as error:
                raise GeneratorError(error.strerror) from error
            handle.Close()
        else:
            with open(path, 'r+b'):
                pass
    except ImportError as error:
        raise GeneratorError(tr('generator_word_required')) from error
    except OSError as error:
        raise GeneratorError(str(error)) from error


class DocumentGenerator:
    """A session used only by its creating COM apartment."""

    def __init__(self, source):
        self.source = os.path.abspath(source)
        self.app = self.document = None
        self.rows = []
        self.tables = []
        self._window_placement = None

    def open(self):
        # Check again immediately before COM startup in case the file became
        # unavailable after the form's initial check or a Retry confirmation.
        check_document_available(self.source)
        try:
            import win32com.client
            self.app = win32com.client.DispatchEx('Word.Application')
        except Exception as error:
            raise GeneratorError(tr('generator_word_required')) from error
        security = update_links = alerts = None
        opened = False
        try:
            security = self.app.AutomationSecurity
            update_links = self.app.Options.UpdateLinksAtOpen
            alerts = self.app.DisplayAlerts
            self.app.AutomationSecurity = 3
            self.app.Options.UpdateLinksAtOpen = False
            self.app.DisplayAlerts = 0  # wdAlertsNone: report errors in our form.
            self.document = self.app.Documents.Open(
                FileName=self.source, ReadOnly=False, AddToRecentFiles=True, Visible=False)
            if self.document.ReadOnly or self.document.ProtectionType != -1:
                raise GeneratorError(tr('generator_protected'))
            self.rows = self._load_rows()
            self.tables = self._load_tables()
            self._validate_names(self.rows + self.tables)
            self.app.Visible = True
            self.document.Windows(1).Visible = True
            self.document.Activate()
            opened = True
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
                if alerts is not None:
                    self.app.DisplayAlerts = alerts
            except Exception:
                logger.debug('Cannot restore Word options', exc_info=True)
            if not opened:
                self.document = self.app = None
        return self.snapshot()

    def _state_variable(self, name=STATE_VARIABLE):
        variables = self.document.Variables
        for index in range(1, variables.Count + 1):
            variable = variables.Item(index)
            if variable.Name == name:
                return variable
        return None

    def _load_rows(self):
        variable = self._state_variable()
        if variable is None:
            return []
        try:
            rows = json.loads(variable.Value)
            self._validate_rows(rows)
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

    @staticmethod
    def _validate_rows(rows):
        if not isinstance(rows, list) or any(
                not isinstance(row, dict) or set(row) not in ({'name', 'value'}, {'name', 'value', 'group'}) or
                not all(isinstance(value, str) for value in row.values()) or
                ('group' in row and not row['group']) for row in rows):
            raise GeneratorError(tr('generator_invalid_state'))
        groups = {}
        previous = None
        # Linked bookmarks stay adjacent so one value control spans their rows.
        for row in rows:
            group = row.get('group')
            if group is not None:
                if group in groups and (group != previous or groups[group] != row['value']):
                    raise GeneratorError(tr('generator_invalid_state'))
                groups[group] = row['value']
            previous = group

    def snapshot(self):
        return [dict(row) for row in self.rows]

    def state(self):
        return {'rows': self.snapshot(), 'tables': deepcopy(self.tables)}

    def _load_tables(self):
        variable = self._state_variable(TABLE_STATE_VARIABLE)
        if variable is None:
            return []
        try:
            tables = json.loads(variable.Value)
            if not isinstance(tables, list):
                raise ValueError('Invalid tables')
            for table in tables:
                if set(table) != {'name', 'rows', 'widths', 'applied_rows'}:
                    raise ValueError('Invalid table')
                if (not isinstance(table['widths'], list) or not table['widths'] or
                        any(not isinstance(width, (int, float)) or not 0 < width < 10000
                            for width in table['widths']) or
                        type(table['applied_rows']) is not int or table['applied_rows'] < 1):
                    raise ValueError('Invalid table dimensions')
                self._validate_table_values(table['rows'], len(table['widths']))
            self._validate_names(tables)
            return tables
        except (ValueError, TypeError, KeyError, GeneratorError) as error:
            raise GeneratorError(tr('generator_invalid_state')) from error

    @staticmethod
    def _validate_table_values(rows, columns):
        if (not isinstance(rows, list) or not rows or
                any(not isinstance(row, list) or len(row) != columns or
                    any(not isinstance(value, str) or '\x07' in value for value in row) for row in rows)):
            raise GeneratorError(tr('generator_table_changed'))

    def _store_tables(self):
        variable = self._state_variable(TABLE_STATE_VARIABLE)
        if not self.tables and variable is None:
            return
        value = json.dumps(self.tables, ensure_ascii=False)
        if variable is None:
            self.document.Variables.Add(TABLE_STATE_VARIABLE, value)
        else:
            variable.Value = value

    def update_fields(self, rows, tables):
        self._validate_names(rows + tables)
        if len(tables) != len(self.tables):
            raise GeneratorError(tr('generator_invalid_state'))
        # Check every table before committing any scalar edits.
        for old, new in zip(self.tables, tables):
            self._validate_table_values(new['rows'], len(old['widths']))
            if old['name'] != new['name']:
                if self.document.Bookmarks.Exists(new['name']):
                    raise GeneratorError(tr('generator_duplicate_name'))
                if not self.document.Bookmarks.Exists(old['name']):
                    raise GeneratorError(tr('generator_missing_bookmark', name=old['name']))
        self.update_rows(rows)
        changed = False
        for old, new in zip(self.tables, tables):
            if old['name'] != new['name']:
                area = self.document.Bookmarks(old['name']).Range.Duplicate
                self.document.Bookmarks.Add(new['name'], area)
                self.document.Bookmarks(old['name']).Delete()
                old['name'] = new['name']
                changed = True
            if old['rows'] != new['rows']:
                old['rows'] = deepcopy(new['rows'])
                changed = True
        if changed:
            self._store_tables()

    def _check_overlap(self, area, exclude=None):
        for item in self.rows + self.tables:
            if item['name'] == exclude or not self.document.Bookmarks.Exists(item['name']):
                continue
            other = self.document.Bookmarks(item['name']).Range
            if area.InStory(other) and area.Start < other.End and other.Start < area.End:
                raise GeneratorError(tr('generator_overlap'))

    def _new_name(self, prefix):
        names = {item['name'].casefold() for item in self.rows + self.tables}
        number = 1
        while prefix + str(number) in names or self.document.Bookmarks.Exists(prefix + str(number)):
            number += 1
        return prefix + str(number)

    @staticmethod
    def _cell_text(cell):
        text = cell.Range.Text
        if text.endswith('\r\x07'):
            text = text[:-2]
        return text.replace('\r', '\n')

    @staticmethod
    def _table_rows(table):
        # Rows.Item fails anywhere in a table with vertical merges. Expanding
        # ranges by wdRow also works for rows with horizontal/vertical merges.
        area = table.Range
        position, end = area.Start, area.End
        rows = []
        while position < end:
            row = area.Duplicate
            row.SetRange(position, position)
            row.Expand(10)  # wdRow
            if row.Start != position or not position < row.End <= end:
                raise GeneratorError(tr('generator_table_changed'))
            rows.append(row)
            position = row.End
        return rows

    def add_table_selection(self):
        if not _same_path(self.app.ActiveDocument.FullName, self.document.FullName):
            raise GeneratorError(tr('generator_select_table_row'))
        area = self.app.Selection.Range.Duplicate
        if area.Tables.Count != 1 or area.Start == area.End:
            raise GeneratorError(tr('generator_select_table_row'))
        table = area.Tables.Item(1)
        if table.NestingLevel != 1 or table.Range.Tables.Count != 1:
            raise GeneratorError(tr('generator_select_table_row'))
        # A multi-row selection uses its last row, including that row's values.
        selected = [row for row in self._table_rows(table)
                    if row.Start < area.End and area.Start < row.End]
        if not selected:
            raise GeneratorError(tr('generator_select_table_row'))
        row = selected[-1]
        if area.Start > row.Start or area.End < row.End or not row.Cells.Count:
            raise GeneratorError(tr('generator_select_table_row'))
        self._check_overlap(row)
        name = self._new_name('table')
        values = [self._cell_text(row.Cells.Item(i)) for i in range(1, row.Cells.Count + 1)]
        widths = [float(row.Cells.Item(i).Width) for i in range(1, row.Cells.Count + 1)]
        self.document.Bookmarks.Add(name, row)
        self.tables.append({'name': name, 'rows': [values], 'widths': widths, 'applied_rows': 1})
        self._store_tables()

    def delete_table(self, index):
        name = self.tables[index]['name']
        if self.document.Bookmarks.Exists(name):
            self.document.Bookmarks(name).Delete()
        del self.tables[index]
        self._store_tables()

    def _table_region(self, item):
        if not self.document.Bookmarks.Exists(item['name']):
            raise GeneratorError(tr('generator_missing_bookmark', name=item['name']))
        area = self.document.Bookmarks(item['name']).Range
        try:
            if area.Tables.Count != 1:
                raise ValueError('Table removed')
            table = area.Tables.Item(1)
            if table.NestingLevel != 1 or table.Range.Tables.Count != 1:
                raise ValueError('Nested table')
            rows = [row for row in self._table_rows(table)
                    if row.Start < area.End and area.Start < row.End]
            if (len(rows) != item['applied_rows'] or area.Start != rows[0].Start or
                    area.End != rows[-1].End or
                    any(row.Cells.Count != len(item['widths']) for row in rows)):
                raise ValueError('Managed rows changed')
            self._check_overlap(area, exclude=item['name'])
            if self.document.TrackRevisions or table.Range.Revisions.Count:
                raise GeneratorError(tr('generator_table_tracked'))
            return table, rows
        except GeneratorError:
            raise
        except Exception as error:
            raise GeneratorError(tr('generator_table_changed')) from error

    @staticmethod
    def _copy_row_style(source, target):
        # Inserting the complete formatted row preserves its merged cells,
        # borders, widths and paragraph formatting, including in legacy .doc.
        target.FormattedText = source.FormattedText

    def _apply_tables(self):
        if not self.tables:
            return
        # Validate the entire batch before making any structural edits.
        for item in self.tables:
            self._table_region(item)
        before = deepcopy(self.tables)
        undo = self.app.UndoRecord
        undo.StartCustomRecord(tr('generator_title'))
        changed = False
        try:
            ordered = sorted(self.tables, key=lambda item: self.document.Bookmarks(item['name']).Range.Start,
                             reverse=True)
            for item in ordered:
                table, rows = self._table_region(item)
                start = rows[0].Start
                count, desired = item['applied_rows'], len(item['rows'])
                # Keep the selected Word row; grow or shrink only its managed block.
                while count < desired:
                    new = rows[-1].Duplicate
                    new.Collapse(0)  # wdCollapseEnd
                    # Word expands a bookmark starting at the insertion point
                    # to include the new row. Keep adjacent managed blocks apart.
                    adjacent = []
                    for other in self.rows + self.tables:
                        if other['name'] != item['name'] and self.document.Bookmarks.Exists(other['name']):
                            boundary = self.document.Bookmarks(other['name']).Range.Duplicate
                            if boundary.InStory(new) and boundary.Start == new.Start:
                                adjacent.append((other['name'], boundary))
                    try:
                        self._copy_row_style(rows[0], new)
                    finally:
                        changed = changed or new.Start != new.End
                    for name, boundary in adjacent:
                        boundary.Start = new.End
                        self.document.Bookmarks.Add(name, boundary)
                    count += 1
                    rows = [row for row in self._table_rows(table) if row.Start >= start][:count]
                while count > desired:
                    rows[-1].Cells.Delete(2)  # wdDeleteCellsEntireRow
                    changed = True
                    count -= 1
                    rows = [row for row in self._table_rows(table) if row.Start >= start][:count]
                for offset, values in enumerate(item['rows']):
                    row = rows[offset]
                    for column, value in enumerate(values, 1):
                        cell = row.Cells.Item(column)
                        if self._cell_text(cell) != value:
                            area = cell.Range.Duplicate
                            area.End -= 1
                            area.Text = value.replace('\r\n', '\r').replace('\n', '\r')
                            changed = True
                rows = [row for row in self._table_rows(table) if row.Start >= start][:count]
                area = rows[0].Duplicate
                area.End = rows[-1].End
                self.document.Bookmarks.Add(item['name'], area)
                changed = True
                item['applied_rows'] = count
            self._store_tables()
        except Exception:
            undo.EndCustomRecord()
            if changed:
                self.document.Undo(1)
            self.tables = before
            raise
        else:
            undo.EndCustomRecord()

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
        self._validate_rows(rows)
        if any(old.get('group') != new.get('group') for old, new in zip(self.rows, rows)):
            raise GeneratorError(tr('generator_invalid_state'))
        self._validate_names(rows + self.tables)
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

    def add_selection(self, shared_index=None):
        if shared_index is not None and not 0 <= shared_index < len(self.rows):
            raise GeneratorError(tr('generator_invalid_state'))
        if not _same_path(self.app.ActiveDocument.FullName, self.document.FullName):
            raise GeneratorError(tr('generator_select_text'))
        area = self.app.Selection.Range.Duplicate
        if '\x07' in area.Text:
            raise GeneratorError(tr('generator_table_selection'))
        if area.End == area.StoryLength and area.Text.endswith('\r'):
            area.MoveEnd(1, -1)
        if area.Start == area.End:
            raise GeneratorError(tr('generator_select_text'))
        self._check_overlap(area)
        number = len(self.rows) + 1
        used_names = {row['name'].casefold() for row in self.rows + self.tables}
        while ('bookmark' + str(number)) in used_names or self.document.Bookmarks.Exists('bookmark' + str(number)):
            number += 1
        name = 'bookmark' + str(number)
        self.document.Bookmarks.Add(name, area)
        if shared_index is None:
            self.rows.append({'name': name, 'value': area.Text.replace('\r', '\n')})
        else:
            source = self.rows[shared_index]
            group = source.setdefault('group', uuid.uuid4().hex)
            self.rows.insert(shared_index + 1, {'name': name, 'value': source['value'], 'group': group})
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

    def save_document(self):
        """Persist generator fields in the current document without filling them."""
        self._apply_tables()
        self._store_rows()
        self.document.Save()

    def export_document(self, target):
        current_path = self.document.FullName
        target = os.path.abspath(target)
        if _same_path(target, self.source) or _same_path(target, current_path):
            raise GeneratorError(tr('generator_keep_source'))
        extension = os.path.splitext(current_path)[1].lower()
        if os.path.splitext(target)[1].lower() != extension:
            raise GeneratorError(tr('generator_keep_format', extension=extension))
        self._validate_bookmarks()
        self.save_document()
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
                if self._state_variable(TABLE_STATE_VARIABLE) is not None:
                    output.Variables(TABLE_STATE_VARIABLE).Delete()
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
        connection_lost = False
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
                if connection_lost:
                    self.dispatch(callback, None, WordDisconnected(tr('generator_word_disconnected')))
                    continue
                try:
                    if startup_error:
                        raise GeneratorError(startup_error)
                    result = operation(session)
                except Exception as error:
                    if _word_disconnected(error):
                        connection_lost = True
                        logger.debug('Word connection closed', exc_info=True)
                        message = WordDisconnected(tr('generator_word_disconnected'))
                    else:
                        message = str(error)
                    self.dispatch(callback, None, message)
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
    import wx
    from controls.document_generator_frame import DocumentGeneratorFrame, show_generator_message
    windows = getattr(owner, '_document_generators', None)
    if windows is None:
        owner._document_generators = windows = {}
    key = os.path.normcase(os.path.abspath(path))
    existing = windows.get(key)
    if existing:
        existing.Show()
        existing.Raise()
        return
    while True:
        try:
            check_document_available(path)
        except GeneratorError as error:
            if show_generator_message(owner, tr('generator_open_unavailable', path=path, error=error),
                                      retry=True) != wx.ID_OK:
                return
        else:
            break
    frame = DocumentGeneratorFrame(owner, path)
    windows[key] = frame
    frame.Show()
