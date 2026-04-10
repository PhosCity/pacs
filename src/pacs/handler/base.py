import pacs.common_vars as common_vars
from pacs.manager.package_manager import PackageManager
from pacs.manager.task_manager import TaskManager
from pacs.manager.validation_manager import ValidationManager
from pacs.utils import install_aur_helper

local_pacman_package = common_vars.local_pacman_package
local_aur_package = common_vars.local_aur_package
supported_aur_helpers = common_vars.suppoerted_aur_helpers


def handle_base(
    base: dict, vm: ValidationManager, tm: TaskManager, pm: PackageManager
) -> None:
    valid_keys = ["base-system", "kernels", "firmware", "headers", "swap", "aur_helper"]
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

            if aur_helper not in local_aur_package:
                tm.add_pre_task(
                    install_aur_helper,
                    f'Install AUR Helper "{aur_helper}"',
                    aur_helper,
                    local_pacman_package,
                )

            pm.set_aur_helper(aur_helper)
        else:
            pm.add_pacman_package(value)
