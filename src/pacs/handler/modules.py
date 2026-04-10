from pacs.utils import parse_toml_file
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
from pacs.manager.validation_manager import ValidationManager

module_dir = common_vars.module_dir


def handle_modules(
    enabled_modules: list,
    pm: PackageManager,
    dm: DotfileManager,
    sm: ServiceManager,
    vm: ValidationManager,
):
    for module in enabled_modules:
        module_file = module_dir / f"{module}.toml"

        if not vm.validate(
            module_file.exists(),
            f"The module file does not exist at {module_file}",
            validate_now=True,
        ):
            continue

        module_data = parse_toml_file(module_file)
        handle_module_sub(module_data, module_file, pm, dm, sm, vm)


def handle_module_sub(
    module_data: dict,
    module_file: Path,
    pm: PackageManager,
    dm: DotfileManager,
    sm: ServiceManager,
    vm: ValidationManager,
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
                    handle_module_sub(value, module_file, pm, dm, sm, vm)

            case "if-cpu-intel":
                if cpu_vendor() == "intel":
                    handle_module_sub(value, module_file, pm, dm, sm, vm)

            case "if-gpu-nvidia":
                if has_nvidia_graphics():
                    handle_module_sub(value, module_file, pm, dm, sm, vm)

            case "if-gpu-intel":
                if has_intel_graphics():
                    handle_module_sub(value, module_file, pm, dm, sm, vm)

            case "if-gpu-amd":
                if has_amd_graphics():
                    handle_module_sub(value, module_file, pm, dm, sm, vm)

            case "if-has-battery":
                if has_battery():
                    handle_module_sub(value, module_file, pm, dm, sm, vm)

            case "if-has-uefi":
                if has_uefi():
                    handle_module_sub(value, module_file, pm, dm, sm, vm)

            case "if-is-virutal-manager":
                if is_virutal_manager():
                    handle_module_sub(value, module_file, pm, dm, sm, vm)
            case _:
                print(f"Ignoring unknown key {key} in module {module_file.stem}")


def handle_hooks(value, module_file):
    pass
