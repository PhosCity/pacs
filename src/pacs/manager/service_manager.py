from rich.columns import Columns
from tomlkit import document, item

import pacs.common_vars as common_vars
from pacs.manager.task_manager import TaskManager
from pacs.manager.validation_manager import ValidationManager
from pacs.utils import (
    difference_list,
    list_is_same,
    parse_toml_file,
    run_command,
    toml_to_file,
)

service_state_file = common_vars.state_dir / "managed_service.toml"


class ServiceManager:
    def __init__(self, tm: TaskManager, vm: ValidationManager):
        self.tm = tm
        self.vm = vm
        self.services_to_enable: list[str] = []
        self.user_services_to_enable: list[str] = []

        # Get the list of all managed services
        self.managed_services: list[str] = []
        self.user_managed_services: list[str] = []
        if service_state_file.exists():
            service_state_data = parse_toml_file(service_state_file)
            for key, value in service_state_data.items():
                if key == "managed_services":
                    self.managed_services = value
                elif key == "user_managed_services":
                    self.user_managed_services = value
                else:
                    vm.validate(
                        False,
                        f"There is unknown key in the state file for services: {key}",
                    )

        # Get all services that is available in the system
        self.services_in_system = self.find_service_in_system()
        self.user_services_in_system = self.find_service_in_system(user_scope=True)

    def find_service_in_system(self, user_scope: bool = False) -> list[str]:
        cmd = ["systemctl", "list-unit-files", "--no-pager", "--no-legend"]
        if user_scope:
            cmd.append("--user")
        success, result = run_command(cmd)

        if not self.vm.validate(
            success,
            f"Cannot determine services available in system.\n{result['stderr']}",
        ):
            return []

        services_in_system = []

        for line in result["stdout"].splitlines():
            if not line:
                continue

            parts = line.split()
            if len(parts) < 2:
                continue

            name, state = parts[0], parts[1]

            if state in {"enabled", "disabled", "indirect"}:
                services_in_system.append(name)

        return services_in_system

    def add_services_to_enable(
        self, service_names: str | list[str], user_scope=False
    ) -> None:
        if isinstance(service_names, str):
            service_names = [service_names]

        managed_services, services_in_system, services_to_enable = self._select_scope(
            user_scope
        )

        for service in service_names:
            if "@" in service:
                # https://wiki.archlinux.org/title/Systemd#Using_units
                # https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/7/html/system_administrators_guide/chap-managing_services_with_systemd#sect-Managing_Services_with_systemd-Instantiated_Units
                if service not in managed_services:
                    print(
                        f'Instantiated units "{service}" is not validated. Make sure it\'s correct yourself.'
                    )
            else:
                self.vm.validate(
                    service in services_in_system,
                    f'Cannot find service "{service}" in the system.',
                )

            if service not in services_to_enable:
                services_to_enable.append(service)

    def enable_services(self, services: list[str], user_scope: bool = False) -> None:
        for service in services:
            cmd = ["sudo", "systemctl", "enable", service]
            if user_scope:
                cmd = ["systemctl", "--user", "enable", service]

            success, _ = run_command(cmd, capture_output=False)

            managed_services, _, _ = self._select_scope(user_scope)

            if self.vm.validate(success, f'Enabling "{service}" failed'):
                if service not in managed_services:
                    managed_services.append(service)

    def disable_services(self, services: list[str], user_scope: bool = False) -> None:
        for service in services:
            cmd = ["sudo", "systemctl", "disable", service]
            if user_scope:
                cmd = ["systemctl", "--user", "disable", service]
            success, _ = run_command(cmd, capture_output=False)

            managed_services, _, _ = self._select_scope(user_scope)

            if self.vm.validate(success, f'Disabling "{service}" failed'):
                if service in managed_services:
                    managed_services.remove(service)

    def update_service_state_file(self):
        doc = document()
        if self.services_to_enable:
            managed_services = item(self.services_to_enable)
            managed_services.multiline(True)
            doc["managed_services"] = managed_services
        if self.user_services_to_enable:
            managed_services = item(self.user_services_to_enable)
            managed_services.multiline(True)
            doc["user_managed_services"] = managed_services
        toml_to_file(service_state_file, doc)

    def execute(self):
        for user_scope, label in [(False, "system"), (True, "user")]:
            managed_services, _, desired_services = self._select_scope(user_scope)

            # Determine services to disable
            # These are services that was enabled in the past but has been removed from config this time
            services_to_disable = difference_list(managed_services, desired_services)

            services_to_enable = []
            for service in desired_services:
                cmd = ["systemctl", "is-enabled", service]
                if user_scope:
                    cmd = ["systemctl", "--user", "is-enabled", service]
                success, result = run_command(cmd)

                if not success or result["stdout"] != "enabled":
                    services_to_enable.append(service)

            # Enable services
            if services_to_enable:
                services_to_enable.sort()

                self.tm.add_post_task(
                    self.enable_services,
                    Columns(
                        services_to_enable,
                        title=f"Enable the following {label} services",
                        expand=True,
                    ),
                    services_to_enable,
                    user_scope=user_scope,
                )

            # Disable services
            if services_to_disable:
                services_to_disable.sort()

                self.tm.add_pre_task(
                    self.disable_services,
                    Columns(
                        services_to_disable,
                        title=f"Disable the following {label} services",
                        expand=True,
                    ),
                    services_to_disable,
                    user_scope=user_scope,
                )

        # Update the service state file
        if not list_is_same(
            self.managed_services, self.services_to_enable
        ) or not list_is_same(self.user_managed_services, self.user_services_to_enable):
            self.tm.add_post_task(
                self.update_service_state_file,
                "Update service state.",
            )

    def _select_scope(self, user_scope: bool) -> tuple[list[str], list[str], list[str]]:
        if user_scope:
            return (
                self.user_managed_services,
                self.user_services_in_system,
                self.user_services_to_enable,
            )
        return (
            self.managed_services,
            self.services_in_system,
            self.services_to_enable,
        )
