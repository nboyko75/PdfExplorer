"""Align added table/worksheet axes without deleting original rows or columns."""
from difflib import SequenceMatcher


def align_axis(left, right, left_axis, right_axis, dimension):
    # Ignore newly introduced/edited cell values when finding unchanged anchors.
    common = set(left.values()) & set(right.values())
    def signatures(cells, axis):
        lines = {number: [] for number in axis}
        for position, value in sorted(cells.items()):
            if position[dimension] in lines and value in common:
                lines[position[dimension]].append(value)
        return [tuple(lines[number]) for number in axis]
    matcher = SequenceMatcher(None, signatures(left, left_axis),
                              signatures(right, right_axis), autojunk=False)
    old, new, count = {}, {}, 0
    for tag, i, j, k, l in matcher.get_opcodes():
        # Equal-sized edited blocks retain their positions. Extra source axes
        # are inserted; axes absent from a source remain in the original.
        for offset in range(max(j - i, l - k)):
            count += 1
            if i + offset < j:
                old[left_axis[i + offset]] = count
            if k + offset < l:
                new[right_axis[k + offset]] = count
    return old, new, count


def align_grids(grids, axes):
    """Return source-to-union row/column maps, including the original at index 0.

    Grids contain hashable cell values; axes contain their actual row/column
    numbers. Identical additions from several sources occupy the same slots.
    """
    rows, cols = axes[0]
    maps = [({r: r for r in rows}, {c: c for c in cols})]
    merged = dict(grids[0])
    for grid, (source_rows, source_cols) in zip(grids[1:], axes[1:]):
        old_rows, new_rows, row_count = align_axis(merged, grid, rows, source_rows, 0)
        old_cols, new_cols, col_count = align_axis(merged, grid, cols, source_cols, 1)
        merged = {(old_rows[r], old_cols[c]): value for (r, c), value in merged.items()}
        for (r, c), value in grid.items():
            merged.setdefault((new_rows[r], new_cols[c]), value)
        maps = [({r: old_rows[target] for r, target in rm.items()},
                 {c: old_cols[target] for c, target in cm.items()}) for rm, cm in maps]
        maps.append((new_rows, new_cols))
        rows, cols = list(range(1, row_count + 1)), list(range(1, col_count + 1))
    return maps, (len(rows), len(cols))


def added_axes(mapping, count):
    return sorted(set(range(1, count + 1)) - set(mapping.values()))
