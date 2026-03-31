from rich.columns import Columns
from tomlkit import document

import pacs.common_vars as common_vars
from pacs.manager.task_manager import TaskManager
from pacs.manager.validation_manager import ValidationManager
from pacs.utils import difference_list, parse_toml_file, run_command, toml_to_file

service_state_file = common_vars.state_dir / "managed_service.toml"


class ServiceManager:
    def __init__(self, vm: ValidationManager):
        self.services_to_enable: list[str] = []

        # Get the list of all managed services
        if not service_state_file.exists():
            self.managed_services: list[str] = []
        else:
            service_state_data = parse_toml_file(service_state_file)
            for key, value in service_state_data.items():
                if key == "managed_services":
                    self.managed_services: list[str] = value
                else:
                    vm.validate(
                        False,
                        f"There is unknown key in the state file for services: {key}",
                    )

        # Get all services that is available in the system
        success, result = run_command(
            [
                "systemctl",
                "list-unit-files",
                "--type=service",
                "--no-pager",
                "--no-legend",
            ]
        )

        vm.validate(
            success,
            f"Cannot determine services available in system.\n{result['stderr']}",
        )

        self.services_in_system = []

        for line in result["stdout"].split("\n"):
            if not line:
                continue

            parts = line.split()
            if len(parts) >= 2:
                name, state = parts[0], parts[1]

                if state not in ["static", "indirect", "generated", "transient"]:
                    self.services_in_system.append(name)

    def add_services_to_enable(
        self, service_name: str | list[str], vm: ValidationManager
    ) -> None:
        if isinstance(service_name, str):
            service_name = [service_name]

        for service in service_name:
            vm.validate(
                service in self.services_in_system,
                f'Cannot find service "{service}" in the system.',
            )

            if service not in self.services_to_enable:
                self.services_to_enable.append(service)

    def enable_services(self, services: list[str], vm: ValidationManager) -> None:
        for service in services:
            success, _ = run_command(["systemctl", "enable", service])

            if vm.validate(success, f'Enabling "{service}" failed'):
                if service not in self.managed_services:
                    self.managed_services.append(service)

    def disable_services(self, services: list[str], vm: ValidationManager) -> None:
        for service in services:
            success, _ = run_command(["systemctl", "disable", service])

            if vm.validate(success, f'Disabling "{service}" failed'):
                if service in self.managed_services:
                    self.managed_services.remove(service)

    def update_service_state_file(self):
        doc = document()
        doc["managed_services"] = self.managed_services
        toml_to_file(service_state_file, doc)

    def execute(self, tm: TaskManager, vm: ValidationManager):
        # Determine services to disable
        # These are services that was enabled in the past but has been removed from config this time
        services_to_disable = difference_list(
            self.managed_services, self.services_to_enable
        )

        # Determine services that actually need enabling
        services_to_enable = []

        for service in self.services_to_enable:
            _, result = run_command(["systemctl", "is-enabled", service])

            if result["stdout"] != "enabled":
                services_to_enable.append(service)

        # Enable services
        if services_to_enable:
            services_to_enable.sort()

            tm.add_post_task(
                self.enable_services,
                Columns(
                    services_to_enable,
                    title="Enable the following services",
                ),
                services_to_enable,
                vm,
            )

        # Disable services
        if services_to_disable:
            services_to_disable.sort()

            tm.add_pre_task(
                self.disable_services,
                Columns(
                    services_to_disable,
                    title="Disable the following services",
                ),
                services_to_disable,
                vm,
            )

        # Update the service state file
        if self.managed_services:
            tm.add_task(
                self.update_service_state_file,
                "Update service state file",
            )
