from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from pacs.manager.task_manager import TaskManager
from pacs.manager.validation_manager import ValidationManager
from pacs.utils import XDGType, get_xdg_dir, run_command

SCHEMA = "org.gnome.desktop.interface"


# ╭─────────────────────────────────────────────────────────────────────────────╮
# │ Helpers                                                                     │
# ╰─────────────────────────────────────────────────────────────────────────────╯
def list_dirs(p: Path) -> list[Path]:
    try:
        return list(p.iterdir())
    except (PermissionError, FileNotFoundError):
        return []


@lru_cache
def get_data_dirs() -> list[Path]:
    dirs: list[Path] = []

    def extend(value):
        if isinstance(value, list):
            dirs.extend(value)
        else:
            dirs.append(value)

    extend(get_xdg_dir(XDGType.DATA))
    extend(get_xdg_dir(XDGType.DATA_DIRS))

    seen = set()
    confirmed = []

    for d in dirs:
        if d.exists() and d not in seen:
            seen.add(d)
            confirmed.append(d)

    return confirmed


def get_icon_base_dirs() -> list[Path]:
    dirs = [d / "icons" for d in get_data_dirs()]
    dirs.append(Path.home() / ".icons")
    return [d for d in dirs if d.exists()]


# ╭─────────────────────────────────────────────────────────────────────────────╮
# │ Themes/Icons/Cursors                                                        │
# ╰─────────────────────────────────────────────────────────────────────────────╯
@lru_cache
def get_theme_names() -> list[str]:
    theme_dirs: list[Path] = []

    for d in get_data_dirs():
        td = d / "themes"
        if td.exists():
            theme_dirs.append(td)

    user_theme_dir = Path.home() / ".themes"
    if user_theme_dir.exists():
        theme_dirs.append(user_theme_dir)

    exclusions = {"Default", "Emacs"}
    names: set[str] = set()

    for base in theme_dirs:
        for theme_dir in list_dirs(base):
            if not theme_dir.is_dir():
                continue

            if any(
                sub.is_dir() and sub.name.startswith("gtk-")
                for sub in list_dirs(theme_dir)
            ):
                if theme_dir.name not in exclusions:
                    names.add(theme_dir.name)

    return sorted(names)


@lru_cache
def get_icon_themes(require_cursors: bool = False) -> list[str]:
    names = set()
    exclusions = {"default", "hicolor", "locolor"}

    for base in get_icon_base_dirs():
        for theme_dir in list_dirs(base):
            if not theme_dir.is_dir():
                continue

            if theme_dir.name.lower() in exclusions:
                continue

            if require_cursors and not (theme_dir / "cursors").exists():
                continue

            names.add(theme_dir.name)

    return sorted(names)


def get_icon_theme_names() -> list[str]:
    return get_icon_themes(False)


def get_cursor_themes() -> list[str]:
    return get_icon_themes(True)


# ╭─────────────────────────────────────────────────────────────────────────────╮
# │ Settings Class                                                              │
# ╰─────────────────────────────────────────────────────────────────────────────╯
@dataclass
class Setting:
    type_: type
    key: str
    valid_values: list | None = None
    valid_condition: Callable | None = None

    def validate(self, value) -> tuple[bool, str]:
        if not isinstance(value, self.type_):
            return False, f"Expected {self.type_.__name__}, got {type(value).__name__}"

        if self.valid_values is not None and value not in self.valid_values:
            return False, f"Value must be one of {self.valid_values}"

        if self.valid_condition is not None and not self.valid_condition(value):
            return False, "Custom validation condition failed"

        return True, " "


@lru_cache
def get_gsettings_definitions() -> dict[str, Setting]:
    return {
        "theme": Setting(str, "gtk-theme", valid_values=get_theme_names()),
        "icon-theme": Setting(str, "icon-theme", valid_values=get_icon_theme_names()),
        "cursor-theme": Setting(str, "cursor-theme", valid_values=get_cursor_themes()),
        "cursor-size": Setting(int, "cursor-size", valid_condition=lambda x: x > 0),
        "font": Setting(str, "font-name"),
        "colorscheme": Setting(
            str,
            "color-scheme",
            valid_values=["default", "prefer-dark", "prefer-light"],
        ),
        "antialiasing": Setting(
            str,
            "font-antialiasing",
            valid_values=["none", "grayscale", "rgba"],
        ),
        "hinting": Setting(
            str,
            "font-hinting",
            valid_values=["none", "slight", "medium", "full"],
        ),
        "rgba": Setting(
            str,
            "font-rgba-order",
            valid_values=["none", "rgb", "bgr", "vrgb", "vbgr"],
        ),
    }


# ╭─────────────────────────────────────────────────────────────────────────────╮
# │ GSettings Helpers                                                           │
# ╰─────────────────────────────────────────────────────────────────────────────╯
def get_valid_schemas() -> list[str]:
    success, result = run_command(["gsettings", "list-schemas"])
    if not success:
        raise RuntimeError("Valid schemas could not be determined.")
    return result["stdout"].splitlines()


def parse_gsettings_value(s: str):
    s = s.strip()

    if s in {"true", "false"}:
        return s == "true"

    if s.startswith("'") and s.endswith("'"):
        return s[1:-1]

    if s.isdigit():
        return int(s)

    try:
        return float(s)
    except ValueError:
        return s


def format_gsettings_value(value):
    if isinstance(value, str):
        return f"'{value}'"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def get_gsettings_value(schema: str, key: str):
    success, result = run_command(["gsettings", "get", schema, key])
    if success:
        return parse_gsettings_value(result["stdout"])
    return None


def apply_gsettings(schema: str, key: str, value):
    formatted = format_gsettings_value(value)
    success, _ = run_command(["gsettings", "set", schema, key, formatted])
    if not success:
        raise RuntimeError(f"Failed to set {key} in {schema}")


# ╭─────────────────────────────────────────────────────────────────────────────╮
# │ Core                                                                        │
# ╰─────────────────────────────────────────────────────────────────────────────╯
def handle_gtk(gtk_theme: dict, tm: TaskManager, vm: ValidationManager):
    if not vm.validate(
        SCHEMA in get_valid_schemas(),
        f'"{SCHEMA}" is not a valid gsettings schema.',
    ):
        return

    settings = get_gsettings_definitions()
    changes: dict[str, Any] = {}

    for key, new_value in gtk_theme.items():
        if key not in settings:
            vm.validate(False, f"Invalid GTK setting: {key}")
            continue

        setting = settings[key]

        valid, error = setting.validate(new_value)
        if not vm.validate(valid, error):
            continue

        current_value = get_gsettings_value(SCHEMA, setting.key)

        if current_value is None:
            continue

        if current_value != new_value:
            changes[key] = new_value

    settings = get_gsettings_definitions()

    for key, value in changes.items():
        tm.add_task(
            apply_gsettings,
            f'Change gtk {key} to "{value}".',
            SCHEMA,
            settings[key].key,
            value,
        )


def handle_theming(themes: dict, tm: TaskManager, vm: ValidationManager):
    for key, value in themes.items():
        if key == "gtk":
            handle_gtk(value, tm, vm)
        else:
            vm.validate(False, f"Invalid key {key} for themes.")
