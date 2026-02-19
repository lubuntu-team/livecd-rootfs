"""GRUB boot configuration for multiple architectures."""

import pathlib
import shutil
from abc import abstractmethod

from .base import BaseBootConfigurator


def copy_grub_common_files(grub_pkg_dir: pathlib.Path, iso_root: pathlib.Path) -> None:
    fonts_dir = iso_root.joinpath("boot", "grub", "fonts")
    fonts_dir.mkdir(parents=True, exist_ok=True)

    src = grub_pkg_dir.joinpath("usr", "share", "grub", "unicode.pf2")
    dst = fonts_dir.joinpath("unicode.pf2")
    shutil.copy(src, dst)


def copy_grub_modules(
    grub_pkg_dir: pathlib.Path,
    iso_root: pathlib.Path,
    grub_target: str,
    patterns: list[str],
) -> None:
    """Copy GRUB module files matching given patterns from src to dest."""
    src_dir = grub_pkg_dir.joinpath("usr", "lib", "grub", grub_target)
    dest_dir = iso_root.joinpath("boot", "grub", grub_target)
    dest_dir.mkdir(parents=True, exist_ok=True)

    for pat in patterns:
        for file in src_dir.glob(pat):
            shutil.copy(file, dest_dir)


class GrubBootConfigurator(BaseBootConfigurator):
    """Base class for architectures that use GRUB (all except S390X).

    Common GRUB functionality shared across AMD64, ARM64, PPC64EL, and RISC-V64.
    Subclasses must implement generate_grub_config().
    """

    def grub_header(self, include_loadfont: bool = True) -> str:
        """Return common GRUB config header (timeout, colors).

        Args:
            include_loadfont: Whether to include 'loadfont unicode'
                              (not needed for RISC-V)
        """
        result = "set timeout=30\n\n"
        if include_loadfont:
            result += "loadfont unicode\n\n"
        result += """\
set menu_color_normal=white/black
set menu_color_highlight=black/light-gray

"""
        return result

    def hwe_menu_entry(
        self,
        kernel_name: str,
        kernel_params: str,
        extra_params: str = "",
    ) -> str:
        """Return HWE kernel menu entry if HWE is enabled.

        Args:
            kernel_name: Kernel binary name (vmlinuz or vmlinux)
            kernel_params: Kernel parameters to append
            extra_params: Additional parameters (e.g., console=tty0, $cmdline)
        """
        if not self.hwe:
            return ""
        return f"""\
menuentry "{self.humanproject} with the HWE kernel" {{
    set gfxpayload=keep
    linux /casper/hwe-{kernel_name} {extra_params}{kernel_params}
    initrd /casper/hwe-initrd
}}
"""

    @abstractmethod
    def generate_grub_config(self) -> str:
        """Generate grub.cfg content.

        Each GRUB-based architecture must implement this to return the
        GRUB configuration.
        """
        ...

    def make_bootable(
        self,
        workdir: pathlib.Path,
        project: str,
        capproject: str,
        subarch: str,
        hwe: bool,
    ) -> None:
        """Make the ISO bootable by extracting files and generating GRUB config."""
        super().make_bootable(workdir, project, capproject, subarch, hwe)
        with self.logger.logged("generating grub config"):
            content = self.generate_grub_config()
            grub_dir = self.iso_root.joinpath("boot", "grub")
            grub_dir.mkdir(parents=True, exist_ok=True)
            grub_dir.joinpath("grub.cfg").write_text(content)
