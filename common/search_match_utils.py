import os
import re
from datetime import datetime


def _matches_text_query(content, query, case_sensitive=True, whole_word=False):
    if not isinstance(content, str) or not query:
        return False
    if whole_word:
        flags = 0 if case_sensitive else re.IGNORECASE
        pattern = re.compile(rf"(?<!\w){re.escape(query)}(?!\w)", flags)
        return bool(pattern.search(content))
    if case_sensitive:
        return query in content
    return query.lower() in content.lower()


def _parse_size_kb(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", ".")
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _matches_date_filter(file_path, date_mode=0, date_from=None, date_to=None):
    if date_mode != 1:
        return True
    date_from_value = _parse_date_value(date_from)
    date_to_value = _parse_date_value(date_to)
    if date_from_value is None and date_to_value is None:
        return True
    try:
        modified_date = datetime.fromtimestamp(os.path.getmtime(file_path)).date()
    except OSError:
        return True
    if date_from_value is not None and modified_date < date_from_value:
        return False
    if date_to_value is not None and modified_date > date_to_value:
        return False
    return True


def _matches_size_filter(file_path, size_mode=0, size_from=None, size_to=None):
    if size_mode != 1:
        return True
    size_from_kb = _parse_size_kb(size_from)
    size_to_kb = _parse_size_kb(size_to)
    if size_from_kb is None and size_to_kb is None:
        return True
    try:
        size_kb = os.path.getsize(file_path) / 1024.0
    except OSError:
        return True
    if size_from_kb is not None and size_kb < size_from_kb:
        return False
    if size_to_kb is not None and size_kb > size_to_kb:
        return False
    return True


def _parse_date_value(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.fromisoformat(value).date()
    except (TypeError, ValueError):
        try:
            return datetime.strptime(value, "%d.%m.%Y").date()
        except (TypeError, ValueError):
            return None
