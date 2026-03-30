import argparse
import os
from urllib.parse import urlparse

from rich.traceback import install

from pacs.initialize import run_init
from pacs.sync import run_sync
from pacs.utils import is_arch_linux

install()


def valid_url(value: str) -> str:
    """
    Validate that a given string is a properly formed url.

    Args:
    -----
        value: The input string to validate as a url.

    Returns:
    --------
        The original URL string if it is valid.

    Raises:
    -------
        argparse.ArgumentTypeError: If the input is not a valid url.
    """
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        raise argparse.ArgumentTypeError("Invalid URL")
    return value


def parse_arguments() -> argparse.Namespace:
    """
    Parse arguments.

    Returns
    -------
    argparse.Namespace
        Parsed argument:
        - path (str): Path to an image file or a directory.
    """
    parser = argparse.ArgumentParser(
        prog="pacs", description="Declarative Arch Linux Config in Python"
    )

    subparsers = parser.add_subparsers(dest="command")

    # init command
    init_parser = subparsers.add_parser("init", help="Initialize the config")
    init_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform a dry run without making changes",
    )
    init_parser.add_argument(
        "--url",
        type=valid_url,
        help="git url to fetch",
    )

    # sync command
    sync_parser = subparsers.add_parser("sync", help="Sync config")
    sync_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform a dry run without making changes",
    )

    return parser.parse_args()


def main():
    if os.geteuid() == 0:
        raise SystemExit(
            "Do not run this script as root. Run as a normal user with sudo access.\nPrivilege will be escalated when necessary."
        )

    if not is_arch_linux():
        raise RuntimeError("This program only supports Arch Linux.")

    args = parse_arguments()
    if args.command == "init":
        run_init(args)
    elif args.command == "sync":
        run_sync(args)
    else:
        print("Invalid command. Use --help to see available commands.")


if __name__ == "__main__":
    main()
