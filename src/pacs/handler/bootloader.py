import re
import tempfile
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm
from rich.syntax import Syntax

import pacs.common_vars as common_vars
from pacs.manager.task_manager import TaskManager
from pacs.manager.validation_manager import ValidationManager
from pacs.utils import run_command

all_installed_packages = common_vars.local_installed_package

console = Console()


def parse_grub_file(path: Path) -> list:
    entries = []

    for line in path.read_text().splitlines():
        stripped = line.strip()

        if not stripped or "=" not in stripped:
            entries.append({"type": "raw", "lines": line})
            continue

        key, value = map(str.strip, stripped.split("=", 1))

        commented = False
        if key.startswith("#"):
            key = key[1:].lstrip()
            commented = True

        entries.append(
            {
                "type": "entry",
                "key": key,
                "value": value,
                "commented": commented,
            }
        )

    return entries


def validate_resolution(value: str) -> bool:
    MODE_PATTERN = re.compile(r"^(auto|\d+x\d+(x\d+)?)$")
    if not value:
        return False

    # split by , or ;
    modes = re.split(r"[;,]", value)

    for mode in modes:
        mode = mode.strip()

        if not MODE_PATTERN.fullmatch(mode):
            return False

    return True


def render(entries: list, vm: ValidationManager) -> tuple[str, str]:
    full_lines: list[str] = []
    active_lines: list[str] = []

    for entry in entries:
        if entry["type"] == "raw":
            full_lines.append(entry["lines"])
            continue

        prefix = "#" if entry["commented"] else ""
        line = f"{prefix}{entry['key']}={entry['value']}"
        full_lines.append(line)

        if not entry["commented"]:
            active_lines.append(f"{entry['key']}={entry['value']}")

    return "\n".join(full_lines), "\n".join(active_lines)


# https://www.gnu.org/software/grub/manual/grub/html_node/Simple-configuration.html
def validate_grub_config(grub_config: dict, vm: ValidationManager):
    for key, value in grub_config.items():
        if key == "GRUB_DEFAULT":
            # value must either be integer of "saved"
            if value.isdigit():
                continue

            vm.validate(
                value == "saved",
                f'{key} has an invalid value: "{value}".\nValid value is integer or "saved"',
            )
        elif key == "GRUB_SAVEDEFAULT":
            vm.validate(
                value in ["true", "false"],
                f'{key} has an invalid value: "{value}".\nValid value is "true" or "false"',
            )
        elif key == "GRUB_TIMEOUT":
            vm.validate(
                value.isdigit() or value == "-1",
                f'{key} has an invalid value: "{value}".\nValid value is positive integer of "-1".',
            )
        elif key == "GRUB_TIMEOUT_STYLE":
            vm.validate(
                value in ["menu", "countdown", "hidden"],
                f'{key} has an invalid value: "{value}".\nValid value is "menu", "countdown" or "hidden".',
            )
        elif key == "‘GRUB_GFXMODE’":
            vm.validate(
                validate_resolution(value),
                f'{key} has an invalid value: "{value}".\nValid value is "auto", "widthxheight", or "widthxheightxdepth".',
            )
        elif key == "GRUB_THEME":
            if value[:1] == value[-1:] and value.startswith(("'", '"')):
                value = value[1:-1]
            value = Path(value)
            vm.validate(
                value.exists() and value.is_file(),
                f'{key} has an invalid value: "{value}".\nThis path is not pointing to a valid file.',
            )
        elif key == "GRUB_DISABLE_OS_PROBER":
            vm.validate(
                "os-prober" in all_installed_packages,
                "Config has enabled usage of os-prober but it has not been installed.\nAdd os-prober package to config.",
            )
            vm.validate(
                value in ["true", "false"],
                f'{key} has an invalid value: "{value}".\nValid value is "true" or "false"',
            )


def update_grub_file(content: str):
    with tempfile.NamedTemporaryFile(
        mode="w", delete=False, prefix="grub_", suffix=".tmp"
    ) as tmp:
        tmp.write(content)
        temp_path = Path(tmp.name)

    # Create backup
    success, _ = run_command(
        ["sudo", "cp", "/etc/default/grub", "/etc/default/grub.bak"]
    )
    if not success:
        raise RuntimeError("Failed to create backup of grub config.")

    success, _ = run_command(["sudo", "mv", str(temp_path), "/etc/default/grub"])
    if not success:
        raise RuntimeError("Failed to update grub config.")

    success, _ = run_command(
        ["sudo", "grub-mkconfig", "-o", "/boot/grub/grub.cfg"], capture_output=False
    )
    if not success:
        raise RuntimeError("Failed to generate grub config using grub-mkconfig.")


def update_config(entries: list, updates: dict) -> list:
    seen_keys = set()
    new_entries = []

    for entry in entries:
        if entry["type"] != "entry":
            new_entries.append(entry)
            continue

        key = entry["key"]

        # Skip duplicates
        if key in seen_keys:
            continue

        seen_keys.add(key)

        if key in updates:
            entry["value"] = updates[key]

            # only uncomment if it was updated
            if entry["commented"]:
                entry["commented"] = False

        new_entries.append(entry)

    # Add missing keys
    for key, value in updates.items():
        if key not in seen_keys:
            new_entries.append(
                {
                    "type": "entry",
                    "key": key,
                    "value": value,
                    "commented": False,
                }
            )

    return new_entries


def configure_grub(grub_config: dict, tm: TaskManager, vm: ValidationManager):
    validate_grub_config(grub_config, vm)

    grub_config_path = Path("/etc/default/grub")

    if not vm.validate(
        grub_config_path.exists(),
        f'Grub config not found at "{grub_config_path}"',
    ):
        return

    entries = parse_grub_file(grub_config_path)
    entries = update_config(entries, grub_config)

    new_content, active_lines = render(entries, vm)

    original_content = grub_config_path.read_text()
    if new_content.strip() != original_content.strip():
        syntax = Syntax(active_lines, "bash", theme="monokai", line_numbers=True)
        console.print(syntax)

        # Ask for confirmation
        if not vm.validate(
            Confirm.ask("\nDo you trust this grub configuration and want to continue?"),
            "Aborted by user due to grub configuration.",
        ):
            return

        tm.add_task(update_grub_file, "Update grub file", new_content)


def handle_bootloader(bootloader: dict, tm: TaskManager, vm: ValidationManager):
    for key, value in bootloader.items():
        if key == "grub":
            configure_grub(value, tm, vm)
        else:
            vm.validate(
                False,
                f'Only grub can be configured as bootloader for now.\nYou have "{key}" configuration in your config.',
            )
