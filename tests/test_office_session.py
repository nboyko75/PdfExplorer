import unittest
from unittest.mock import MagicMock
from file_operations.office_session import preview_document


class OfficeSessionTests(unittest.TestCase):
    def test_export_failure_closes_document_and_balances_com(self):
        for kind, collection in (("Word", "Documents"), ("Excel", "Workbooks"), ("PowerPoint", "Presentations")):
            with self.subTest(kind=kind):
                client, com = MagicMock(), MagicMock()
                app = client.DispatchEx.return_value
                document = getattr(app, collection).Open.return_value
                with self.assertRaisesRegex(RuntimeError, "export failed"):
                    with preview_document(client, com, kind, "source"):
                        raise RuntimeError("export failed")
                document.Close.assert_called_once_with(*(() if kind == "PowerPoint" else (False,)))
                app.Quit.assert_called_once()
                com.CoInitialize.assert_called_once()
                com.CoUninitialize.assert_called_once()
                if kind == "PowerPoint":
                    self.assertNotIn("Visible", vars(app))

    def test_open_failure_still_quits(self):
        client, com = MagicMock(), MagicMock()
        app = client.DispatchEx.return_value
        app.Documents.Open.side_effect = RuntimeError("open failed")
        with self.assertRaisesRegex(RuntimeError, "open failed"):
            with preview_document(client, com, "Word", "source"):
                self.fail("Should not enter")
        app.Quit.assert_called_once()
        com.CoUninitialize.assert_called_once()

    def test_close_failure_does_not_mask_export_failure(self):
        client, com = MagicMock(), MagicMock()
        app = client.DispatchEx.return_value
        app.Workbooks.Open.return_value.Close.side_effect = RuntimeError("close failed")
        with self.assertRaisesRegex(ValueError, "original"):
            with preview_document(client, com, "Excel", "source"):
                raise ValueError("original")
        app.Quit.assert_called_once()
        com.CoUninitialize.assert_called_once()

    def test_initialization_failure_does_not_uninitialize(self):
        client, com = MagicMock(), MagicMock()
        com.CoInitialize.side_effect = RuntimeError("init failed")
        with self.assertRaisesRegex(RuntimeError, "init failed"):
            with preview_document(client, com, "Word", "source"):
                self.fail("Should not enter")
        client.DispatchEx.assert_not_called()
        com.CoUninitialize.assert_not_called()
