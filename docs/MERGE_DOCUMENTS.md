# Merge similar documents / Об’єднати схожі документи

Select one Excel workbook (.xlsx, .xlsm, .xls or .xlsb). Use the file-list
button, Document menu, or a tree/file-list context menu. Microsoft Excel
must be installed (as for the existing Office-based preview).

Search scans only sibling files, without subfolders. Matching is local and
uses text-token cosine similarity plus same-cell agreement (threshold 0.45).
It does not call a cloud AI service or a semantic language model. Filenames
are not used as similarity evidence. Search skips unreadable files and reports
them; all found files are checked initially.

Compare matches worksheets by exact name and cells by row/column address.
It does not align reordered rows, renamed sheets, or shifted columns. Sheets
without matching names are reported, not silently imported. Only target
worksheets are modified. All worksheets, including hidden ones, participate.

The Preview tab uses Excel HTML export. Worksheet tabs show a cell grid for
review. Click a highlighted cell to open its choices, which include all unique
values and their source filenames. The original value rejects the change.
One distinct alternative is selected automatically; several alternatives
require a choice. Empty values are explicit choices and can clear a cell.
Changing checked files invalidates the comparison and requires Compare again.

Save is available only after comparison and when every conflict has a choice.
Changes are applied to a temporary copy through Excel, retaining the workbook
format. The original is replaced only after successful saving; its previous
bytes are retained in a uniquely named .merge-backup file alongside it.
Cancel never writes the target; during I/O it waits for the current operation
before closing. Macros/events and link updates are disabled in owned Excel
sessions. Existing user Excel sessions are not closed. Changes to protected,
array-formula, non-anchor merged cells and imported external workbook formulas
are rejected. The review limit is 200,000 used-range cells per workbook;
over-limit books are reported instead of silently truncated.

Before saving, the target fingerprint must still match the searched snapshot.
If files change before comparison, run Search again. A locked target or failed
save leaves the original intact. Backup files are never overwritten.

# Windows smoke check

1. Make copies of small Excel files with two matching worksheet names.
2. Change the same cell to one alternative in one copy; expect auto-selection.
3. Add a different alternative in another copy; expect an unresolved choice.
4. Verify all four entry points, checkbox invalidation, HTML preview, sheet
   tabs, source labels, choosing the original, and Save gating.
5. Cancel and compare the original file bytes; they must be unchanged.
6. Save and check both sheets, workbook format, styles, formulas and backup.
7. Repeat with a locked workbook, a protected sheet, macro-enabled workbook,
   and a changed source file. Verify errors and preservation of originals.

The merge core and packaging integration were checked headlessly. Windows,
Excel COM, WebView2 and native wx grid rendering require a Windows smoke test.
