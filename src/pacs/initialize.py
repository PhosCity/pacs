from pathlib import Path

from rich.prompt import Prompt
from tomlkit import comment, document, nl, table, item

import pacs.common_vars as common_vars
from pacs.manager.task_manager import TaskManager
from pacs.manager.validation_manager import ValidationManager
from pacs.utils import clone_git_repo, difference_list, intersection_list, toml_to_file

config_dir = common_vars.config_dir
config_py_path = common_vars.config_py_path
host_dir = common_vars.host_dir
module_dir = common_vars.module_dir

supported_linux_kernels = common_vars.supported_linux_kernels
supported_aur_helpers = common_vars.suppoerted_aur_helpers
bootloader_packages = common_vars.bootloader_packages

local_pacman_package = common_vars.local_pacman_package
local_aur_package = common_vars.local_aur_package

vm = ValidationManager()
tm = TaskManager(vm)

base_packages = ["base", "base-devel", "sudo", "pacman-contrib"]
firmware_packages = ["linux-firmware"]
supported_headers = [f"{kernel}-headers" for kernel in supported_linux_kernels]


def run_init(args):
    vm.validate(
        not config_dir.exists(),
        f"The config directory already exists at\n {config_dir}",
        validate_now=True,
    )

    if args.url:
        clone_git_repo(args.url, config_dir)
        return

    host_name = Prompt.ask("Enter the hostname for this system: ")
    host_file = host_dir / f"{host_name}.toml"

    write_config_file(host_name)
    write_host_file(host_file)
    write_module_file()

    if args.dry_run:
        tm.dry_run()
    else:
        tm.execute_tasks()


def write_config_file(host_name):
    doc = document()
    doc.add(comment('The active host configuration is in "./hosts" folder'))
    doc.add(nl())
    doc.add("host", host_name)

    tm.add_task(
        toml_to_file,
        f"Create the main config file at\n {config_py_path}",
        config_py_path,
        doc,
    )


def write_host_file(host_file: Path):
    doc = document()
    doc["enabled-modules"] = ["packages"]
    doc.add(nl())

    base = table()

    # Base
    base["base-system"] = intersection_list(base_packages, local_pacman_package)

    # Kernels
    base["kernels"] = intersection_list(supported_linux_kernels, local_pacman_package)

    # Firmeware
    installed_firmwares = intersection_list(firmware_packages, local_pacman_package)
    if installed_firmwares:
        base["firmware"] = installed_firmwares

    # Headers
    installed_headers = intersection_list(supported_headers, local_pacman_package)
    if installed_headers:
        base["headers"] = installed_headers

    # Bootloader
    installed_bootloader_packages = intersection_list(
        bootloader_packages, local_pacman_package
    )
    if installed_bootloader_packages:
        base["bootloader"] = installed_bootloader_packages

    # AUR Helpers
    installed_aur_helpers = intersection_list(supported_aur_helpers, local_aur_package)
    if installed_aur_helpers:
        if len(installed_aur_helpers) > 1:
            print(
                f"There are multiple AUR helpers installed. Chosen {installed_aur_helpers[0]}.\nChange manually if another one is desired."
            )
        base["aur_helper"] = installed_aur_helpers[0]

    doc.add("base", base)

    tm.add_task(
        toml_to_file,
        f"Create the host file at\n {host_file}",
        host_file,
        doc,
    )


def write_module_file():
    doc = document()

    remaining_pacman_packages = difference_list(
        local_pacman_package,
        base_packages + supported_linux_kernels + firmware_packages + supported_headers,
    )
    if remaining_pacman_packages:
        remaining_pacman_packages.sort()
        pacman_packages = item(remaining_pacman_packages)
        pacman_packages.multiline(True)
        doc["pacman_packages"] = pacman_packages
        doc.add(nl())

    installed_aur_helpers = intersection_list(supported_aur_helpers, local_aur_package)
    remaining_aur_packages = difference_list(local_aur_package, installed_aur_helpers)
    if remaining_aur_packages:
        remaining_aur_packages.sort()
        aur_packages = item(remaining_aur_packages)
        aur_packages.multiline(True)
        doc["aur_packages"] = aur_packages

    module_file = module_dir / "packages.toml"
    tm.add_task(
        toml_to_file,
        f"Create the module file at\n {module_file}",
        module_file,
        doc,
    )
