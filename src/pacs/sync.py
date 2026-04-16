import pacs.common_vars as common_vars

# Handlers
from pacs.handler.base import handle_base
from pacs.handler.default_apps import handle_default_apps
from pacs.handler.modules import handle_modules
from pacs.handler.theme import handle_theming
from pacs.handler.bootloader import handle_bootloader

# Managers
from pacs.manager.dotfile_manager import DotfileManager
from pacs.manager.package_manager import PackageManager
from pacs.manager.service_manager import ServiceManager
from pacs.manager.task_manager import TaskManager
from pacs.manager.validation_manager import ValidationManager

# Others
from pacs.utils import parse_toml_file

tm = TaskManager()
vm = ValidationManager()
pm = PackageManager(vm)
dm = DotfileManager(vm)
sm = ServiceManager(vm)

config_dir = common_vars.config_dir
config_py_path = common_vars.config_py_path
host_dir = common_vars.host_dir


allowed_host_keys = {
    "enabled-modules": list,
    "mimetypes": dict,
    "base": dict,
    "theme": dict,
    "bootloader": dict,
    "update-on-sync": str,
    "clean-cache-on-sync": str,
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
            handle_modules(value, pm, dm, sm, vm)
        elif key == "mimetypes":
            handle_default_apps(value, vm, tm)
        elif key == "base":
            handle_base(value, vm, tm, pm)
        elif key == "theme":
            handle_theming(value, tm, vm)
        elif key == "bootloader":
            handle_bootloader(value, tm, vm)
        elif key == "update-on-sync":
            pm.check_duration(value, "update")
        elif key == "clean-cache-on-sync":
            pm.check_duration(value, "clean")

    pm.execute(tm, vm)
    sm.execute(tm, vm)
    dm.execute(tm, vm)

    if args.dry_run:
        tm.dry_run(vm)
    else:
        tm.execute_tasks(vm)
    vm.execute()
