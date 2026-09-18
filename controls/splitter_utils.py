from common.consts import DEFAULT_SHORTCUTS_SASH, MAX_SHORTCUTS_SASH, MIN_SHORTCUTS_SASH


def normalize_shortcuts_sash(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = DEFAULT_SHORTCUTS_SASH

    return max(MIN_SHORTCUTS_SASH, min(value, MAX_SHORTCUTS_SASH))
