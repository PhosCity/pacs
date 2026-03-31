from datetime import datetime
from pathlib import Path

from tomlkit import document, item, table

import pacs.common_vars as common_vars
from pacs.manager.task_manager import TaskManager
from pacs.manager.validation_manager import ValidationManager
from pacs.utils import parse_toml_file, toml_to_file

dotfile_state_file = common_vars.state_dir / "managed_dotfiles.toml"


class DotfileManager:
    def __init__(self, vm: ValidationManager):
        # A path is paired with a list because same file can be symlinked to various places
        self.files_to_symlink: dict[Path, list[Path]] = {}
        self.external_files: dict[str, dict[str, str]] = {}

        # Get the list of all managed dotfiles
        if not dotfile_state_file.exists():
            self.managed_symlinks: dict[str, list[str]] = {}
            self.managed_external_files: dict = {}
        else:
            dotfile_state_data = parse_toml_file(dotfile_state_file)
            for key, value in dotfile_state_data.items():
                if not vm.validate(
                    key in ["symlinks", "external"],
                    f"There is unknown key in the state file for services: {key}",
                ):
                    continue
                if key == "symlinks":
                    self.managed_symlinks: dict[str, list[str]] = value
                elif key == "external":
                    self.managed_external_files = value

    def add_symlink(
        self, dotfiles: dict[Path, list], module_file: Path, vm: ValidationManager
    ) -> None:
        for dot_type, dot_file in dotfiles.items():
            for dotfile in dot_file:
                for source, destination in dotfile.items():
                    source = Path(source).expanduser()
                    destination = Path(destination).expanduser()

                    # Convert relative paths to absolute
                    if not source.is_absolute():
                        source = (module_file.parent / source).resolve()
                    if not destination.is_absolute():
                        destination = (module_file.parent / destination).resolve()

                    # Check if the source file exists
                    if not vm.validate(
                        source.exists(),
                        f'Trying to symlink\n "{source}"\ndefined in module "{module_file.stem}" but file could not be found.',
                    ):
                        continue

                    if source not in self.files_to_symlink:
                        self.files_to_symlink[source] = []
                    self.files_to_symlink[source].append(destination)

    def update_dotfiles_state_file(self):
        doc = document()

        symlinks = table()

        for key, value in self.files_to_symlink.items():
            items = item([str(x) for x in value])
            if len(value) > 1:
                items.multiline(True)
            symlinks[str(key)] = items

        doc["symlinks"] = symlinks
        toml_to_file(dotfile_state_file, doc)

    def execute(self, tm: TaskManager, vm: ValidationManager):
        # Files to symlink
        for source, destination_list in self.files_to_symlink.items():
            for destination in destination_list:
                if destination.is_symlink():
                    # Skip if the symlink already points to the source
                    if destination.readlink() == source:
                        continue

                tm.add_task(
                    self._symlink_files,
                    f"Symlink dotfile.\n {source}\nto\n {destination}",
                    source,
                    destination,
                )

        # Files to unlink and remove
        files_to_remove = []
        for source, destination_list in self.managed_symlinks.items():
            source_path = Path(source)

            managed = {Path(d) for d in destination_list}
            current = {Path(d) for d in self.files_to_symlink.get(source_path, [])}

            to_remove = managed - current

            files_to_remove.extend(to_remove)

        for destination in files_to_remove:
            if not destination.exists() and not destination.is_symlink():
                continue

            if not vm.validate(
                destination.is_symlink(),
                f"The file at {destination} was expected to be a symlink but it was an actual file.",
            ):
                continue
            tm.add_task(
                self._remove_symlink,
                f"Remove unmanaged symlink\n {destination}",
                destination,
            )

        if self.files_to_symlink:
            tm.add_task(
                self.update_dotfiles_state_file,
                "Update dotfiles state.",
            )

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

        # If destination is already a  symlink
        if target.is_symlink():
            target.unlink()
            target.symlink_to(source)
            return

        # If destination file or folder exists, create a backup before symlinking
        if target.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = target.with_name(f"{target.name}.backup.{timestamp}")

            counter = 1
            while backup_path.exists():
                backup_path = target.with_name(
                    f"{target.name}.backup.{timestamp}_{counter}"
                )
                counter += 1

            target.rename(backup_path)

        # Create symlink
        target.symlink_to(source)

    def _remove_symlink(self, file_to_remove: Path) -> None:
        """
        Remove symlinked files that are no longer managed without touching the original source file.

        Parameters
        ----------
        file_to_remove : Path
        """

        file_to_remove.unlink()
