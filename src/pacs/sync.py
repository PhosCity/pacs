import pacs.common_vars as common_vars
from pacs.manager.task_manager import TaskManager
from pacs.manager.validation_manager import ValidationManager
from pacs.manager.package_manager import PackageManager
from pacs.utils import install_aur_helper, parse_toml_file

tm = TaskManager()
vm = ValidationManager()
pm = PackageManager()

config_dir = common_vars.config_dir
config_py_path = common_vars.config_py_path
host_dir = common_vars.host_dir
supported_aur_helpers = common_vars.suppoerted_aur_helpers

local_pacman_package = common_vars.local_pacman_package
local_aur_package = common_vars.local_aur_package

allowed_host_keys = {
    "aur_helper": str,
    "enabled-modules": list,
    "mimetypes": dict,
    "base": dict,
}


def run_sync(args):
    vm.validate(
        config_dir.exists(),
        f"The config directory does not exists at\n {config_dir}",
        validate_now=True,
    )

    vm.validate(
        config_py_path.exists(),
        f"The main config file does not exists at\n {config_py_path}",
        validate_now=True,
    )

    # Get the active host name
    config = parse_toml_file(config_py_path)
    host = config["host"]

    host_file = host_dir / f"{host}.toml"

    vm.validate(
        host_file.exists(),
        f"The host file does not exists at\n {host_file}",
        validate_now=True,
    )

    host_file_data = parse_toml_file(host_file)

    for key, value in host_file_data.items():
        if key not in allowed_host_keys:
            print(f"Ignoring unknown key: {key}")
            continue

        expected_type = allowed_host_keys[key]
        if not vm.validate(
            isinstance(value, expected_type),
            f'The key "{key}" in host "{host}" should be of type "{expected_type.__name__}". Got type "{type(value)}"',
        ):
            continue

        if key == "enabled-modules":
            handle_enable_modules(value)
        elif key == "mimetypes":
            tm.add_task(handle_default_apps, "Recreate mime types", value)
        elif key == "base":
            handle_base(value)

    if args.dry_run:
        tm.dry_run(vm)
    else:
        tm.execute_tasks(vm)
    vm.execute()


def handle_enable_modules(enabled_modules: list):
    pass


def handle_default_apps(associations: dict) -> None:
    pass


def handle_base(base):
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
