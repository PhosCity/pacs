import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from tomlkit import document, item, table

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

dotfile_state_file = common_vars.state_dir / "managed_dotfiles.toml"


@dataclass
class ExternalFiles:
    type: Literal["file", "git-repo"]
    url: str
    destination: Path
    refresh_period: str


@dataclass
class ExternalState:
    last_refreshed: datetime | None = None
    destination: Path | None = None


@dataclass
class RemovalAction:
    path: Path
    kind: Literal["symlink", "external"]


class DotfileManager:
    def __init__(self, vm: ValidationManager):
        self.files_to_symlink: dict[Path, set[Path]] = {}

        self.external_files: dict[str, ExternalFiles] = {}
        self.external_state: dict[str, ExternalState] = {}

        self.managed_symlinks: dict[str, list[str]] = {}
        self.managed_external_state: dict[str, dict[str, str]] = {}

        if dotfile_state_file.exists():
            state = parse_toml_file(dotfile_state_file)

            for key, value in state.items():
                if not vm.validate(
                    key in ["symlinks", "external"],
                    f"Unknown key in dotfile state: {key}",
                ):
                    continue

                if key == "symlinks":
                    self.managed_symlinks = value

                elif key == "external":
                    self.managed_external_state = value

                    for name, ext in value.items():
                        last = ext.get("lastRefreshed")
                        dest = ext.get("destination")

                        last_refreshed = None
                        if last:
                            try:
                                last_refreshed = datetime.fromisoformat(last)
                            except Exception:
                                pass

                        self.external_state[name] = ExternalState(
                            last_refreshed=last_refreshed,
                            destination=Path(dest).expanduser() if dest else None,
                        )

    def add_symlink(
        self, dotfiles: dict[Path, list], module_file: Path, vm: ValidationManager
    ) -> None:
        base = module_file.parent

        for entries in dotfiles.values():
            for mapping in entries:
                for source, destination in mapping.items():
                    source = resolve_path(source, base)
                    destination = resolve_path(destination, base)

                    if not vm.validate(
                        source.exists(),
                        f'Source not found:\n "{source}" in module "{module_file.stem}"',
                    ):
                        continue

                    self.files_to_symlink.setdefault(source, set()).add(destination)

    def add_external(
        self, external: dict, module_file: Path, vm: ValidationManager
    ) -> None:
        for key, value in external.items():
            ext_type = value.get("type")
            url = value.get("url")
            refresh = value.get("refreshPeriod")
            destination = value.get("destination")

            if not vm.validate(
                ext_type and url and refresh and destination,
                f"Incomplete external config: {key} in {module_file.stem}",
            ):
                continue

            if not vm.validate(
                ext_type in ["file", "git-repo"],
                f"Incomplete external config: {key} in {module_file.stem}",
            ):
                continue

            if not vm.validate(
                url_is_valid(url),
                f"Invalid url in module {module_file.stem}: {url}",
            ):
                continue

            config = ExternalFiles(
                type=ext_type,
                url=url,
                destination=Path(destination).expanduser(),
                refresh_period=refresh,
            )

            self.external_files[key] = config

            # Ensure state entry exists
            if key not in self.external_state:
                self.external_state[key] = ExternalState()

            # Always update destination for cleanup correctness
            self.external_state[key].destination = config.destination

    def update_dotfiles_state_file(self):
        doc = document()

        # Symlinks
        symlinks = table()
        for src, dests in self.files_to_symlink.items():
            items = item([str(d) for d in dests])
            if len(dests) > 1:
                items.multiline(True)
            symlinks[str(src)] = items

        doc["symlinks"] = symlinks

        # External
        doc["external"] = {
            key: {
                "lastRefreshed": state.last_refreshed.isoformat()
                if state.last_refreshed
                else None,
                "destination": str(state.destination) if state.destination else None,
            }
            for key, state in self.external_state.items()
        }

        tmp = dotfile_state_file.with_suffix(".tmp")
        toml_to_file(tmp, doc)
        tmp.replace(dotfile_state_file)

    def _diff_symlinks(self):
        to_create = []
        to_remove = []

        desired = {src: set(dests) for src, dests in self.files_to_symlink.items()}
        managed = {
            Path(src): {Path(d) for d in dests}
            for src, dests in self.managed_symlinks.items()
        }

        for src, dests in desired.items():
            for dest in dests:
                if dest not in managed.get(src, set()):
                    to_create.append((src, dest))

        for src, dests in managed.items():
            for dest in dests:
                if dest not in desired.get(src, set()):
                    to_remove.append(RemovalAction(dest, "symlink"))

        return to_create, to_remove

    def _plan_external_actions(self, now: datetime):
        to_fetch = []
        to_remove = []

        # Fetch/update
        for key, config in self.external_files.items():
            state = self.external_state.get(key)

            should_refresh = True

            if state and state.last_refreshed:
                try:
                    period = parse_refresh_period(config.refresh_period)
                    should_refresh = now - state.last_refreshed >= period
                except Exception:
                    should_refresh = True

            if should_refresh:
                to_fetch.append((key, config))

        # Removal
        for key, state in self.external_state.items():
            if key not in self.external_files and state.destination:
                to_remove.append(RemovalAction(state.destination, "external"))

        return to_fetch, to_remove

    def execute(self, tm: TaskManager, vm: ValidationManager):
        now = datetime.now(timezone.utc)

        removal_actions: list[RemovalAction] = []

        # Symlinks
        to_create, to_remove = self._diff_symlinks()

        for source, destination in to_create:
            if destination.is_symlink() and destination.resolve() == source.resolve():
                continue

            tm.add_task(
                self._symlink_files,
                f"Symlink dotfile.\n {source}\nto\n {destination}",
                source,
                destination,
            )

        removal_actions.extend(to_remove)

        # External
        to_fetch, to_remove_ext = self._plan_external_actions(now)

        for key, config in to_fetch:
            self.external_state[key].last_refreshed = now

            if config.type == "file":
                tm.add_task(
                    self._download_file,
                    f"Download file from the url\n {config.url} to location\n {config.destination}",
                    config.url,
                    config.destination,
                    vm,
                )
            else:
                tm.add_task(
                    self._clone_repo,
                    f"Clone repo from the url\n {config.url} to location\n {config.destination}",
                    config.url,
                    config.destination,
                    vm,
                )

        removal_actions.extend(to_remove_ext)

        # Removal
        for action in removal_actions:
            path = action.path

            if not path.exists() and not path.is_symlink():
                continue

            if action.kind == "symlink":
                if not vm.validate(
                    path.is_symlink(), f"Expected symlink but found real file: {path}"
                ):
                    continue

            tm.add_task(self._remove_path, f"Remove unmanaged file at\n {path}", path)

        # Save state
        if self.files_to_symlink or self.external_files:
            tm.add_task(self.update_dotfiles_state_file, "Update dotfile state")

    def _symlink_files(self, source: Path, target: Path) -> None:
        """
        Safely create or update a symbolic link.

        - If `target` does not exist:
            Create a new symlink pointing to `source`.
        - If `target` is already a symlink:
            - replace it with a new symlink to `source`.
        - If `target` exists and is not a symlink (file or directory):
            - Rename it to a timestamped backup in the same directory.
            - Then create a symlink at `target` pointing to `source`.

        Backups:
            Existing files/directories are renamed using the pattern:
                "<name>.backup.<YYYYMMDD_HHMMSS>[_N]"
            where N is added if needed to avoid overwriting an existing backup.

        Args:
            source (Path | str): The source path the symlink should point to.
            target (Path | str): The destination path where the symlink will be created.
                Parent directories are created automatically if needed.
        """
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.is_symlink():
            if target.resolve() == source.resolve():
                return

            target.unlink()
            target.symlink_to(source)
            return

        if target.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = target.with_name(f"{target.name}.backup.{timestamp}")

            counter = 1
            while backup.exists():
                backup = target.with_name(f"{target.name}.backup.{timestamp}_{counter}")
                counter += 1

            target.rename(backup)

        target.symlink_to(source)

    def _remove_path(self, path: Path) -> None:
        """
        Remove files/folders that are no longer managed without touching the original source file.

        Parameters
        ----------
        file_to_remove : Path
        """
        if path.is_symlink():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

    def _download_file(self, url: str, final_path: Path, vm: ValidationManager):
        """
        Download a file to a temporary location first, then move to final_path.

        Args:
            url: File URL
            final_path: Destination path
        """
        final_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(delete=False, dir=final_path.parent) as tmp:
            temp_path = Path(tmp.name)

        success = download_file(url, temp_path)

        if success and temp_path.exists():
            temp_path.replace(final_path)
        else:
            temp_path.unlink(missing_ok=True)
            vm.validate(False, f"Failed to download from the url: {url}")

    def _clone_repo(self, repo_url: str, final_path: Path, vm: ValidationManager):
        """
        Clone a git repo to a temporary location first, then move to final_path.

        Args:
            repo_url: Git repository URL
            final_path: Destination directory
            vm: ValidationManager
        """
        try:
            with tempfile.TemporaryDirectory(dir=final_path.parent) as tmp:
                temp_dir = Path(tmp)
                clone_git_repo(repo_url, temp_dir)

                final_path.parent.mkdir(parents=True, exist_ok=True)

                if final_path.exists():
                    self._remove_path(final_path)

                shutil.move(str(temp_dir), str(final_path))

        except Exception as e:
            vm.validate(False, f"Failed to clone repo: {repo_url}\n{e}")
