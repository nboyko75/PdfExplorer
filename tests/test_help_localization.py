"""Verify localized resource routing without wxPython or a Windows GUI."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load_help():
    spec = importlib.util.spec_from_file_location('help_under_test', ROOT / 'controls/help_form.py')
    module = importlib.util.module_from_spec(spec)
    constants = types.SimpleNamespace(HELP_RELATIVE_PATH='docs/help/index.html',
                                     MANUAL_RELATIVE_PATH='docs/DocExplorer_User_Manual.pdf')
    with mock.patch.dict(sys.modules, {'wx': mock.MagicMock(), 'common.consts': constants,
                                     'localization': types.SimpleNamespace(tr=lambda key, **kwargs: key)}):
        spec.loader.exec_module(module)
    return module


class HelpLocalizationTests(unittest.TestCase):
    def test_every_language_has_html_and_pdf(self):
        help_module = load_help()
        for code in help_module.SUPPORTED_HELP_LOCALES:
            for relative in (help_module.HELP_RELATIVE_PATH, help_module.MANUAL_RELATIVE_PATH):
                path = Path(help_module._localized_resource_path(relative, code))
                self.assertTrue(path.is_file())
                self.assertTrue(path.stem.endswith('_' + code))

    def test_alias_and_unknown_language(self):
        help_module = load_help()
        for code, expected in [('pt-BR','pt_br'), ('zh-CN','zh_cn'), ('en-US','en'), ('unknown','en'), ('../../bad','en')]:
            path = Path(help_module._localized_resource_path(help_module.HELP_RELATIVE_PATH, code))
            self.assertEqual(path.name, 'index_' + expected + '.html')

    def test_packaged_and_english_fallback(self):
        help_module = load_help()
        with tempfile.TemporaryDirectory() as directory:
            docs = Path(directory) / 'docs/help'; docs.mkdir(parents=True)
            english = docs / 'index_en.html'; english.write_text('English')
            with mock.patch.object(sys, '_MEIPASS', directory, create=True):
                self.assertEqual(Path(help_module._localized_resource_path(help_module.HELP_RELATIVE_PATH, 'uk')), english)
                english.unlink()
                legacy = docs / 'index.html'; legacy.write_text('Legacy')
                self.assertEqual(Path(help_module._localized_resource_path(help_module.HELP_RELATIVE_PATH, 'uk')), legacy)

if __name__ == '__main__':
    unittest.main()
