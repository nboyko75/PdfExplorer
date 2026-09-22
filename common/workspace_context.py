"""Scope deferred callbacks and PDF edit buffers to their owning workspace."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps

_current = ContextVar('docexplorer_workspace', default=None)
_active = None
_fallback_pdf_sessions = {}


def set_active_workspace(workspace):
    global _active
    _active = workspace


def find_workspace(value):
    if hasattr(value, 'GetEventObject'):
        value = value.GetEventObject()
    while value is not None:
        if hasattr(value, '_pdf_session_bytes'):
            return value
        active = getattr(value, 'active_workspace', None)
        if active is not None:
            return active
        value = value.GetParent() if hasattr(value, 'GetParent') else None
    return None


@contextmanager
def workspace_scope(workspace):
    token = _current.set(workspace)
    try:
        yield
    finally:
        _current.reset(token)


def pdf_sessions():
    workspace = _current.get()
    if workspace is None:
        workspace = _active
    return workspace._pdf_session_bytes if workspace is not None else _fallback_pdf_sessions


def scoped_callback(function):
    @wraps(function)
    def call(*args, **kwargs):
        owner = kwargs.get('owner')
        if owner is None and args:
            owner = find_workspace(args[0])
        if owner is None:
            return function(*args, **kwargs)
        with workspace_scope(owner):
            return function(*args, **kwargs)
    return call


def scoped_workspace(cls):
    for name, member in list(vars(cls).items()):
        if callable(member) and not name.startswith('__'):
            setattr(cls, name, scoped_callback(member))
    return cls


def scope_owner_callbacks(namespace):
    """Preserve the owner even when an inactive tab receives a deferred event."""
    for name, function in list(namespace.items()):
        if getattr(function, '__module__', None) != namespace['__name__']:
            continue
        code = getattr(function, '__code__', None)
        if code and code.co_argcount and code.co_varnames[0] in ('owner', 'event'):
            namespace[name] = scoped_callback(function)
