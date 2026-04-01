import subprocess
from pathlib import Path

from pacs.utils import run_command

# https://github.com/archlinux/archinstall/blob/master/archinstall/lib/hardware.py


def graphics_devices() -> dict[str, str]:
    """
    Returns detected graphics devices

    Returns:
        dict[str, str]:
            Key: Device identifier
            Value: Full lsp3ci description line
    """
    cards = {}
    output = subprocess.check_output(["lspci"], text=True)

    for line in output.splitlines():
        if "VGA" in line or "3D" in line:
            _, identifier = line.split(": ", 1)
            cards[identifier.strip()] = line

    return cards


def cpu_info() -> dict[str, str]:
    """
    Retrieves CPU information from /proc/cpuinfo.

    Returns:
        dict[str, str]:
            Key: CPU information field
            Value: Corresponding value from /proc/cpuinfo
    """
    cpu_info_path = Path("/proc/cpuinfo")
    cpu: dict[str, str] = {}

    with cpu_info_path.open() as file:
        for line in file:
            if line := line.strip():
                key, value = line.split(":", maxsplit=1)
                cpu[key.strip()] = value.strip()

    return cpu


def has_battery() -> bool:
    """
    Checks if the system has a battery by examining power supply type entries.

    Returns:
        bool: True if a battery is detected, False otherwise

    Raises:
        OSError: If the file cannot be read.
    """
    for type_path in Path("/sys/class/power_supply/").glob("*/type"):
        try:
            with open(type_path) as f:
                if f.read().strip() == "Battery":
                    return True
        except OSError:
            continue

    return False


def has_nvidia_graphics() -> bool:
    """
    Checks if any detected graphics device is from NVIDIA.

    Returns:
        bool: True if NVIDIA graphics are detected, False otherwise
    """
    return any("nvidia" in x.lower() for x in graphics_devices())


def has_amd_graphics() -> bool:
    """
    Checks if any detected graphics device is from AMD.

    Returns:
        bool: True if AMD graphics are detected, False otherwise
    """
    return any("amd" in x.lower() for x in graphics_devices())


def has_intel_graphics() -> bool:
    """
    Checks if any detected graphics device is from Intel.

    Returns:
        bool: True if Intel graphics are detected, False otherwise
    """
    return any("intel" in x.lower() for x in graphics_devices())


def cpu_vendor() -> str | None:
    """
    Determines the CPU vendor (Intel/AMD) from CPU information.

    Returns:
        str | None:
            "intel" if vendor is GenuineIntel,
            "amd" if vendor is AuthenticAMD,
            None if vendor cannot be determined
    """
    if vendor := cpu_info().get("vendor_id"):
        if vendor == "GenuineIntel":
            return "intel"
        elif vendor == "AuthenticAMD":
            return "amd"
        else:
            return None
    return None


def has_uefi() -> bool:
    """
    Check whether the system is booted in UEFI mode.

    Returns:
        bool: True if the system is running in UEFI mode, False otherwise.
    """
    return Path("/sys/firmware/efi").exists()


def is_virutal_manager() -> bool:
    success, result = run_command(["systemd-detect-virt"])
    if not success:
        return False

    output = result["stdout"]
    if output == "none":
        return False

    return True
