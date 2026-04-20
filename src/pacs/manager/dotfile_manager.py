import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from rich.text import Text
from tomlkit import document, table

import pacs.common_vars as common_vars
from pacs.manager.task_manager import TaskManager
from pacs.manager.validation_manager import ValidationManager
from pacs.utils import (
    clone_git_repo,
    download_file,
    parse_refresh_period,
    parse_toml_file,
    resolve_path,
    toml_to_file,
    url_is_valid,
)

config_dir = common_vars.config_dir
dotfile_state_file = common_vars.state_dir / "managed_dotfiles.toml"


class DotfileManager:
    def __init__(self, tm: TaskManager, vm: ValidationManager):
        self.vm = vm
        self.tm = tm

        self.files_to_symlink: dict[Path, Path] = {}
        self.external_files: dict[Path, dict] = {}

        # State
        self.managed_symlinks: dict[Path, Path] = {}
        self.managed_externals: dict[Path, dict] = {}

        if dotfile_state_file.exists():
            state = parse_toml_file(dotfile_state_file)

            self.managed_symlinks = {
                Path(dest): Path(src) for dest, src in state.get("symlinks", {}).items()
            }

            self.managed_externals = {
                Path(dest): value for dest, value in state.get("external", {}).items()
            }

    # ╭─────────────────────────────────────────────────────────────────────────────╮
    # │ Config Collection                                                           │
    # ╰─────────────────────────────────────────────────────────────────────────────╯
    def add_symlink(self, dotfiles: dict[Path, list], module_file: Path) -> None:
        base = module_file.parent
        module_name = module_file.stem

        for entries in dotfiles.values():
            for mapping in entries:
                for destination, source in mapping.items():
                    source = resolve_path(source, base)
                    destination = resolve_path(destination, base)

                    # Source and destination must not be same
                    if source == destination:
                        continue

                    # Duplicate key is not allowed
                    if destination in self.files_to_symlink:
                        self.vm.validate(
                            False,
                            f'Multiple source files mapped to same destination: "{destination}"',
                        )
                        continue

                    # Source must exist
                    if not self.vm.validate(
                        source.exists(),
                        f'Source not found:\n "{source}" in module "{module_name}"',
                    ):
                        continue

                    # Destination cannot be inside the pacs configuration folder
                    if not self.vm.validate(
                        config_dir not in destination.parents,
                        f'Destination:\n "{destination}"\n in module "{module_name}" points to the config directory.',
                    ):
                        continue

                    self.files_to_symlink[destination] = source

    def add_external(self, external: dict, module_file: Path) -> None:
        base = module_file.parent
        module_name = module_file.stem

        for destination, value in external.items():
            destination = resolve_path(destination, base)
            ext_type, url, refresh = (
                value.get("type"),
                value.get("url"),
                value.get("refreshPeriod"),
            )

            # Duplicate key is not allowed
            if destination in self.external_files:
                self.vm.validate(
                    False,
                    f'Multiple external files linked to same destination: "{destination}"',
                )
                continue

            if not self.vm.validate(
                ext_type and url and refresh,
                f'Incomplete external config: "{destination}" in module "{module_name}"',
            ):
                continue

            if not self.vm.validate(
                ext_type in {"file", "git-repo"},
                f'Invalid type "{ext_type}" in external config: "{destination}" in module "{module_name}"',
            ):
                continue

            if not self.vm.validate(
                url_is_valid(url),
                f'Invalid url in module "{module_name}": "{url}"',
            ):
                continue

            self.external_files[destination] = {
                "type": ext_type,
                "url": url,
                "refresh_period": refresh,
            }

            # # Ensure state entry exists
            # self.external_state.setdefault(key, {})["destination"] = (
            #     resolved_destination
            # )

    # ╭─────────────────────────────────────────────────────────────────────────────╮
    # │ Tasks                                                                       │
    # ╰─────────────────────────────────────────────────────────────────────────────╯
    def task_symlink_files(self, files_to_symlink: dict[Path, Path]):
        for dest, src in files_to_symlink.items():
            dest.parent.mkdir(parents=True, exist_ok=True)

            if dest.is_symlink() and dest.resolve() == src.resolve():
                continue

            if dest.is_symlink():
                dest.unlink()
            elif dest.exists():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup = dest.with_name(f"{dest.name}.backup.{timestamp}")

                counter = 1
                while backup.exists():
                    backup = dest.with_name(f"{dest.name}.backup.{timestamp}_{counter}")
                    counter += 1

                dest.rename(backup)

            dest.symlink_to(src)

    def task_download_file(self, files_to_download: dict[Path, str]):
        for path, url in files_to_download.items():
            path.parent.mkdir(parents=True, exist_ok=True)

            with tempfile.TemporaryDirectory(dir=path.parent) as tmpdirname:
                temp_path = Path(tmpdirname) / path.name
                success = download_file(url, temp_path)

                if success and temp_path.exists() and temp_path.stat().st_size > 0:
                    temp_path.replace(path)
                else:
                    self.vm.validate(False, f"Failed to download from the url: {url}")

    def task_clone_repo(self, git_repo_to_clone: dict[Path, str]):
        for path, repo_url in git_repo_to_clone.items():
            try:
                with tempfile.TemporaryDirectory(dir=path.parent) as tmp:
                    temp_dir = Path(tmp)
                    # TODO: find if the function below clones to subfolder or the exact folder
                    clone_git_repo(repo_url, temp_dir)

                    path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(temp_dir), str(path))

            except Exception as e:
                self.vm.validate(False, f"Failed to clone repo: {repo_url}\n{e}")

    def task_unlink_symlinks(self, files_to_unlink: list[Path]):
        for symlink in files_to_unlink:
            symlink.unlink(missing_ok=True)

    def task_delete_files(self, files_to_delete: list[Path]):
        for file in files_to_delete:
            if file.is_dir():
                shutil.rmtree(file)
            else:
                file.unlink(missing_ok=True)

    def _create_renderables(
        self, title: str, mapping: dict[Path, Path] | dict[Path, str] | list[Path]
    ):
        text = Text()

        text.append(title + "\n")

        if isinstance(mapping, dict):
            for i, (src, dst) in enumerate(mapping.items()):
                if i:
                    text.append("\n")

                text.append(str(src), style="cyan")
                text.append(" -> ")
                text.append(str(dst), style="green")
        elif isinstance(mapping, list):
            for dst in mapping:
                text.append(str(dst) + "\n")

        text.overflow = "fold"
        return text

    # ╭─────────────────────────────────────────────────────────────────────────────╮
    # │ State                                                                       │
    # ╰─────────────────────────────────────────────────────────────────────────────╯
    def update_state(self):
        doc = document()

        if self.files_to_symlink:
            # Symlinks
            symlinks = table()
            for dest, src in self.files_to_symlink.items():
                symlinks[str(dest)] = str(src)

            doc["symlinks"] = symlinks

        if self.external_files:
            # External
            external = {}
            now = datetime.now(timezone.utc).isoformat()

            for dest, config in self.external_files.items():
                external[str(dest)] = {
                    "last_refreshed": now,
                    "type": config["type"],
                    "url": config["url"],
                }

            doc["external"] = external

        tmp = dotfile_state_file.with_suffix(".tmp")
        toml_to_file(tmp, doc)
        tmp.replace(dotfile_state_file)

    # ╭─────────────────────────────────────────────────────────────────────────────╮
    # │ Execution                                                                   │
    # ╰─────────────────────────────────────────────────────────────────────────────╯
    def execute(self):
        # ╭─────────────────────────────────────────────────────────────────────────╮
        # │ Symlink Diff                                                            │
        # ╰─────────────────────────────────────────────────────────────────────────╯
        to_symlink: dict[Path, Path] = {}
        to_unlink: list[Path] = []

        for dest, src in self.files_to_symlink.items():
            if dest not in self.managed_symlinks or self.managed_symlinks[dest] != src:
                to_symlink[dest] = src

        for dest in self.managed_symlinks:
            if dest not in self.files_to_symlink:
                if not self.vm.validate(
                    dest.is_symlink(),
                    f'Trying to remove a symlink but found real file: "{dest}"',
                ):
                    continue
                    # TODO: Currently user has not option other than to manually fix it in state file and path.
                    # Give user to remove regardless
                to_unlink.append(dest)

        if to_symlink:
            self.tm.add_task(
                self.task_symlink_files,
                self._create_renderables("Symlink the following files:", to_symlink),
                to_symlink,
            )

        if to_unlink:
            self.tm.add_task(
                self.task_unlink_symlinks,
                self._create_renderables(
                    "Unlink the following files that are no longer managed:", to_unlink
                ),
                to_unlink,
            )

        # ╭─────────────────────────────────────────────────────────────────────────╮
        # │ External File Diff                                                      │
        # ╰─────────────────────────────────────────────────────────────────────────╯
        to_download: dict[Path, str] = {}
        to_clone: dict[Path, str] = {}
        to_delete: list[Path] = []

        now = datetime.now(timezone.utc)

        for dest, config in self.external_files.items():
            state = self.managed_externals.get(dest)

            should_refresh = True
            if state:
                if (
                    state.get("url") != config["url"]
                    or state.get("type") != config["type"]
                ):
                    should_refresh = True
                else:
                    try:
                        period = parse_refresh_period(config["refresh_period"])
                        last = datetime.fromisoformat(state["last_refreshed"])
                        should_refresh = now - last >= period
                    except Exception:
                        should_refresh = True

            if not should_refresh:
                continue

            if config["type"] == "file":
                to_download[dest] = config["url"]
            else:
                to_clone[dest] = config["url"]

        for dest in self.managed_externals:
            if dest not in self.external_files:
                to_delete.append(dest)

        if to_download:
            self.tm.add_task(
                self.task_download_file,
                self._create_renderables("Download external files:", to_download),
                to_download,
            )

        if to_clone:
            self.tm.add_task(
                self.task_clone_repo,
                self._create_renderables("Clone git repo", to_clone),
                to_clone,
            )
        if to_delete:
            self.tm.add_task(
                self.task_delete_files,
                self._create_renderables("Remove unmanaged external files", to_delete),
                to_delete,
            )

        # ╭─────────────────────────────────────────────────────────────────────────╮
        # │ State                                                                   │
        # ╰─────────────────────────────────────────────────────────────────────────╯
        if any([to_symlink, to_unlink, to_download, to_clone, to_delete]):
            self.tm.add_task(self.update_state, "Update dotfiles state.")
