from pacs.utils import get_xdg_dir, list_packages, XDGType, PackageType


config_dir = get_xdg_dir(XDGType.CONFIG) / "pacs"
state_dir = get_xdg_dir(XDGType.STATE) / "pacs"


config_py_path = config_dir / "config.toml"
host_dir = config_dir / "host"
module_dir = config_dir / "module"

supported_linux_kernels = ["linux", "linux-lts", "linux-zen", "linux-hardened"]
supported_bootloaders = ["grub"]
suppoerted_aur_helpers = ["yay", "paru"]

local_pacman_package = list_packages(PackageType.PACMAN)
local_aur_package = list_packages(PackageType.AUR)
