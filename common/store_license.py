"""Microsoft Store licensing. No local trial counter and no EXE restrictions."""
import asyncio
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime, timezone
import math
import sys
from urllib.parse import quote


@dataclass(frozen=True)
class License:
    state: str
    expires: datetime = None
    detail: str = ''

    @property
    def allowed(self):
        return self.state in ('unpackaged', 'paid', 'trial')

    @property
    def days_left(self):
        if not self.expires:
            return 0
        return max(0, math.ceil((self.expires - datetime.now(timezone.utc)).total_seconds() / 86400))


def package_family_name():
    """Only APPMODEL_ERROR_NO_PACKAGE means unrestricted; errors fail closed."""
    if sys.platform != 'win32':
        return None
    get_name = ctypes.WinDLL('kernel32', use_last_error=True).GetCurrentPackageFamilyName
    get_name.argtypes = [ctypes.POINTER(wintypes.UINT), wintypes.LPWSTR]
    get_name.restype = wintypes.LONG
    length = wintypes.UINT()
    result = get_name(ctypes.byref(length), None)
    if result == 15700:  # APPMODEL_ERROR_NO_PACKAGE
        return None
    if result != 122:  # ERROR_INSUFFICIENT_BUFFER
        raise OSError(result, 'Cannot determine package identity')
    buffer = ctypes.create_unicode_buffer(length.value)
    result = get_name(ctypes.byref(length), buffer)
    if result:
        raise OSError(result, 'Cannot read package identity')
    return buffer.value


def classify(active, trial, expires, now=None):
    now = now or datetime.now(timezone.utc)
    if not active:
        return License('expired' if trial else 'unlicensed')
    if not trial:
        return License('paid')
    if expires is None or expires.tzinfo is None:
        return License('error', detail='Store returned an invalid expiration date')
    expires = expires.astimezone(timezone.utc)
    return License('trial' if expires > now else 'expired', expires)


def query_license(hwnd):
    """Run on a dedicated worker; never block the wx event loop."""
    try:
        if package_family_name() is None:
            return License('unpackaged')
        from winrt.runtime import init_apartment, uninit_apartment, ApartmentType
        init_apartment(ApartmentType.MULTI_THREADED)
        try:
            from winrt.windows.services.store import StoreContext
            from winrt.runtime.interop import initialize_with_window

            async def query():
                context = StoreContext.get_default()
                initialize_with_window(context, hwnd)
                license = await asyncio.wait_for(context.get_app_license_async(), timeout=25)
                return classify(license.is_active, license.is_trial, license.expiration_date)

            return asyncio.run(query())
        finally:
            uninit_apartment()
    except Exception as exc:
        return License('error', detail=str(exc))


def store_uri():
    family = package_family_name()
    if not family:
        raise RuntimeError('No package identity')
    return 'ms-windows-store://pdp/?PFN=' + quote(family, safe='')
