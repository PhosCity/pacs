from pathlib import Path

import pacs.common_vars as common_vars
from pacs.hardware import (
    cpu_vendor,
    has_amd_graphics,
    has_battery,
    has_intel_graphics,
    has_nvidia_graphics,
    has_uefi,
    is_virutal_manager,
)
from pacs.manager.dotfile_manager import DotfileManager
from pacs.manager.package_manager import PackageManager
from pacs.manager.service_manager import ServiceManager
from pacs.manager.task_manager import TaskManager
from pacs.manager.validation_manager import ValidationManager
from pacs.utils import (
    XDGType,
    find_desktop_file,
    get_xdg_dir,
    install_aur_helper,
    parse_toml_file,
)

tm = TaskManager()
vm = ValidationManager()
pm = PackageManager()
dm = DotfileManager(vm)
sm = ServiceManager(vm)

config_dir = common_vars.config_dir
config_py_path = common_vars.config_py_path
host_dir = common_vars.host_dir
module_dir = common_vars.module_dir
supported_aur_helpers = common_vars.suppoerted_aur_helpers

local_pacman_package = common_vars.local_pacman_package
local_aur_package = common_vars.local_aur_package

allowed_host_keys = {
    "enabled-modules": list,
    "mimetypes": dict,
    "base": dict,
}


def run_sync(args):
    vm.validate(
        config_dir.exists(),
        f"The config directory does not exists at\n {config_dir}",
        validate_now=True,
    )

    vm.validate(
        config_py_path.exists(),
        f"The main config file does not exists at\n {config_py_path}",
        validate_now=True,
    )

    # Get the active host name
    config = parse_toml_file(config_py_path)
    host = config["host"]

    host_file = host_dir / f"{host}.toml"

    vm.validate(
        host_file.exists(),
        f"The host file does not exists at\n {host_file}",
        validate_now=True,
    )

    host_file_data = parse_toml_file(host_file)

    for key, value in host_file_data.items():
        if key not in allowed_host_keys:
            print(f"Ignoring unknown key: {key}")
            continue

        expected_type = allowed_host_keys[key]
        if not vm.validate(
            isinstance(value, expected_type),
            f'The key "{key}" in host "{host}" should be of type "{expected_type.__name__}". Got type "{type(value)}"',
        ):
            continue

        if key == "enabled-modules":
            handle_modules(value)
        elif key == "mimetypes":
            tm.add_task(handle_default_apps, "Recreate mime types", value)
        elif key == "base":
            handle_base(value)

    pm.execute(tm, vm)
    sm.execute(tm, vm)
    dm.execute(tm, vm)

    if args.dry_run:
        tm.dry_run(vm)
    else:
        tm.execute_tasks(vm)
    vm.execute()


def handle_modules(enabled_modules: list):
    for module in enabled_modules:
        module_file = module_dir / f"{module}.toml"

        if not vm.validate(
            module_file.exists(),
            f"The module file does not exist at {module_file}",
            validate_now=True,
        ):
            continue

        module_data = parse_toml_file(module_file)
        handle_module_sub(module_data, module_file)


def handle_module_sub(
    module_data: dict,
    module_file: Path,
):
    for key, value in module_data.items():
        match key:
            case "description":
                continue

            case "pacman_packages":
                pm.add_pacman_package(value)

            case "aur_packages":
                pm.add_aur_package(value)

            case "dotfiles":
                dm.add_symlink(value, module_file, vm)

            case "external":
                dm.add_external(value, module_file, vm)

            case "services":
                sm.add_services_to_enable(value, vm)

            case "hooks":
                handle_hooks(value, module_file)

            case "if-cpu-amd":
                if cpu_vendor() == "amd":
                    handle_module_sub(value, module_file)

            case "if-cpu-intel":
                if cpu_vendor() == "intel":
                    handle_module_sub(value, module_file)

            case "if-gpu-nvidia":
                if has_nvidia_graphics():
                    handle_module_sub(value, module_file)

            case "if-gpu-intel":
                if has_intel_graphics():
                    handle_module_sub(value, module_file)

            case "if-gpu-amd":
                if has_amd_graphics():
                    handle_module_sub(value, module_file)

            case "if-has-battery":
                if has_battery():
                    handle_module_sub(value, module_file)

            case "if-has-uefi":
                if has_uefi():
                    handle_module_sub(value, module_file)

            case "if-is-virutal-manager":
                if is_virutal_manager():
                    handle_module_sub(value, module_file)
            case _:
                print(f"Ignoring unknown key {key} in module {module_file.stem}")


def handle_default_apps(associations: dict) -> None:
    """
    Build mimeapps.list content.
    """

    output_path = get_xdg_dir(XDGType.CONFIG) / "mimeapps.list"

    mimetype_map = {
        "browser": [
            "text/html",
            "x-scheme-handler/http",
            "x-scheme-handler/https",
        ],
        "text_editor": [
            "text/plain",  # .txt
            "text/markdown",  # .md
            "text/html",  # .html
            "text/css",  # .css
            "text/csv",  # .csv
            "application/json",  # .json
            "application/xml",  # .xml
            "application/x-yaml",  # .yaml/.yml
        ],
        "file_manager": [
            "inode/directory",
        ],
        "video_player": [
            "video/mp4",  # .mp4
            "video/x-matroska",  # .mkv
            "video/webm",  # .webm
            "video/x-msvideo",  # .avi
            "video/quicktime",  # .mov
        ],
        "audio_player": [
            "audio/mpeg",  # .mp3
            "audio/wav",  # .wav
            "audio/flac",  # .flac
            "audio/ogg",  # .ogg
            "audio/mp4",  # .m4a
            "audio/aac",  # .aac
        ],
        "image_viewer": [
            "image/png",  # .png
            "image/jpeg",  # .jpg/.jpeg
            "image/gif",  # .gif
            "image/webp",  # .webp
            "image/svg+xml",  # .svg
            "image/bmp",  # .bmp
        ],
    }

    sections = {
        "Default Applications": {},
        "Added Associations": {},
        "Removed Associations": {},
    }

    def populate(section_name: str, data: dict | None):
        if not data:
            return

        section = sections[section_name]

        for key, value in sorted(data.items()):
            vm.validate(
                find_desktop_file(value),
                f"The desktop file for {value} does not exist.",
            )
            mimetypes = mimetype_map.get(key) or [key]

            if isinstance(value, list):
                value = ";".join(value) + ";"

            for mimetype in mimetypes:
                section[mimetype] = value

    if default := associations.get("default"):
        populate("Default Applications", default)
    if added_associations := associations.get("added-associations"):
        populate("Added Associations", added_associations)
    if removed_associations := associations.get("removed-associations"):
        populate("Removed Associations", removed_associations)

    # Remove empty sections
    sections = {k: v for k, v in sections.items() if v}
    if not sections:
        return

    lines = []
    for section_name, entries in sections.items():
        lines.append(f"[{section_name}]")
        for mime, val in sorted(entries.items()):
            lines.append(f"{mime}={val}")
        lines.append("")

    output_path.write_text("\n".join(lines))


def handle_hooks(value, module_file):
    pass


def handle_base(base):
    valid_keys = ["base-system", "kernels", "firmware", "headers", "swap", "aur_helper"]
    for key, value in base.items():
        if not vm.validate(
            key in valid_keys,
            f"{key} is not a valid key while configuring base system.",
        ):
            continue

        if key == "aur_helper":
            aur_helper = value

            vm.validate(
                aur_helper in supported_aur_helpers,
                f"{aur_helper} is not a supported aur helper.",
            )

            if aur_helper not in local_aur_package:
                tm.add_pre_task(
                    install_aur_helper,
                    f'Install AUR Helper "{aur_helper}"',
                    aur_helper,
                    local_pacman_package,
                )

            pm.set_aur_helper(aur_helper)
        else:
            pm.add_pacman_package(value)
