# Word document generator

Select one `.doc`, `.docx` or `.docm` file, then choose **Create a document
generator** after **Merge similar documents** in the Document menu or context
menu. The paper-and-gear toolbar button runs the same command. Labels and
generator messages are translated into all supported application languages.

The command requires desktop Microsoft Word and pywin32. It opens the selected
file directly, in its original format, and shows a non-modal DocExplorer window.
Before creating the generator or launching Word, the document generator module
checks that the file exists and can be opened for editing without a sharing
lock. If unavailable, a topmost **Retry / Cancel** dialog appears. **Retry**
checks availability again; **Cancel** stops without opening Word. Availability
is checked again immediately before Word starts. Opening failures also offer
Retry / Cancel, and failed Word sessions are released before another attempt.
If Word disconnects while the form is open, technical COM errors are logged
instead of shown in a popup. A short status message asks you to reopen the
generator. Entered values remain visible for copying; Word actions are disabled
and Exit closes the form without repeating the connection error.
The form has a **Bookmark values** panel above a **Table values** panel. Each
panel has a title and info button with a tooltip and click popup. **Add value**
is at the bottom right of the bookmark panel. **Add row** and **Add table** are
at the bottom left and right of the table panel. Drag the recessed horizontal splitter
to resize the panels; its position is saved and restored with the form geometry.
The Save, Export and Exit buttons are aligned to the right below the recessed
status bar, which displays progress and messages.
On first use, the form occupies the left half of the current screen's work area.
Its position and size are saved on closing and restored on the next opening.
Word's position and size are also remembered independently. On first use, Word
opens on the right half of the form's screen; subsequent sessions restore its
last normal bounds. Minimizing or maximizing Word keeps the remembered normal
bounds. A saved location on a disconnected monitor falls back to the right half
of the form's screen. You can select and edit text in Word while the
form stays open. Word's previous position, size and maximized state are restored
before its generator document is closed.

No `_generator.docm` copy or VBA form is created. VBA project access and macro
execution are not required. Source macros are disabled while opening the file;
the user's Word security settings are restored afterwards.

1. Select text in Word and click **Add value**. A row appears with a bookmark name and
   the selected text as its initial value.
2. Edit the bookmark name or replacement value. Names begin with a letter and
   contain up to 40 ASCII letters, digits or underscores. Names must be unique.
   Fields are applied when leaving an editor or using a toolbar button.
   Rows are one line high by default. Check **Expand** on the right of a row to
   edit its value in a multiline textbox; uncheck it to collapse the row.
   Collapsing preserves line breaks, shown as `↵` in the compact preview. Editing
   that preview replaces the value with the single-line text you enter.
3. Click a row's **×** button to remove its bookmark and row, keeping the text.
4. Click **Save** to save the bookmarks and generator fields in the current Word
   document and apply table edits described below. This does not open a file
   dialog or replace the source text of individual bookmark values.
5. Click **Export** (after Save in the toolbar) and choose a separate output file.
   The source is saved with its bookmarks and generator fields; a copy is filled
   with the replacement values. Both files retain the original format.
   Existing output files require confirmation.
6. Click **Exit** or close the form. If the generator has not been saved, or fields or
   the Word document have changed since saving, a Yes/No/Cancel prompt appears.
   Yes saves the current Word document directly, No discards unsaved Word changes,
   and Cancel keeps the form open. A failed save also keeps it open. A completed
   exit closes the form and its Word document. Cancelling an export leaves the
   generator open without creating an output file.

Rows and values are stored in Word document variables, including in legacy
`.doc` files. Word's normal Save command persists applied fields. To reopen the
form, run the generator command again in DocExplorer. Other documents opened in
the same Word instance remain open when the generator exits.

To edit repeating table rows:

1. Select a whole row in Word and click **Add table**. If several rows are
   selected, the last selected row becomes the template. The lower panel adds
   an editable grid with that row's values and relative cell widths, and a
   table bookmark name above it. No Word rows are inserted until Save or Export.
2. Edit the cells and bookmark name. Names must be unique across both panels.
   Click a table's name or cell to select it, then use **Add row** to append a
   blank row to that grid. Multiple editable tables are supported.
3. **Save** updates the selected Word row with the first grid row and inserts
   additional rows immediately below it. Rows above and below the managed block
   are preserved. Added rows retain the selected row's formatting and widths.
   Repeated saves update the same block instead of appending duplicates.
4. **Export** also applies the table edits before creating the filled result.
   Table values and bookmarks survive saving and reopening the source. The
   result omits generator metadata. The table's **×** button removes its editor
   and bookmark while keeping its Word rows.

Tables may contain horizontal or vertical merges and different cell counts in
different rows. The editor shows the cells belonging to the selected template
row; a vertically merged cell that starts in an earlier row remains shared in
Word. Added rows copy the template's merged layout and formatting. Nested tables
are not supported. Turn off Track Changes and resolve tracked changes in the affected
table before saving. If the managed rows are removed or structurally changed
in Word, remove their editor and add the row again. Table regions cannot overlap
other generator bookmarks. Failed structural edits are rolled back as a single
Word undo record before reporting the error.

Overlapping generator selections and selections spanning table-cell boundaries
are rejected. Text within an individual cell can be bookmarked. If editing the
document removes a managed bookmark, delete its row and add the selection again.
Read-only and protected documents must be made editable before use.

Generated files retain filled bookmarks but omit the generator field data.
Existing macros in an input `.docm` remain part of that format; the generator
never injects VBA.

Validation:

- `python -m unittest discover -s tests -p test_document_generator.py -v`
  checks command routing, translations, validation, ownership and worker isolation.
- `python tests/document_generator_probe.py` exercises installed Word using
  synthetic `.doc`, `.docx` and `.docm` files, including field persistence,
  formatting, adjacent bookmarks, Unicode and repeated exports.
- `python tests/document_generator_ui_probe.py` checks the native form and
  panels at three window widths in every supported language, including active
  cell edits, saved splitter position and retrying/cancelling failed opens.
- `python tests/document_generator_open_probe.py --word` checks real file locks,
  missing/read-only files, the topmost Retry/Cancel dialog, and documents open in
  Word. Omitting `--word` runs the file and dialog checks without Office.
- `python tests/document_generator_tables_probe.py` checks actual Word table
  selection, cell formatting, insertion, metadata, rollback, repeated saves,
  reopening and exporting for all three supported formats, including merged
  headers, horizontal and vertical template merges, and shrinking managed rows.

Implementation references: [Word Range.FormattedText](https://learn.microsoft.com/en-us/office/vba/api/word.range.formattedtext)
and [Word custom undo records](https://learn.microsoft.com/en-us/office/vba/api/word.undorecord.startcustomrecord).
