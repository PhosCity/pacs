from rich.columns import Columns

import pacs.common_vars as common_vars
from pacs.manager.task_manager import TaskManager
from pacs.manager.validation_manager import ValidationManager
from pacs.utils import difference_list, run_command

local_pacman_packages = common_vars.local_pacman_package
local_aur_packages = common_vars.local_aur_package
all_installed_packages = local_pacman_packages + local_aur_packages


class PackageManager:
    def __init__(self):
        self.pacman_packages: list[str] = []
        self.aur_packages: list[str] = []
        self.aur_helper = None

    def add_pacman_package(self, package_name: str | list[str]) -> None:
        """
        Add a new pacman package to install or keep installed

        Parameters:
            package_name (str): Name of package name
        """
        if isinstance(package_name, list):
            self.pacman_packages.extend(package_name)
        elif isinstance(package_name, str):
            self.pacman_packages.append(package_name)

    def add_aur_package(self, package_name: str | list[str]) -> None:
        """
        Add a new AUR package to install or keep installed

        Parameters:
            package_name (str): Name of package name
        """
        if isinstance(package_name, list):
            self.aur_packages.extend(package_name)
        elif isinstance(package_name, str):
            self.aur_packages.append(package_name)

    def set_aur_helper(self, helper: str) -> None:
        self.aur_helper = helper

    def install_pacman(
        self, pacman_packages_to_install: list[str], vm: ValidationManager
    ) -> None:
        """
        Install all the collected packages using pacman
        """
        success, _ = run_command(
            ["sudo", "pacman", "-S", "--needed", *pacman_packages_to_install],
            capture_output=False,
        )
        vm.validate(success, "Failed to install pacman packages.")

    def install_aur(
        self, aur_packages_to_install: list[str], vm: ValidationManager
    ) -> None:
        """
        Install all the collected packages using an AUR helper of your choice
        """
        if not self.aur_helper:
            raise RuntimeError("An aur helper could not be found.")

        success, _ = run_command(
            [self.aur_helper, "-S", "--needed", *aur_packages_to_install],
            capture_output=False,
        )
        vm.validate(success, "Failed to install AUR packages.")

    def uninstall_packages(
        self, packages_to_uninstall: list[str], vm: ValidationManager
    ) -> None:
        """
        Uninstall all the collected packages using an AUR helper of your choice
        """
        success, _ = run_command(
            ["sudo", "pacman", "-Rcns", *packages_to_uninstall], capture_output=False
        )
        vm.validate(success, "Failed to remove unused packages from the system.")

    def execute(self, tm: TaskManager, vm: ValidationManager) -> None:
        if self.aur_packages:
            vm.validate(
                self.aur_helper is not None,
                "AUR packages has been defined for this host but aur helper is not.",
            )

        pacman_packages_to_install = difference_list(
            self.pacman_packages, local_pacman_packages
        )
        aur_packages_to_install = difference_list(self.aur_packages, local_aur_packages)

        if pacman_packages_to_install:
            pacman_packages_to_install.sort()
            tm.add_task(
                self.install_pacman,
                Columns(
                    pacman_packages_to_install,
                    title="Install following packages from pacman",
                ),
                pacman_packages_to_install,
                vm,
            )

        if aur_packages_to_install:
            aur_packages_to_install.sort()
            tm.add_task(
                self.install_aur,
                Columns(
                    aur_packages_to_install,
                    title="Install following packages from AUR",
                ),
                aur_packages_to_install,
                vm,
            )

        packages_to_uninstall = difference_list(
            all_installed_packages, self.pacman_packages + self.aur_packages
        )
        if self.aur_helper in packages_to_uninstall:
            packages_to_uninstall.remove(self.aur_helper)

        if packages_to_uninstall:
            packages_to_uninstall.sort()
            tm.add_task(
                self.uninstall_packages,
                Columns(
                    packages_to_uninstall,
                    title="Uninstall following packages from the system",
                ),
                packages_to_uninstall,
                vm,
            )
