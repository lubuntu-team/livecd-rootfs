import dataclasses
import os
import pathlib
import shutil
import subprocess
from typing import Iterator


@dataclasses.dataclass
class PackageInfo:
    package: str
    filename: str
    architecture: str
    version: str

    @property
    def spec(self) -> str:
        return f"{self.package}:{self.architecture}={self.version}"


def check_proc(proc, ok_codes=(0,)) -> None:
    proc.wait()
    if proc.returncode not in ok_codes:
        raise Exception(f"{proc} failed")


class AptStateManager:
    """Maintain and use an apt state directory to access package info and debs."""

    def __init__(self, logger, series: str, apt_dir: pathlib.Path):
        self.logger = logger
        self.series = series
        self.apt_root = apt_dir.joinpath("root")
        self.apt_conf_path = apt_dir.joinpath("apt.conf")

    def _apt_env(self) -> dict[str, str]:
        return dict(os.environ, APT_CONFIG=str(self.apt_conf_path))

    def setup(self, chroot: pathlib.Path):
        """Set up the manager by copying the apt configuration from `chroot`."""
        for path in "etc/apt", "var/lib/apt":
            tgt = self.apt_root.joinpath(path)
            tgt.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(chroot.joinpath(path), tgt, ignore_dangling_symlinks=True)
        self.apt_conf_path.write_text(f'Dir "{self.apt_root}/"; \n')
        with self.logger.logged("updating apt indices"):
            self.logger.run(["apt-get", "update"], env=self._apt_env())

    def show(self, pkgs: list[str]) -> Iterator[PackageInfo]:
        """Return information about the binary packages named by `pkgs`.

        Parses apt-cache output, which uses RFC822-like format: field names
        followed by ": " and values, with multi-line values indented with
        leading whitespace. We skip continuation lines (starting with space)
        since PackageInfo only needs single-line fields.

        The `fields` set (derived from PackageInfo's dataclass fields) acts as
        a filter - we only extract fields we care about, ignoring others like
        Description.
        """
        proc = subprocess.Popen(
            ["apt-cache", "-o", "APT::Cache::AllVersions=0", "show"] + pkgs,
            stdout=subprocess.PIPE,
            encoding="utf-8",
            env=self._apt_env(),
        )
        assert proc.stdout is not None
        fields = {f.name for f in dataclasses.fields(PackageInfo)}
        params: dict[str, str] = {}
        for line in proc.stdout:
            if line == "\n":
                yield PackageInfo(**params)
                params = {}
                continue
            if line.startswith(" "):
                continue
            field, value = line.split(": ", 1)
            field = field.lower()
            if field in fields:
                params[field] = value.strip()
        check_proc(proc)
        if params:
            yield PackageInfo(**params)

    def download(self, rootdir: pathlib.Path, pkg_info: PackageInfo) -> None:
        """Download the package specified by `pkg_info` under `rootdir`.

        The package is saved to the same path under `rootdir` as it is
        at in the archive it comes from.
        """
        target_dir = rootdir.joinpath(pkg_info.filename).parent
        target_dir.mkdir(parents=True, exist_ok=True)
        self.download_direct(pkg_info.spec, target_dir)

    def download_direct(self, spec: str, target: pathlib.Path) -> None:
        """Download the package specified by spec to target directory.

        The package is downloaded using apt-get download and saved directly
        in the target directory.
        """
        self.logger.run(
            ["apt-get", "download", spec],
            cwd=target,
            check=True,
            env=self._apt_env(),
        )

    def in_release_path(self) -> pathlib.Path:
        """Return the path to the InRelease file.

        This ignores all but the first path.
        Will raise Error if there isn't at least one match.
        """
        [path] = self.apt_root.joinpath("var/lib/apt/lists").glob(
            f"*ubuntu.com*_dists_{self.series}_InRelease"
        )
        return path
