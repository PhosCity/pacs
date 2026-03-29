import platform
from pathlib import Path


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
