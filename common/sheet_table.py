"""Excel cell table used by workbook review grids."""
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
    if cell.value is None:
        return tr('merge_empty')
    if cell.display_text is not None:
        return cell.display_text
    if cell.formula:
        return '' if cell.result is None else str(cell.result)
    return str(cell.value)


class SheetTable(gridlib.GridTableBase):
    def __init__(self, sheet, conflicts, difference_positions=None, source_colors=None):
        super().__init__()
        self.sheet, self.conflicts = sheet, conflicts
        self.difference_positions = difference_positions
        self.labels = {}
        self.colors = {}
        self.source_colors = source_colors or {}
        self.font_cache = {}
        self.rows = max([sheet.rows] + [r for r, c in conflicts])
        self.cols = max([sheet.cols] + [c for r, c in conflicts])
        for pos, conflict in conflicts.items():
            labels = []
            for index, (value, sources) in enumerate(zip(conflict.values, conflict.sources)):
                labels.append(display(value))
            self.labels[pos] = labels
            self.colors[pos] = [(0, 0, 0) if i == 0 else self.source_colors.get(sources[0], (0, 0, 0))
                                for i, sources in enumerate(conflict.sources)]

    def GetNumberRows(self):
        return self.rows

    def GetNumberCols(self):
        return self.cols

    def GetColLabelValue(self, col):
        return column_name(col + 1)

    def GetValue(self, row, col):
        pos = row + 1, col + 1
        if pos[0] in self.sheet.hidden_rows or pos[1] in self.sheet.hidden_cols:
            return ""
        if self.difference_positions is not None and pos not in self.difference_positions:
            return ""
        conflict = self.conflicts.get(pos)
        if conflict:
            return self.labels[pos][conflict.selected] if conflict.selected is not None else tr('merge_choose')
        cell = self.sheet.cells.get(pos, engine.EMPTY)
        return '' if cell.value is None else display(cell)

    def IsEmptyCell(self, row, col):
        return not bool(self.GetValue(row, col))

    def SetValue(self, row, col, value):
        pos = row + 1, col + 1
        if pos in self.conflicts and value in self.labels[pos]:
            self.conflicts[pos].selected = self.labels[pos].index(value)

    def build_attr(self, row, col):
        """Transfer each attribute/editor to Grid.SetAttr once, never during painting."""
        pos = row + 1, col + 1
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
            vertical = {-4160: wx.ALIGN_TOP, -4108: wx.ALIGN_CENTER_VERTICAL,
                        -4107: wx.ALIGN_BOTTOM}.get(style['vertical'], vertical)
        attr.SetAlignment(horizontal, vertical)
        if pos in self.conflicts:
            attr.SetReadOnly(False)
            attr.SetRenderer(ChoiceRenderer())
            attr.SetEditor(ColoredChoiceEditor(self.labels[pos], self.colors[pos]))
        else:
            attr.SetReadOnly(True)
        return attr


class ChoiceRenderer(gridlib.GridCellStringRenderer):
    """Keep a drop-down affordance visible when the cell is not being edited."""
    def Clone(self):
        return ChoiceRenderer()

    def Draw(self, grid, attr, dc, rect, row, col, isSelected):
        table = grid.GetTable()
        pos = row + 1, col + 1
        selected = table.conflicts[pos].selected
        color = table.colors[pos][selected] if selected is not None else (0, 0, 0)
        dc.SetClippingRegion(rect)
        try:
            dc.SetPen(wx.TRANSPARENT_PEN)
            dc.SetBrush(wx.Brush(grid.GetSelectionBackground() if isSelected else grid.GetCellBackgroundColour(row, col)))
            dc.DrawRectangle(rect)
            dc.SetFont(grid.GetCellFont(row, col))
            dc.SetTextForeground(wx.Colour(*color))
            width = min(20, rect.width)
            text_rect = wx.Rect(rect.x + 3, rect.y, max(0, rect.width - width - 6), rect.height)
            dc.DrawLabel(table.GetValue(row, col), text_rect, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
            button = wx.Rect(rect.x + rect.width - width, rect.y, width, rect.height)
            wx.RendererNative.Get().DrawComboBoxDropButton(grid, dc, button, 0)
        finally:
            dc.DestroyClippingRegion()


class ColoredComboBox(adv.OwnerDrawnComboBox):
    def __init__(self, parent, id, labels, colors):
        self.item_colors = colors
        super().__init__(parent, id, choices=labels, style=wx.CB_READONLY)

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
        dc.DrawLabel(self.GetString(item), wx.Rect(rect.x + 3, rect.y, max(0, rect.width - 6), rect.height),
                     wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)

    def OnMeasureItem(self, item):
        return max(22, self.GetCharHeight() + 6)

    def OnMeasureItemWidth(self, item):
        if not 0 <= item < self.GetCount():
            return 100
        return self.GetTextExtent(self.GetString(item)).width + 12


class ColoredChoiceEditor(gridlib.GridCellEditor):
    """Index-based selection keeps equal display texts from selecting the wrong formula."""
    def __init__(self, labels, colors):
        super().__init__()
        self.labels, self.colors = list(labels), list(colors)
        self.initial = self.pending = wx.NOT_FOUND

    def Clone(self):
        return ColoredChoiceEditor(self.labels, self.colors)

    def Create(self, parent, id, evtHandler):
        self.combo = ColoredComboBox(parent, id, self.labels, self.colors)
        self.SetControl(self.combo)
        self.combo.Bind(wx.EVT_COMBOBOX, self.on_choice)
        if evtHandler:
            self.combo.PushEventHandler(evtHandler)

    def SetSize(self, rect):
        self.combo.SetSize(rect)

    def BeginEdit(self, row, col, grid):
        self.grid, self.row, self.col = grid, row, col
        selected = grid.GetTable().conflicts[row + 1, col + 1].selected
        self.initial = wx.NOT_FOUND if selected is None else selected
        self.combo.SetSelection(self.initial)
        self.combo.SetFocus()

    def on_choice(self, event):
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
        if self.pending != wx.NOT_FOUND and self.pending != self.initial:
            return self.labels[self.pending]
        return None

    def ApplyEdit(self, row, col, grid):
        grid.GetTable().conflicts[row + 1, col + 1].selected = self.pending
        grid.ForceRefresh()

    def Reset(self):
        self.combo.SetSelection(self.initial)

    def GetValue(self):
        return self.combo.GetValue()
