import json
import os
import sys


def _get_project_root_dir():
    # In frozen builds (e.g. PyInstaller), persist settings next to the executable.
    if getattr(sys, "frozen", False):
        executable_path = os.path.abspath(getattr(sys, "executable", ""))
        executable_dir = os.path.dirname(executable_path)
        if executable_dir:
            return executable_dir

    current_file = os.path.abspath(__file__)
    current_dir = os.path.dirname(current_file)
    if os.path.basename(current_dir) == "controls":
        return os.path.dirname(current_dir)
    return current_dir


def _get_settings_file_path():
    return os.path.join(_get_project_root_dir(), ".pdf_explorer_settings.json")


def load_settings():
    settings_file = _get_settings_file_path()
    try:
        if os.path.isfile(settings_file):
            with open(settings_file, "r", encoding="utf-8") as handle:
                return json.load(handle)
    except Exception:
        pass
    return {}


def save_settings(settings):
    settings_file = _get_settings_file_path()
    try:
        os.makedirs(os.path.dirname(settings_file), exist_ok=True)
        with open(settings_file, "w", encoding="utf-8") as handle:
            json.dump(settings, handle)
    except Exception:
        pass


def update_settings(new_values):
    settings = load_settings()
    settings.update(new_values)
    save_settings(settings)


def save_window_geometry(frame):
    if frame.IsIconized():
        return

    position = frame.GetPosition()
    size = frame.GetSize()
    update_settings(
        {
            "window_position": [int(position.x), int(position.y)],
            "window_size": [int(size.x), int(size.y)],
        }
    )


def restore_window_geometry(frame, settings=None):
    if settings is None:
        settings = load_settings()

    position = settings.get("window_position")
    size = settings.get("window_size")

    if isinstance(size, list) and len(size) == 2:
        width, height = int(size[0]), int(size[1])
        if width > 100 and height > 100:
            frame.SetSize((width, height))

    if isinstance(position, list) and len(position) == 2:
        x, y = int(position[0]), int(position[1])
        frame.SetPosition((x, y))
