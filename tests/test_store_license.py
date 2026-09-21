import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, Mock
import sys
import types
from common.store_license import classify, query_license, store_uri


class StoreLicenseTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 21, tzinfo=timezone.utc)

    def test_paid_license_does_not_depend_on_trial_expiration(self):
        self.assertEqual(classify(True, False, self.now-timedelta(days=1), self.now).state, 'paid')

    def test_active_trial(self):
        result = classify(True, True, self.now+timedelta(days=30), self.now)
        self.assertTrue(result.allowed)
        self.assertEqual(result.state, 'trial')

    def test_exact_expiration_blocks(self):
        self.assertFalse(classify(True, True, self.now, self.now).allowed)

    def test_inactive_license_blocks_even_with_future_expiration(self):
        self.assertFalse(classify(False, True, self.now+timedelta(days=30), self.now).allowed)
        self.assertFalse(classify(False, False, None, self.now).allowed)

    def test_invalid_expiration_fails_closed(self):
        self.assertEqual(classify(True, True, None, self.now).state, 'error')
        self.assertFalse(classify(True, True, datetime(2027, 1, 1), self.now).allowed)

    @patch('common.store_license.package_family_name', return_value=None)
    def test_unpacked_exe_does_not_import_winrt(self, _):
        self.assertEqual(query_license(0).state, 'unpackaged')

    @patch('common.store_license.package_family_name', side_effect=OSError('identity unavailable'))
    def test_identity_errors_do_not_grant_access(self, _):
        self.assertEqual(query_license(0).state, 'error')

    @patch('common.store_license.package_family_name', return_value='DocExplorer_123')
    def test_store_link_uses_real_package_identity(self, _):
        self.assertEqual(store_uri(), 'ms-windows-store://pdp/?PFN=DocExplorer_123')


class BridgeTests(unittest.TestCase):
    def test_packaged_query_initializes_window_and_releases_apartment(self):
        async def get_license():
            return types.SimpleNamespace(is_active=True, is_trial=False, expiration_date=None)
        context = types.SimpleNamespace(get_app_license_async=get_license)
        runtime = types.ModuleType('winrt.runtime')
        runtime.init_apartment = Mock()
        runtime.uninit_apartment = Mock()
        runtime.ApartmentType = types.SimpleNamespace(MULTI_THREADED=1)
        interop = types.ModuleType('winrt.runtime.interop')
        interop.initialize_with_window = Mock()
        store = types.ModuleType('winrt.windows.services.store')
        store.StoreContext = types.SimpleNamespace(get_default=lambda: context)
        with patch.dict(sys.modules, {'winrt.runtime': runtime,
                                     'winrt.runtime.interop': interop,
                                     'winrt.windows.services.store': store}), \
             patch('common.store_license.package_family_name', return_value='Package_123'):
            self.assertEqual(query_license(1234).state, 'paid')
        interop.initialize_with_window.assert_called_once_with(context, 1234)
        runtime.uninit_apartment.assert_called_once()


if __name__ == '__main__':
    unittest.main()
