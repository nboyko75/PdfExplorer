import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from file_operations.batch_rename import search, apply, validate, RenameError, valid_name


class BatchRenameTests(unittest.TestCase):
    def test_recursive_preview_and_capture_replacement(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'old_12.txt').write_text('first')
            (root / 'child').mkdir()
            (root / 'child' / 'old_34.txt').write_text('second')
            plan = search(folder, False, r'old_(\d+)', r'new_\1')
            self.assertEqual(len(plan), 1)
            self.assertTrue((root / 'old_12.txt').exists())
            plan = search(folder, True, r'old_(\d+)', r'new_\1')
            self.assertEqual(apply(plan), 2)
            self.assertEqual((root / 'new_12.txt').read_text(), 'first')
            self.assertEqual((root / 'child' / 'new_34.txt').read_text(), 'second')

    def test_blocked_file_choices(self):
        import os
        for action in ('retry', 'skip', 'skip_all', 'cancel'):
            with self.subTest(action=action), tempfile.TemporaryDirectory() as folder:
                for name in ('a.txt', 'b.txt', 'c.txt'):
                    Path(folder, name).write_text(name)
                plan = search(folder, False, r'^(.)', r'new_\1')
                real_rename = os.rename
                attempts, prompts = [], []
                def rename(source, target):
                    attempts.append(source)
                    if Path(source).name in ('a.txt', 'b.txt'):
                        if action != 'retry' or attempts.count(source) == 1:
                            raise PermissionError('File is in use')
                    real_rename(source, target)
                def choose(entry, error):
                    prompts.append(entry.source)
                    return action
                with patch('file_operations.batch_rename.os.rename', side_effect=rename):
                    count = apply(plan, on_error=choose)
                self.assertEqual(count, {'retry': 3, 'skip': 1, 'skip_all': 1, 'cancel': 0}[action])
                self.assertEqual(len(prompts), 1 if action in ('skip_all', 'cancel') else 2)
                if action == 'cancel':
                    self.assertEqual(len(attempts), 1)

    def test_file_masks(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ('old.PDF', 'old.xlsx', 'old.txt', 'old'):
                Path(folder, name).write_text('data')
            names = lambda mask: {Path(e.source).name for e in search(folder, False, '^old', 'new', mask)}
            self.assertEqual(names('*.pdf; *.xlsx'), {'old.PDF', 'old.xlsx'})
            self.assertEqual(len(names('*.*')), 4)
            self.assertEqual(len(names('')), 4)

    def test_collision_does_not_modify_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ('a.txt', 'b.txt'):
                Path(folder, name).write_text(name)
            plan = search(folder, False, r'^[ab]', 'same')
            with self.assertRaises(RenameError):
                apply(plan)
            self.assertEqual(Path(folder, 'a.txt').read_text(), 'a.txt')
            plan = search(folder, False, '^a', 'b')
            with self.assertRaises(RenameError):
                apply(plan)

    def test_stale_preview_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder, 'a.txt')
            source.write_text('old')
            plan = search(folder, False, '^a', 'b')
            source.write_text('changed content')
            with self.assertRaises(RenameError):
                apply(plan)
            self.assertFalse(Path(folder, 'b.txt').exists())

    def test_invalid_names_and_empty_pattern(self):
        for name in ('', '..', '../x', 'a/b', 'a\\b', 'CON.txt', 'LPT1', 'a.', 'a ', 'a:b'):
            self.assertFalse(valid_name(name), name)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(RenameError):
                search(folder, False, '', 'x')

    def test_case_change_and_unchanged_match(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, 'a.txt').write_text('data')
            self.assertEqual(apply(search(folder, False, '^a', 'a')), 0)
            self.assertEqual(apply(search(folder, False, '^a', 'A')), 1)
            self.assertEqual(Path(folder, 'A.txt').read_text(), 'data')


if __name__ == '__main__':
    unittest.main()
