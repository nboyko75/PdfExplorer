"""Excel cell table used by workbook review grids."""
import os
import wx
import wx.adv as adv
import wx.grid as gridlib
from localization import tr
from file_operations import excel_merge as engine


def column_name(index):
    result = ''
    while index:
        index, rem = divmod(index - 1, 26)
        result = chr(65 + rem) + result
    return result


def display(cell):
    if engine.is_empty_display(cell):
        return ''
    if cell.display_text is not None:
        return cell.display_text
    if cell.formula:
        return '' if cell.result is None else engine.format_system_number(cell.result)
    return engine.format_system_number(cell.value)


class SheetTable(gridlib.GridTableBase):
    def __init__(self, sheet, conflicts, difference_positions=None, source_colors=None, min_columns=0):
        super().__init__()
        self.sheet, self.conflicts = sheet, conflicts
        self.difference_positions = difference_positions
        self.labels = {}
        self.colors = {}
        self.value_indices = {}
        self.choice_sources = {}
        self.source_colors = {engine.source_key(source): color
                              for source, color in (source_colors or {}).items()}
        self.font_cache = {}
        self.row_numbers = sorted(engine.populated_rows(sheet))
        max_col = max([sheet.cols, min_columns] + [c for r, c in conflicts])
        self.col_numbers = [c for c in range(1, max_col + 1) if c not in sheet.hidden_cols]
        self.row_indices = {number: index for index, number in enumerate(self.row_numbers)}
        self.col_indices = {number: index for index, number in enumerate(self.col_numbers)}
        self.rows, self.cols = len(self.row_numbers), len(self.col_numbers)
        for pos, conflict in conflicts.items():
            # Comparison groups equal values, but the editor must retain every
            # contributing workbook's identity and color, even for duplicates.
            choices = [(index, engine.source_key(source))
                       for index, sources in enumerate(conflict.sources)
                       for source_index, source in enumerate(sources)
                       if (index == 0 and source_index == 0) or not engine.is_empty_display(conflict.values[index])]
            self.value_indices[pos] = [index for index, source in choices]
            self.choice_sources[pos] = [source for index, source in choices]
            self.labels[pos] = [display(conflict.values[index]) for index, source in choices]
            self.colors[pos] = [self.source_colors.get(source, (0, 0, 0)) for index, source in choices]
            if conflict.selected is not None and conflict.selected not in self.value_indices[pos]:
                conflict.selected = 0
                conflict.selected_source = None

    def selected_choice(self, pos):
        conflict = self.conflicts[pos]
        matches = [i for i, value_index in enumerate(self.value_indices[pos])
                   if value_index == conflict.selected]
        return next((i for i in matches if self.choice_sources[pos][i] == conflict.selected_source),
                    matches[0] if matches else None)

    def select_choice(self, pos, index):
        conflict = self.conflicts[pos]
        conflict.selected = self.value_indices[pos][index]
        conflict.selected_source = self.choice_sources[pos][index]

    def selected_color(self, pos):
        conflict = self.conflicts[pos]
        selected = self.selected_choice(pos)
        if selected is None:
            return (0, 0, 0)
        if conflict.selected_source is None and self.value_indices[pos].count(conflict.selected) > 1:
            # An automatic choice shared by several files has no single source.
            return (0, 0, 0)
        return self.colors[pos][selected]

    def GetNumberRows(self):
        return self.rows

    def GetNumberCols(self):
        return self.cols

    def cell_position(self, row, col):
        return self.row_numbers[row], self.col_numbers[col]

    def grid_position(self, row, col):
        if row in self.row_indices and col in self.col_indices:
            return self.row_indices[row], self.col_indices[col]
        return None

    def GetRowLabelValue(self, row):
        return str(self.row_numbers[row])

    def GetColLabelValue(self, col):
        return column_name(self.col_numbers[col])

    def GetValue(self, row, col):
        pos = self.cell_position(row, col)
        if pos[0] in self.sheet.hidden_rows or pos[1] in self.sheet.hidden_cols:
            return ""
        if self.difference_positions is not None and pos not in self.difference_positions:
            return ""
        conflict = self.conflicts.get(pos)
        if conflict:
            return display(conflict.values[conflict.selected]) if conflict.selected is not None else tr('merge_choose')
        cell = self.sheet.cells.get(pos, engine.EMPTY)
        return '' if cell.value is None or cell.value == '' else display(cell)

    def IsEmptyCell(self, row, col):
        return not bool(self.GetValue(row, col))

    def SetValue(self, row, col, value):
        pos = self.cell_position(row, col)
        if pos in self.conflicts and value in self.labels[pos]:
            self.select_choice(pos, self.labels[pos].index(value))

    def build_attr(self, row, col):
        """Transfer each attribute/editor to Grid.SetAttr once, never during painting."""
        pos = self.cell_position(row, col)
        attr = gridlib.GridCellAttr()
        cell = self.sheet.cells.get(pos, engine.EMPTY)
        value = cell.result if cell.formula else cell.value
        horizontal = wx.ALIGN_RIGHT if isinstance(value, (int, float)) and not isinstance(value, bool) else wx.ALIGN_LEFT
        vertical = wx.ALIGN_BOTTOM
        style = self.sheet.styles.get(pos)
        if style:
            key = tuple(style[n] for n in ('font_name', 'font_size', 'bold', 'italic', 'underline', 'strike'))
            font = self.font_cache.get(key)
            if font is None:
                font = wx.Font(max(1, round(style['font_size'])), wx.FONTFAMILY_DEFAULT,
                               wx.FONTSTYLE_ITALIC if style['italic'] else wx.FONTSTYLE_NORMAL,
                               wx.FONTWEIGHT_BOLD if style['bold'] else wx.FONTWEIGHT_NORMAL,
                               style['underline'], style['font_name'])
                font.SetStrikethrough(style['strike'])
                self.font_cache[key] = font
            attr.SetFont(font)
            attr.SetTextColour(wx.Colour(*style['foreground']))
            attr.SetBackgroundColour(wx.Colour(*style['background']))
            horizontal = {-4131: wx.ALIGN_LEFT, -4152: wx.ALIGN_RIGHT,
                          -4108: wx.ALIGN_CENTER, 7: wx.ALIGN_CENTER}.get(style['horizontal'], horizontal)
            vertical = {-4160: wx.ALIGN_TOP, -4108: wx.ALIGN_CENTER,
                        -4107: wx.ALIGN_BOTTOM}.get(style['vertical'], vertical)
        attr.SetAlignment(horizontal, vertical)
        attr.SetOverflow(True)
        if pos in self.conflicts:
            attr.SetReadOnly(False)
            attr.SetRenderer(ChoiceRenderer())
            attr.SetEditor(ColoredChoiceEditor(self.labels[pos], self.colors[pos], self.choice_sources[pos]))
        else:
            attr.SetReadOnly(True)
            attr.SetRenderer(OverflowRenderer())
        return attr


class OverflowRenderer(gridlib.GridCellStringRenderer):
    """Paint spill text in each empty cell so its background cannot erase it."""
    def Clone(self):
        return OverflowRenderer()

    def Draw(self, grid, attr, dc, rect, row, col, isSelected):
        # Native overflow repaints neighboring backgrounds, erasing spill text
        # already drawn there. Each renderer paints only its own cell instead.
        local_attr = attr.Clone()
        local_attr.SetOverflow(False)
        try:
            super().Draw(grid, local_attr, dc, rect, row, col, isSelected)
        finally:
            local_attr.DecRef()
        table = grid.GetTable()
        if not table.IsEmptyCell(row, col):
            return
        for step in (-1, 1):
            origin = col + step
            while 0 <= origin < table.GetNumberCols() and table.IsEmptyCell(row, origin):
                origin += step
            if 0 <= origin < table.GetNumberCols():
                self.draw_spill(grid, dc, rect, row, col, origin)

    def draw_spill(self, grid, dc, rect, row, col, origin):
        table = grid.GetTable()
        source_attr = grid.GetOrCreateCellAttr(row, origin)
        try:
            horizontal, vertical = source_attr.GetAlignment()
            if not source_attr.GetOverflow():
                return
            source_rect = wx.Rect(rect)
            offset = (sum(grid.GetColSize(c) for c in range(origin, col)) if origin < col
                      else -sum(grid.GetColSize(c) for c in range(col, origin)))
            source_rect.x -= offset
            source_rect.width = grid.GetColSize(origin)
            # Match GridCellStringRenderer's inset before laying out text.
            # Its text margins are applied inside this one-pixel inset.
            source_rect.Deflate(1)
            dc.SetFont(grid.GetCellFont(row, origin))
            color = grid.GetCellTextColour(row, origin)
            pos = table.cell_position(row, origin)
            conflict = table.conflicts.get(pos)
            cell = (conflict.values[conflict.selected] if conflict and conflict.selected is not None
                    else table.sheet.cells.get(pos, engine.EMPTY))
            value = cell.result if cell.formula else cell.value
            if not isinstance(value, str):
                return  # Excel does not spill numbers into neighboring cells.
            if conflict and conflict.selected is not None:
                color = wx.Colour(*table.selected_color(pos))
            dc.SetTextForeground(color)
            text = table.GetValue(row, origin)
            width, height = dc.GetTextExtent(text)
            x = source_rect.x + 1
            if horizontal == wx.ALIGN_RIGHT:
                x = source_rect.x + source_rect.width - width - 1
            elif horizontal == wx.ALIGN_CENTER:
                x = source_rect.x + (source_rect.width - width) // 2
            if x >= rect.x + rect.width or x + width <= rect.x:
                return
            y = source_rect.y + 1
            if vertical == wx.ALIGN_CENTER:
                y = source_rect.y + (source_rect.height - height) // 2
            elif vertical == wx.ALIGN_BOTTOM:
                y = source_rect.bottom - height
            clip = wx.DCClipper(dc, rect)
            dc.SetBackgroundMode(wx.TRANSPARENT)
            dc.DrawText(text, x, y)
            del clip
        finally:
            source_attr.DecRef()


class ChoiceRenderer(OverflowRenderer):
    """Keep a drop-down affordance visible when the cell is not being edited."""
    def Clone(self):
        return ChoiceRenderer()

    def Draw(self, grid, attr, dc, rect, row, col, isSelected):
        table = grid.GetTable()
        pos = table.cell_position(row, col)
        color = table.selected_color(pos)
        text_attr = attr.Clone()
        text_attr.SetTextColour(wx.Colour(*color))
        text_attr.SetOverflow(True)
        if isSelected:
            text_attr.SetBackgroundColour(grid.GetSelectionBackground())
        try:
            # Keep provenance colors when selected; the native renderer would
            # otherwise replace them with the grid's selection foreground.
            super().Draw(grid, text_attr, dc, rect, row, col, False)
        finally:
            text_attr.DecRef()
        width = min(20, rect.width)
        button = wx.Rect(rect.x + rect.width - width, rect.y, width, rect.height)
        wx.RendererNative.Get().DrawComboBoxDropButton(grid, dc, button, 0)


class ColoredComboBox(adv.OwnerDrawnComboBox):
    def __init__(self, parent, id, labels, colors, sources=None):
        self.item_colors = colors
        self.item_sources = list(sources or [])
        super().__init__(parent, id, choices=labels, style=wx.CB_READONLY)
        self.SetPopupMinWidth(max([100] + [self.OnMeasureItemWidth(i) for i in range(self.GetCount())]))

    def item_text(self, item, flags=0):
        label = self.GetString(item)
        if item > 0 and self.item_sources and not flags & adv.ODCB_PAINTING_CONTROL:
            return f'{label}  [{os.path.basename(self.item_sources[item])}]'
        return label

    def OnDrawBackground(self, dc, rect, item, flags):
        dc.SetPen(wx.TRANSPARENT_PEN)
        dc.SetBrush(wx.Brush(wx.Colour(226, 239, 218) if flags & adv.ODCB_PAINTING_SELECTED else wx.WHITE))
        dc.DrawRectangle(rect)

    def OnDrawItem(self, dc, rect, item, flags):
        if item == wx.NOT_FOUND:
            item = self.GetSelection()
        if not 0 <= item < self.GetCount():
            return
        dc.SetFont(self.GetFont())
        dc.SetTextForeground(wx.Colour(*self.item_colors[item]))
        dc.DrawLabel(self.item_text(item, flags), wx.Rect(rect.x + 3, rect.y, max(0, rect.width - 6), rect.height),
                     wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)

    def OnMeasureItem(self, item):
        return max(22, self.GetCharHeight() + 6)

    def OnMeasureItemWidth(self, item):
        if not 0 <= item < self.GetCount():
            return 100
        return self.GetTextExtent(self.item_text(item)).width + 12


class ColoredChoiceEditor(gridlib.GridCellEditor):
    """Index-based selection keeps equal display texts from selecting the wrong formula."""
    def __init__(self, labels, colors, sources=None):
        super().__init__()
        self.labels, self.colors = list(labels), list(colors)
        self.sources = list(sources or [])
        self.initial = self.pending = wx.NOT_FOUND

    def Clone(self):
        return ColoredChoiceEditor(self.labels, self.colors, self.sources)

    def Create(self, parent, id, evtHandler):
        self.combo = ColoredComboBox(parent, id, self.labels, self.colors, self.sources)
        self.SetControl(self.combo)
        self.combo.Bind(wx.EVT_COMBOBOX, self.on_choice)
        self.combo.Bind(wx.EVT_COMBOBOX_DROPDOWN, self.on_dropdown)
        self.combo.Bind(wx.EVT_COMBOBOX_CLOSEUP, self.on_closeup)
        self.popup_open = False
        if evtHandler:
            evtHandler.Bind(wx.EVT_KILL_FOCUS, self.on_kill_focus)
            self.combo.PushEventHandler(evtHandler)

    def on_kill_focus(self, event):
        # OwnerDrawnComboBox moves focus into its separate popup window. The
        # grid's generic handler would finish editing and dismiss that popup.
        if not self.popup_open and not self.combo.IsPopupShown():
            event.Skip()

    def on_dropdown(self, event):
        self.popup_open = True
        event.Skip()

    def on_closeup(self, event):
        self.popup_open = False
        event.Skip()

    def SetSize(self, rect):
        self.combo.SetSize(rect)

    def BeginEdit(self, row, col, grid):
        self.grid, self.row, self.col = grid, row, col
        self.choice_made = False
        selected = grid.GetTable().selected_choice(grid.GetTable().cell_position(row, col))
        self.initial = wx.NOT_FOUND if selected is None else selected
        self.combo.SetSelection(self.initial)
        self.combo.SetFocus()

    def on_choice(self, event):
        self.choice_made = True
        event.Skip()
        wx.CallAfter(self.commit_choice)

    def commit_choice(self):
        grid = getattr(self, 'grid', None)
        if (grid and not grid.IsBeingDeleted() and grid.IsCellEditControlEnabled()
                and (grid.GetGridCursorRow(), grid.GetGridCursorCol()) == (self.row, self.col)):
            grid.SaveEditControlValue()
            grid.DisableCellEditControl()

    def EndEdit(self, row, col, grid, oldval):
        self.pending = self.combo.GetSelection()
        if self.pending != wx.NOT_FOUND and (self.pending != self.initial or getattr(self, 'choice_made', False)):
            # wx must receive a nonempty change token even for a blank label.
            # ApplyEdit commits the index, never this notification string.
            return str(self.pending)
        return None

    def ApplyEdit(self, row, col, grid):
        grid.GetTable().select_choice(grid.GetTable().cell_position(row, col), self.pending)
        grid.ForceRefresh()

    def Reset(self):
        self.combo.SetSelection(self.initial)

    def GetValue(self):
        return self.combo.GetValue()
