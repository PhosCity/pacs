import os
import platform
import subprocess
from enum import Enum
from pathlib import Path

from tomlkit import dumps, parse


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

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)

    packages = [line.split()[0] for line in result.stdout.strip().split("\n")]
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
