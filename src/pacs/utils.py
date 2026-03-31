import os
import platform
import subprocess
import sys
import tempfile
import urllib.request
from enum import Enum
from pathlib import Path

from git import Repo
from rich.console import Console
from rich.prompt import Confirm
from rich.syntax import Syntax
from tomlkit import dumps, parse

console = Console()


def is_arch_linux() -> bool:
    """
    Determine whether the current device is running Arch Linux.

    Returns:
    --------
        bool: True if the current os is Arch Linux, False otherwise.
    """
    if platform.system() != "Linux":
        return False

    os_release = Path("/etc/os-release")

    if os_release.is_file():
        try:
            for line in os_release.read_text().splitlines():
                if line.strip().lower() == "id=arch":
                    return True
        except OSError:
            pass

    # Fallback check
    if Path("/etc/arch-release").is_file():
        return True

    return False


class XDGType(str, Enum):
    CONFIG = "config"
    DATA = "data"
    CACHE = "cache"
    STATE = "state"


def get_xdg_dir(xdg_type: XDGType) -> Path:
    """
    Return the XDG base directory path for the given directory type.

    This function resolves the directory according to the XDG Base Directory Specification
    by checking environment variables and falling back to the standard defaults.

    Args
    -----
        xdg_type: XDGType
            The type of XDG directory to retrieve. Must be one of:
            XDGType.CONFIG, XDGType.DATA, XDGType.CACHE, or XDGType.STATE.

    Returns
    -------
    Path
        A path pointing to the resolved XDG directory.
    """
    home = Path.home()

    defaults = {
        XDGType.CONFIG: home / ".config",
        XDGType.DATA: home / ".local" / "share",
        XDGType.CACHE: home / ".cache",
        XDGType.STATE: home / ".local" / "state",
    }

    env_vars = {
        XDGType.CONFIG: "XDG_CONFIG_HOME",
        XDGType.DATA: "XDG_DATA_HOME",
        XDGType.CACHE: "XDG_CACHE_HOME",
        XDGType.STATE: "XDG_STATE_HOME",
    }

    return Path(os.environ.get(env_vars[xdg_type], defaults[xdg_type]))


class PackageType(str, Enum):
    PACMAN = "pacman"
    REMOTE = "remote"
    AUR = "aur"


def list_packages(mode: PackageType):
    """
    Retrieve a list of package names from pacman based on the specified mode.

    Parameters:
        mode (str): The mode to determine which pacman command to execute.
            Supported modes:
                - "pacman": List explicitly installed packages using pacman
                - "remote": List remote packages from pacman database
                - "aur": List all installed packages from AUR

    Returns:
        list: A list of package names as strings.

    Raises:
        ValueError: If an unsupported mode is provided.
    """

    if mode == PackageType.PACMAN:
        cmd = ["pacman", "-Qen"]
    elif mode == PackageType.REMOTE:
        cmd = ["pacman", "-Slq"]
    elif mode == PackageType.AUR:
        cmd = ["pacman", "-Qm"]

    _, result = run_command(cmd)

    packages = [line.split()[0] for line in result["stdout"].split("\n")]
    return packages


def toml_to_file(filename: Path, doc) -> None:
    """
    Write a TOML document to a file.

    Args:
        filename (Path): The path to the TOML file to write.
        doc: A tomlkit document object to be serialized and saved.

    Returns:
        None
    """
    filename.parent.mkdir(parents=True, exist_ok=True)
    filename.write_text(dumps(doc), encoding="utf-8")


def parse_toml_file(toml_file: Path):
    """
    Read and parse a TOML file using tomlkit.

    Args:
        toml_file (Path): Path to the TOML file to parse.

    Returns:
        Parsed TOML data
    """
    if toml_file.suffix.lower() != ".toml":
        raise ValueError(f"The path {toml_file} is not a toml file.")
    return parse(toml_file.read_text())


def difference_list(list1: list[str], list2: list[str]) -> list[str]:
    """
    Return a new list containing elements that are in list1 but not in list2
    Does not preserve order and removes duplicate elements.

    Args:
        list1 (list[str]): The primary list.
        list2 (list[str]): The list of elements to exclude.

    Returns:
        list[str]: A list of elements in list1 but not in list2.
    """
    return list(set(list1) - set(list2))


def intersection_list(list1: list[str], list2: list[str]) -> list[str]:
    """
    Return a new list containing elements that are present in both list1 and list2
    Does not preserve order and removes duplicate elements.

    Args:
        list1 (list[str]): The first list.
        list2 (list[str]): The second list.

    Returns:
        list[str]: A list of elements common to both lists.
    """
    return list(set(list1) & set(list2))


def clone_git_repo(repo_url: str, path_to_clone: Path) -> None:
    """
    Clone a git repository into a specified directory.

    Args:
        repo_url (str): url of the git repository.
        path_to_clone (Path): Target directory where the repository will be cloned.

    Raises:
        FileExistsError: If the target directory already exists and is not empty.
    """
    path_to_clone.parent.mkdir(parents=True, exist_ok=True)

    if path_to_clone.exists() and any(path_to_clone.iterdir()):
        raise FileExistsError(f"Target directory '{path_to_clone}' is not empty.")

    Repo.clone_from(repo_url, path_to_clone)


def run_command(
    cmd: list[str], *, shell: bool = False, text: bool = True, cwd: None | Path = None
) -> tuple[bool, dict]:
    """
    Run a subprocess command and return structured results.

    Args:
        cmd (list[str]): Command to run where each element of list is space delimited.
        shell (bool): Whether to run the command through the shell.
        text (bool): If True, return stdout/stderr as strings.

    Returns:
        tuple:
            bool: True if command successfully ran, False otherwise
            dict: A dictionary containing:
                - returncode (int): Process exit code
                - stdout (str): Standard output
                - stderr (str): Standard error
                - error (Exception | None): Exception if one occurred
    """
    try:
        result = subprocess.run(
            cmd,
            shell=shell,
            capture_output=True,
            text=text,
            cwd=cwd,
        )

        details = {
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "error": None,
        }

        return result.returncode == 0, details

    except Exception as e:
        return False, {
            "returncode": None,
            "stdout": None,
            "stderr": None,
            "error": e,
        }


def install_aur_helper(aur_helper: str, local_pacman_package: list[str]) -> bool:
    """
    Install the AUR helper of your choice.

    Args:
        aur_helper (str): The AUR helper you want to download.
        local_pacman_package (list[str]): List of packages installed using pacman.

    Returns:
        bool: True if AUR helper is successfully downloaded, False otherwise.

    Raises:
        FileNotFoundError: If PKGBUILD cannot be cloned.
    """
    repo_url = f"https://aur.archlinux.org/{aur_helper}.git"

    # Ensure dependencies
    if "base-devel" not in local_pacman_package and "git" not in local_pacman_package:
        console.print("[bold cyan]Installing dependencies...[/bold cyan]")
        success, _ = run_command(
            ["sudo", "pacman", "-S", "--needed", "base-devel", "git"]
        )
        if not success:
            sys.exit(
                f"Failed to install dependencies while installing AUR Helper: {aur_helper}"
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
    run_command(["makepkg", "-si"], cwd=build_dir)

    console.print(f"[bold green]{aur_helper} installed successfully![/bold green]")

    return True


def download_file(url: str, save_path: Path, chunk_size=8192):
    """
    Download a file from a URL to a specified local path.

    Parameters
    ----------
    url : str
        The URL of the file to download.
    save_path : Path
        The destination file path where the downloaded file will be saved.
    chunk_size : int, optional
        The number of bytes to read at a time (default is 8192).
    """

    save_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with urllib.request.urlopen(url) as response, save_path.open("wb") as f:
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
        return True

    except Exception as e:
        console.log(f"Downloading file from url failed\n: {e}")
        return False
