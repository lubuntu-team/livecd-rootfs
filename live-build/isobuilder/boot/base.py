"""Base classes and helper functions for boot configuration."""

import pathlib
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod

from ..builder import Logger
from ..apt_state import AptStateManager


def default_kernel_params(project: str) -> str:
    if project == "ubuntukylin":
        return (
            "file=/cdrom/preseed/ubuntu.seed locale=zh_CN "
            "keyboard-configuration/layoutcode?=cn quiet splash --- "
        )
    if project == "ubuntu-server":
        return " --- "
    else:
        return " --- quiet splash"


class BaseBootConfigurator(ABC):
    """Abstract base class for architecture-specific boot configurators.

    Subclasses must implement:
    - extract_files(): Download and extract bootloader packages
    - mkisofs_opts(): Return mkisofs command-line options
    """

    def __init__(
        self,
        logger: Logger,
        apt_state: AptStateManager,
        iso_root: pathlib.Path,
    ) -> None:
        self.logger = logger
        self.apt_state = apt_state
        self.iso_root = iso_root

    def create_dirs(self, workdir):
        self.scratch = workdir.joinpath("boot-stuff")
        self.scratch.mkdir(exist_ok=True)
        self.boot_tree = self.scratch.joinpath("cd-boot-tree")

    def download_and_extract_package(
        self, pkg_name: str, target_dir: pathlib.Path
    ) -> None:
        """Download a Debian package and extract its contents to target directory."""
        self.logger.log(f"downloading and extracting {pkg_name}")
        target_dir.mkdir(exist_ok=True, parents=True)
        with tempfile.TemporaryDirectory() as tdir_str:
            tdir = pathlib.Path(tdir_str)
            self.apt_state.download_direct(pkg_name, tdir)
            [deb] = tdir.glob("*.deb")
            dpkg_proc = subprocess.Popen(
                ["dpkg-deb", "--fsys-tarfile", deb], stdout=subprocess.PIPE
            )
            tar_proc = subprocess.Popen(
                ["tar", "xf", "-", "-C", target_dir], stdin=dpkg_proc.stdout
            )
            assert dpkg_proc.stdout is not None
            dpkg_proc.stdout.close()
            tar_proc.communicate()

    def copy_grub_modules(
        self, src_dir: pathlib.Path, dest_dir: pathlib.Path, extensions: list[str]
    ) -> None:
        """Copy GRUB module files matching given extensions from src to dest."""
        for ext in extensions:
            for file in src_dir.glob(ext):
                shutil.copy(file, dest_dir)

    @abstractmethod
    def extract_files(self) -> None:
        """Download and extract bootloader packages to the boot tree.

        Each architecture must implement this to set up its specific bootloader files.
        """
        ...

    @abstractmethod
    def mkisofs_opts(self) -> list[str | pathlib.Path]:
        """Return mkisofs command-line options for this architecture.

        Returns:
            List of command-line options to pass to mkisofs/xorriso.
        """
        ...

    def post_process_iso(self, iso_path: pathlib.Path) -> None:
        """Post-process the ISO image after xorriso creates it."""

    def make_bootable(
        self,
        workdir: pathlib.Path,
        project: str,
        capproject: str,
        subarch: str,
        hwe: bool,
    ) -> None:
        """Make the ISO bootable by extracting bootloader files."""
        self.project = project
        self.humanproject = capproject.replace("-", " ")
        self.subarch = subarch
        self.hwe = hwe
        self.create_dirs(workdir)
        with self.logger.logged("configuring boot"):
            self.extract_files()
