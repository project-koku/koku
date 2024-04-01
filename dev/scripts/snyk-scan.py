#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK
import argparse
import dataclasses
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from urllib.error import HTTPError

HAS_ARGCOMPLETE = True
try:
    import argcomplete
except ImportError:
    HAS_ARGCOMPLETE = False


@dataclasses.dataclass(frozen=True)
class SnykDownloader:
    destination: Path
    darwin: str = "https://static.snyk.io/cli/latest/snyk-macos"
    linux: str = "https://static.snyk.io/cli/latest/snyk-linux"
    linux_x86_64: str = "https://static.snyk.io/cli/latest/snyk-linux"
    linux_arm64: str = "https://static.snyk.io/cli/latest/snyk-linux-arm64"
    linux_aarch64: str = "https://static.snyk.io/cli/latest/snyk-linux-arm64"

    _system: str = dataclasses.field(default=platform.system(), init=False)
    _machine: str = dataclasses.field(default=platform.machine(), init=False)

    @property
    def url(self) -> str:
        return getattr(self, f"{self._system}_{self._machine}".lower(), getattr(self, f"{self._system.lower()}", None))

    def download(self, force_download=False) -> Path:
        snyk_binary_path = Path(self.destination).expanduser().joinpath("snyk")
        if force_download or not snyk_binary_path.exists():
            if self.url is None:
                sys.exit(f"No snyk executable available for '{self._system} {self._machine}'.")

            print(f"Downloading snyk to {snyk_binary_path}...")
            try:
                with urllib.request.urlopen(self.url) as response:
                    data = response.read()
            except HTTPError as err:
                sys.exit(f"Failed to download snyx from {self.url}: {err}")

            if not snyk_binary_path.parent.is_dir():
                snyk_binary_path.parent.mkdir(parents=True)

            snyk_binary_path.touch(mode=0o0755, exist_ok=True)
            snyk_binary_path.write_bytes(data)

        return snyk_binary_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--download-dest", "-d", default="~/.cache/snyk", type=Path, help="Directory to download snyk")
    parser.add_argument("--severity-threshold", default="medium")
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument("path", nargs="?", default="", help="Path to scan")

    if HAS_ARGCOMPLETE:
        argcomplete.autocomplete(parser)

    return parser.parse_args()


def check_auth(snyk_binary: Path) -> None:
    # Check for token in the environment
    if os.environ.get("SNYK_TOKEN"):
        return

    # Fallback to looking for a config file
    snyk_config = Path("~/.config/configstore/snyk.json").expanduser()
    if not snyk_config.exists():
        print("No snyk token found. Authenticating...")
        subprocess.run([snyk_binary, "auth"])


def main() -> None:
    args = parse_args()

    if not (snyk_binary := shutil.which("snyk")):
        snyk_binary = SnykDownloader(args.download_dest).download(args.force_download)

    check_auth(snyk_binary)

    cmd = [snyk_binary, "code", "test", f"--severity-threshold={args.severity_threshold}"]
    suffix = "..."
    if args.path:
        cmd.append(args.path)
        suffix = f" {args.path}{suffix}"

    print(f"Scanning{suffix}")
    subprocess.run(cmd)


if __name__ == "__main__":
    main()
