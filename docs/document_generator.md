# Word document generator

Select one `.doc`, `.docx` or `.docm` file, then choose **Create a document
generator** after **Merge similar documents** in the Document menu or context
menu. The paper-and-gear toolbar button runs the same command. Labels and
generator messages are translated into all supported application languages.

The command requires desktop Microsoft Word and pywin32. It opens the selected
file directly, in its original format, and shows a non-modal DocExplorer window.
The Add, Save and Exit buttons are aligned to the right below the status line.
The recessed status bar displays progress and messages. The info button at the
right of the column headers shows instructions as a tooltip or a click popup.
On first use, the form occupies the left half of the current screen's work area.
Its position and size are saved on closing and restored on the next opening.
Word is activated on the right half of the form's screen. You can select and edit text in Word while the
form stays open. Word's previous position, size and maximized state are restored
before its generator document is closed.

No `_generator.docm` copy or VBA form is created. VBA project access and macro
execution are not required. Source macros are disabled while opening the file;
the user's Word security settings are restored afterwards.

1. Select text in Word and click **Add**. A row appears with a bookmark name and
   the selected text as its initial value.
2. Edit the bookmark name or replacement value. Names begin with a letter and
   contain up to 40 ASCII letters, digits or underscores. Names must be unique.
   Fields are applied when leaving an editor or using a toolbar button.
   Rows are one line high by default. Check **Expand** on the right of a row to
   edit its value in a multiline textbox; uncheck it to collapse the row.
   Collapsing preserves line breaks, shown as `↵` in the compact preview. Editing
   that preview replaces the value with the single-line text you enter.
3. Click a row's **×** button to remove its bookmark and row, keeping the text.
4. Click **Save** and choose a separate output file. The source is saved with
   its bookmarks and generator fields; a copy is filled with the replacement
   values. Source text is not replaced. Both files retain the original format.
   Existing output files require confirmation.
5. Click **Exit** or close the form. If no output has been saved, or fields or
   the Word document have changed since saving, a Yes/No/Cancel prompt appears.
   Yes saves through the output dialog, No discards unsaved Word changes, and
   Cancel keeps the form open. Cancelling the output dialog or a failed save
   also keeps it open. A completed exit closes the form and its Word document.

Rows and values are stored in Word document variables, including in legacy
`.doc` files. Word's normal Save command persists applied fields. To reopen the
form, run the generator command again in DocExplorer. Other documents opened in
the same Word instance remain open when the generator exits.

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
  toolbar alignment at three window widths in every supported language.
