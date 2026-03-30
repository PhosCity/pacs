import pacs.common_vars as common_vars
from pacs.manager.task_manager import TaskManager
from pacs.manager.validation_manager import ValidationManager
from pacs.utils import parse_toml_file

tm = TaskManager()
vm = ValidationManager()

config_dir = common_vars.config_dir
config_py_path = common_vars.config_py_path
host_dir = common_vars.host_dir

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
        vm.validate(
            isinstance(value, expected_type),
            f'The key "{key}" in host "{host}" should be of type "{expected_type.__name__}". Got type "{type(value)}"',
        )

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
    pass
