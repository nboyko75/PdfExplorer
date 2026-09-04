DEFAULT_SHORTCUTS_SASH = 120
MIN_SHORTCUTS_SASH = 40
MAX_SHORTCUTS_SASH = 400


def normalize_shortcuts_sash(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = DEFAULT_SHORTCUTS_SASH

    return max(MIN_SHORTCUTS_SASH, min(value, MAX_SHORTCUTS_SASH))
