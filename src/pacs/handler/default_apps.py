from pathlib import Path

from pacs.manager.validation_manager import ValidationManager
from pacs.manager.task_manager import TaskManager
from pacs.utils import XDGType, get_xdg_dir

mimetype_map = {
    "browser": [
        "text/html",
        "x-scheme-handler/http",
        "x-scheme-handler/https",
    ],
    "text_editor": [
        "text/plain",  # .txt
        "text/markdown",  # .md
        "text/html",  # .html
        "text/css",  # .css
        "text/csv",  # .csv
        "application/json",  # .json
        "application/xml",  # .xml
        "application/x-yaml",  # .yaml/.yml
    ],
    "file_manager": [
        "inode/directory",
    ],
    "video_player": [
        "video/mp4",  # .mp4
        "video/x-matroska",  # .mkv
        "video/webm",  # .webm
        "video/x-msvideo",  # .avi
        "video/quicktime",  # .mov
    ],
    "audio_player": [
        "audio/mpeg",  # .mp3
        "audio/wav",  # .wav
        "audio/flac",  # .flac
        "audio/ogg",  # .ogg
        "audio/mp4",  # .m4a
        "audio/aac",  # .aac
    ],
    "image_viewer": [
        "image/png",  # .png
        "image/jpeg",  # .jpg/.jpeg
        "image/gif",  # .gif
        "image/webp",  # .webp
        "image/svg+xml",  # .svg
        "image/bmp",  # .bmp
    ],
}


def find_desktop_file(name: str) -> bool:
    # https://wiki.archlinux.org/title/Desktop_entries#Desktop_entries_for_applications
    xdg_dirs = [
        Path.home() / ".local/share/applications",
        Path("/usr/local/share/applications"),
        Path("/usr/share/applications"),
    ]

    for directory in xdg_dirs:
        path = directory / name
        if path.is_file():
            return True

    return False


def handle_default_apps(
    associations: dict, vm: ValidationManager, tm: TaskManager
) -> None:
    """
    Build mimeapps.list content.
    """

    output_path = get_xdg_dir(XDGType.CONFIG) / "mimeapps.list"

    sections = {
        "Default Applications": {},
        "Added Associations": {},
        "Removed Associations": {},
    }

    def populate(section_name: str, data: dict | None):
        if not data:
            return

        section = sections[section_name]

        for key, value in sorted(data.items()):
            vm.validate(
                find_desktop_file(value),
                f"The desktop file for {value} does not exist.",
            )
            mimetypes = mimetype_map.get(key) or [key]

            if isinstance(value, list):
                value = ";".join(value) + ";"

            for mimetype in mimetypes:
                section[mimetype] = value

    if default := associations.get("default"):
        populate("Default Applications", default)
    if added_associations := associations.get("added-associations"):
        populate("Added Associations", added_associations)
    if removed_associations := associations.get("removed-associations"):
        populate("Removed Associations", removed_associations)

    # Remove empty sections
    sections = {k: v for k, v in sections.items() if v}
    if not sections:
        return

    lines = []
    for section_name, entries in sections.items():
        lines.append(f"[{section_name}]")
        for mime, val in sorted(entries.items()):
            lines.append(f"{mime}={val}")
        lines.append("")

    current_mimeapps = output_path.read_text()
    new_mimeapps = "\n".join(lines)

    if new_mimeapps.strip() != current_mimeapps.strip():
        tm.add_task(output_path.write_text, "Recreate mime types", new_mimeapps)
