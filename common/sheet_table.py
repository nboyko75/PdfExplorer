"""Excel cell table used by workbook review grids."""
import wx
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
    return tr('merge_empty') if cell.value is None else str(cell.value)


class SheetTable(gridlib.GridTableBase):
    def __init__(self, sheet, conflicts, difference_positions=None):
        super().__init__()
        self.sheet, self.conflicts = sheet, conflicts
        self.difference_positions = difference_positions
        self.labels = {}
        self.rows = max([sheet.rows] + [r for r, c in conflicts])
        self.cols = max([sheet.cols] + [c for r, c in conflicts])
        for pos, conflict in conflicts.items():
            labels = []
            for index, (value, sources) in enumerate(zip(conflict.values, conflict.sources)):
                prefix = tr('merge_keep') + ': ' if index == 0 else ''
                labels.append(f'{index + 1}. {prefix}{display(value)} [{", ".join(sources)}]')
            self.labels[pos] = labels

    def GetNumberRows(self):
        return self.rows

    def GetNumberCols(self):
        return self.cols

    def GetColLabelValue(self, col):
        return column_name(col + 1)

    def GetValue(self, row, col):
        pos = row + 1, col + 1
        if pos[0] in self.sheet.hidden_rows:
            return ""
        if self.difference_positions is not None and pos not in self.difference_positions:
            return ""
        conflict = self.conflicts.get(pos)
        if conflict:
            return self.labels[pos][conflict.selected] if conflict.selected is not None else tr('merge_choose')
        cell = self.sheet.cells.get(pos, engine.EMPTY)
        return '' if cell.value is None else str(cell.value)

    def SetValue(self, row, col, value):
        pos = row + 1, col + 1
        if pos in self.conflicts and value in self.labels[pos]:
            self.conflicts[pos].selected = self.labels[pos].index(value)

    def GetAttr(self, row, col, kind):
        pos = row + 1, col + 1
        attr = gridlib.GridCellAttr()
        if pos in self.conflicts:
            conflict = self.conflicts[pos]
            attr.SetEditor(gridlib.GridCellChoiceEditor(self.labels[pos], allowOthers=False))
            attr.SetBackgroundColour(wx.Colour(255, 233, 175) if conflict.selected is None else wx.Colour(221, 242, 220))
        else:
            attr.SetReadOnly(True)
        return attr


