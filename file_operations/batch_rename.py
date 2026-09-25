"""Preview and apply filename regex replacements without overwriting files."""
import fnmatch
import os
import re
from dataclasses import dataclass


class RenameError(ValueError):
    def __init__(self, key, detail=''):
        self.key, self.detail = key, detail
        super().__init__(detail)


@dataclass(frozen=True)
class RenameEntry:
    source: str
    target: str
    signature: tuple


def signature(path):
    st = os.stat(path, follow_symlinks=False)
    return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns


def valid_name(name):
    reserved = {'CON', 'PRN', 'AUX', 'NUL'} | {f'{p}{n}' for p in ('COM', 'LPT') for n in '123456789¹²³'}
    return (bool(name) and name not in ('.', '..') and not name.endswith((' ', '.'))
            and not any(ord(c) < 32 or c in '<>:"/\\|?*' for c in name)
            and name.split('.')[0].upper() not in reserved
            and len(name.encode('utf-16-le')) // 2 <= 255)


def validate(entries, check_files=True):
    targets = set()
    for entry in entries:
        name = os.path.basename(entry.target)
        if not valid_name(name):
            raise RenameError('rename_invalid_name', name)
        key = os.path.abspath(entry.target).casefold()
        if key in targets:
            raise RenameError('rename_conflict', entry.target)
        targets.add(key)
        # Conservative: also reject targets belonging to other pending sources.
        if not check_files:
            continue
        siblings = os.listdir(os.path.dirname(entry.target))
        if any(n.casefold() == name.casefold() and n != os.path.basename(entry.source) for n in siblings):
            raise RenameError('rename_conflict', entry.target)
        if signature(entry.source) != entry.signature:
            raise RenameError('rename_changed', entry.source)


def search(folder, recursive, pattern, replacement, mask="*"):
    if not os.path.isdir(folder):
        raise RenameError('search_no_folder')
    if not pattern:
        raise RenameError('rename_empty_pattern')
    regex = re.compile(pattern)
    # Validate replacement even when no filename matches.
    regex.sub(replacement, '')
    masks = [part.strip().casefold() for part in mask.split(";") if part.strip()] or ["*"]
    masks = ["*" if part == "*.*" else part for part in masks]
    entries = []
    def fail(error):
        raise error
    for root, dirs, files in os.walk(os.path.abspath(folder), onerror=fail, followlinks=False):
        dirs.sort(key=str.casefold)
        for name in sorted(files, key=str.casefold):
            if not any(fnmatch.fnmatchcase(name.casefold(), part) for part in masks):
                continue
            source = os.path.join(root, name)
            if os.path.islink(source) or not os.path.isfile(source) or not regex.search(name):
                continue
            target = os.path.join(root, regex.sub(replacement, name))
            entries.append(RenameEntry(source, target, signature(source)))
        if not recursive:
            break
    return entries


def apply(entries, on_error=None):
    """Apply a preview; on_error(entry, exception) returns retry/skip/skip_all/cancel."""
    validate(entries, check_files=on_error is None)
    count = 0
    skip_all = False
    for entry in entries:
        if entry.source == entry.target:
            continue
        while True:
            try:
                # Recheck on every retry; never overwrite an existing destination.
                validate([entry])
                os.rename(entry.source, entry.target)
                count += 1
                break
            except (OSError, RenameError) as exc:
                if on_error is None:
                    raise
                action = 'skip' if skip_all else on_error(entry, exc)
                if action == 'retry':
                    continue
                if action == 'skip_all':
                    skip_all = True
                elif action != 'skip':
                    return count
                break
    return count
