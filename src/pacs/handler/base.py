import shutil
import sys
import tempfile
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm
from rich.syntax import Syntax

import pacs.common_vars as common_vars
from pacs.manager.package_manager import PackageManager
from pacs.manager.task_manager import TaskManager
from pacs.manager.validation_manager import ValidationManager
from pacs.utils import aur_helper_package_names, clone_git_repo, run_command

console = Console()

supported_aur_helpers = common_vars.supported_aur_helpers
all_installed_packages = common_vars.local_installed_package


def install_aur_helper(aur_helper: str) -> bool:
    """
    Install the AUR helper of your choice.

    Args:
        aur_helper (str): The AUR helper you want to download.

    Returns:
        bool: True once the AUR helper is installed.

    Raises:
        FileNotFoundError: If PKGBUILD cannot be cloned.
        RuntimeError: If building or installing the AUR helper fails.
        SystemExit: If the user does not trust the PKGBUILD. The rest of the sync
            depends on the AUR helper, so carrying on without it makes no sense.
    """
    repo_url = f"https://aur.archlinux.org/{aur_helper}.git"

    # Create temp dir in /tmp
    build_dir = Path(tempfile.mkdtemp(prefix=f"{aur_helper}-build-"))

    try:
        console.print(f"[bold cyan]Cloning {aur_helper}...[/bold cyan]")
        clone_git_repo(repo_url, build_dir)

        pkgbuild_path = build_dir / "PKGBUILD"

        if not pkgbuild_path.exists():
            raise FileNotFoundError("PKGBUILD not found in repo")

        # Display PKGBUILD with syntax highlighting
        console.print(
            "\n[bold yellow]Review PKGBUILD before proceeding:[/bold yellow]\n"
        )
        syntax = Syntax(
            pkgbuild_path.read_text(), "bash", theme="monokai", line_numbers=True
        )
        console.print(syntax)

        # Ask for confirmation
        if not Confirm.ask("\nDo you trust this PKGBUILD and want to continue?"):
            console.print("[red]Aborted by user.[/red]")
            sys.exit(
                f'The AUR helper "{aur_helper}" is not installed but your config '
                "needs it, so the sync has been stopped."
            )

        # Build and install
        console.print("[bold green]Building and installing...[/bold green]")
        success, _ = run_command(
            ["makepkg", "-si"], cwd=build_dir, capture_output=False
        )
        if not success:
            raise RuntimeError(
                f'Failed to build and install the AUR helper "{aur_helper}".'
            )

        if shutil.which(aur_helper) is None:
            raise RuntimeError(
                f'"{aur_helper}" was built but the "{aur_helper}" command was not found.'
            )

        console.print(f"[bold green]{aur_helper} installed successfully![/bold green]")
        return True
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)


def handle_base(
    base: dict, vm: ValidationManager, tm: TaskManager, pm: PackageManager
) -> None:
    valid_keys = [
        "base-system",
        "kernels",
        "firmware",
        "headers",
        "swap",
        "aur-helper",
        "bootloader",
    ]
    for key, value in base.items():
        if not vm.validate(
            key in valid_keys,
            f"{key} is not a valid key while configuring base system.",
        ):
            continue

        if key == "aur-helper":
            aur_helper = value

            vm.validate(
                aur_helper in supported_aur_helpers,
                f"{aur_helper} is not a supported aur helper.",
            )

            if not any(
                package in all_installed_packages
                for package in aur_helper_package_names(aur_helper)
            ):
                # The helper is built before any package from the config gets
                # installed, so these have to be on the system already.
                vm.validate(
                    "base-devel" in all_installed_packages
                    and "git" in all_installed_packages,
                    f'"base-devel" and "git" must already be installed to build the AUR helper "{aur_helper}".\n'
                    "Install them first with: sudo pacman -S --needed base-devel git",
                )
                tm.add_pre_task(
                    install_aur_helper,
                    f'Install AUR Helper "{aur_helper}"',
                    aur_helper,
                )

            pm.set_aur_helper(aur_helper)
        else:
            pm.add_pacman_package(value)
