"""Headless regression tests using real PDFs and a simulated shell handoff."""
import ast
import os
from pathlib import Path
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import fitz

ROOT = Path(__file__).resolve().parents[1]
source = ast.parse((ROOT / 'controls/print_form.py').read_text())
functions = {'_get_print_temp_directory', '_create_print_subset', '_print_with_selected_printer'}
nodes = [node for node in source.body if isinstance(node, ast.FunctionDef) and node.name in functions]


class PrintTempLifetimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / 'original.pdf'
        with fitz.open() as doc:
            for text in ('Page one', 'Page two', 'Page three'):
                doc.new_page().insert_text((72, 72), text)
            doc.save(self.source)
        self.original_bytes = self.source.read_bytes()
        self.printer = Mock()
        self.printer.GetDefaultPrinter.return_value = 'Original printer'
        self.launched = []
        self.env = {
            'os': os, 'tempfile': tempfile, 'time': time, 'fitz': fitz,
            '_PRINT_TEMP_MAX_AGE_SECONDS': 7 * 24 * 3600,
            'win32print': self.printer, 'win32api': object(), 'tr': lambda key: key,
            'office_preview': SimpleNamespace(can_preview_office=lambda path: False),
        }
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'print_form.py', 'exec'), self.env)
        self.addCleanup(patch.stopall)
        patch.object(tempfile, 'gettempdir', return_value=self.temp.name).start()
        patch.object(os, 'startfile', side_effect=lambda path, verb: self.launched.append((path, verb)), create=True).start()

    def test_viewer_can_open_subset_after_print_call_returns(self):
        self.env['_print_with_selected_printer'](str(self.source), 'Test printer', page_numbers=[2, 0])
        path, verb = self.launched[0]
        self.assertEqual(verb, 'print')
        self.assertTrue(Path(path).is_file())
        # Read only AFTER the handoff function has returned (the original bug).
        with fitz.open(path) as doc:
            self.assertEqual(doc.page_count, 2)
            self.assertIn('Page three', doc[0].get_text())
            self.assertIn('Page one', doc[1].get_text())
        self.assertEqual(self.source.read_bytes(), self.original_bytes)
        self.printer.SetDefaultPrinter.assert_called_with('Original printer')

    def test_cleanup_only_removes_old_owned_print_files(self):
        folder = Path(self.env['_get_print_temp_directory']())
        old = folder / 'pdfexplorer_print_old.pdf'
        recent = folder / 'pdfexplorer_print_recent.pdf'
        unrelated = folder / 'user_document.pdf'
        for p in (old, recent, unrelated):
            p.write_bytes(b'content')
        past = time.time() - 8 * 24 * 3600
        for p in (old, unrelated):
            os.utime(p, (past, past))
        self.env['_get_print_temp_directory']()
        self.assertFalse(old.exists())
        self.assertTrue(recent.exists())
        self.assertTrue(unrelated.exists())

    def test_all_pages_print_does_not_remove_source(self):
        self.env['_print_with_selected_printer'](str(self.source), 'Test printer')
        self.assertEqual(self.launched, [(str(self.source), 'print')])
        self.assertEqual(self.source.read_bytes(), self.original_bytes)

    def test_failed_subset_creation_cleans_incomplete_file(self):
        with self.assertRaises(Exception):
            self.env['_create_print_subset'](str(self.source), [])
        folder = Path(self.env['_get_print_temp_directory']())
        self.assertEqual(list(folder.glob('pdfexplorer_print_*.pdf')), [])
        self.assertEqual(self.launched, [])


if __name__ == '__main__':
    unittest.main()
