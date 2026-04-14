import tempfile
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm
from rich.syntax import Syntax

import pacs.common_vars as common_vars
from pacs.manager.package_manager import PackageManager
from pacs.manager.task_manager import TaskManager
from pacs.manager.validation_manager import ValidationManager
from pacs.utils import clone_git_repo, run_command

console = Console()

supported_aur_helpers = common_vars.suppoerted_aur_helpers
all_installed_packages = common_vars.local_installed_package


def install_aur_helper(aur_helper: str, vm: ValidationManager) -> bool:
    """
    Install the AUR helper of your choice.

    Args:
        aur_helper (str): The AUR helper you want to download.
        vm (ValidationManager): Validation Manager

    Returns:
        bool: True if AUR helper is successfully downloaded, False otherwise.

    Raises:
        FileNotFoundError: If PKGBUILD cannot be cloned.
    """
    repo_url = f"https://aur.archlinux.org/{aur_helper}.git"

    # Ensure dependencies
    vm.validate(
        "base-devel" in all_installed_packages and "git" in all_installed_packages,
        'Both "base-devel" and "git" package must be in your config to install AUR helper.',
    )

    # Create temp dir in /tmp
    build_dir = Path(tempfile.mkdtemp(prefix=f"{aur_helper}-build-"))

    console.print(f"[bold cyan]Cloning {aur_helper}...[/bold cyan]")
    clone_git_repo(repo_url, build_dir)

    pkgbuild_path = build_dir / "PKGBUILD"

    if not pkgbuild_path.exists():
        raise FileNotFoundError("PKGBUILD not found in repo")

    # Display PKGBUILD with syntax highlighting
    console.print("\n[bold yellow]Review PKGBUILD before proceeding:[/bold yellow]\n")
    syntax = Syntax(
        pkgbuild_path.read_text(), "bash", theme="monokai", line_numbers=True
    )
    console.print(syntax)

    # Ask for confirmation
    if not Confirm.ask("\nDo you trust this PKGBUILD and want to continue?"):
        console.print("[red]Aborted by user.[/red]")
        return False

    # Build and install
    console.print("[bold green]Building and installing...[/bold green]")
    run_command(["makepkg", "-si"], cwd=build_dir, capture_output=False)

    console.print(f"[bold green]{aur_helper} installed successfully![/bold green]")

    return True


def handle_base(
    base: dict, vm: ValidationManager, tm: TaskManager, pm: PackageManager
) -> None:
    valid_keys = [
        "base-system",
        "kernels",
        "firmware",
        "headers",
        "swap",
        "aur_helper",
        "bootloader",
    ]
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

            if aur_helper not in all_installed_packages:
                tm.add_pre_task(
                    install_aur_helper,
                    f'Install AUR Helper "{aur_helper}"',
                    aur_helper,
                    vm,
                )

            pm.set_aur_helper(aur_helper)
        else:
            pm.add_pacman_package(value)
