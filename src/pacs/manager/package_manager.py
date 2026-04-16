from datetime import datetime, timezone

from rich.columns import Columns
from tomlkit import document

import pacs.common_vars as common_vars
from pacs.manager.task_manager import TaskManager
from pacs.manager.validation_manager import ValidationManager
from pacs.utils import (
    difference_list,
    parse_refresh_period,
    parse_toml_file,
    run_command,
    toml_to_file,
)

local_pacman_packages = common_vars.local_pacman_package
local_aur_packages = common_vars.local_aur_package
all_installed_packages = common_vars.local_installed_package

update_state_file = common_vars.state_dir / "package.toml"


class PackageManager:
    def __init__(self, vm: ValidationManager):
        self.pacman_packages: list[str] = []
        self.aur_packages: list[str] = []
        self.aur_helper = None

        self.last_updated: datetime | None = None
        self.last_cleaned: datetime | None = None
        if update_state_file.exists():
            update_state = parse_toml_file(update_state_file)

            for key, value in update_state.items():
                if key == "lastUpdated":
                    self.last_updated = datetime.fromisoformat(value)
                elif key == "lastCleaned":
                    self.last_cleaned = datetime.fromisoformat(value)
                else:
                    vm.validate(
                        False,
                        f"There is unknown key in the state file for packages: {key}",
                    )

        self.should_update = True
        self.should_clean = True

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

    def check_duration(self, duration: str, mode: str):
        now = datetime.now(timezone.utc)
        if mode == "update":
            if self.last_updated:
                try:
                    period = parse_refresh_period(duration)
                    self.should_update = now - self.last_updated >= period
                except Exception:
                    pass
        elif mode == "clean":
            if self.last_cleaned:
                try:
                    period = parse_refresh_period(duration)
                    self.should_clean = now - self.last_cleaned >= period
                except Exception:
                    pass
        else:
            raise ValueError("Wrong mode while chekcing duration for package.")

    def _update_command(self):
        if self.aur_helper:
            run_command([self.aur_helper, "-Syu"], capture_output=False)
        else:
            run_command(["sudo", "pacman", "-Syu"], capture_output=False)

    def _clean_command(self):
        run_command(["paccache", "-rk1"], capture_output=False)
        run_command(["paccache", "-ruk0"], capture_output=False)

        _, result = run_command(["pacman", "-Qtdq"])
        package_to_clean = result["stdout"]

        if package_to_clean:
            package_to_clean = package_to_clean.split(" ")
            run_command(
                ["sudo", "pacman", "-Rns", *package_to_clean], capture_output=False
            )

    def _update_state(self):
        now = datetime.now(timezone.utc).isoformat()
        doc = document()

        doc["lastUpdated"] = now if self.should_update else self.last_updated
        doc["lastCleaned"] = now if self.should_clean else self.last_cleaned

        toml_to_file(update_state_file, doc)

    def execute(self, tm: TaskManager, vm: ValidationManager) -> None:
        if self.aur_packages:
            vm.validate(
                self.aur_helper is not None,
                "AUR packages has been defined for this host but aur helper is not.",
            )

        pacman_packages_to_install = difference_list(
            self.pacman_packages, all_installed_packages
        )
        aur_packages_to_install = difference_list(
            self.aur_packages, all_installed_packages
        )

        if pacman_packages_to_install:
            pacman_packages_to_install.sort()
            tm.add_task(
                self.install_pacman,
                Columns(
                    pacman_packages_to_install,
                    title="Install following packages from pacman",
                    expand=True,
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
                    expand=True,
                ),
                aur_packages_to_install,
                vm,
            )

        packages_to_uninstall = difference_list(
            local_pacman_packages + local_aur_packages,
            self.pacman_packages + self.aur_packages,
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
                    expand=True,
                ),
                packages_to_uninstall,
                vm,
            )

        if self.should_update:
            tm.add_post_task(self._update_command, "Update packages.")

        if self.should_clean:
            tm.add_post_task(self._clean_command, "Clean packages.")

        if self.should_clean or self.should_update:
            tm.add_post_task(self._update_state, "Update package state.")
