"""PowerPC 64-bit Little Endian architecture boot configuration."""

import pathlib
import shutil

from .grub import (
    copy_grub_common_files,
    copy_grub_modules,
    GrubBootConfigurator,
)
from .base import default_kernel_params


class PPC64ELBootConfigurator(GrubBootConfigurator):
    """Boot setup for PowerPC 64-bit Little Endian architecture."""

    def mkisofs_opts(self) -> list[str | pathlib.Path]:
        """Return mkisofs options for PPC64EL."""
        return []

    def extract_files(self) -> None:
        """Download and extract bootloader packages for PPC64EL."""
        self.logger.log("extracting PPC64EL boot files")

        grub_pkg_dir = self.scratch.joinpath("grub-pkg")

        # Download and extract bootloader packages
        self.download_and_extract_package("grub2-common", grub_pkg_dir)
        self.download_and_extract_package("grub-ieee1275-bin", grub_pkg_dir)

        # Add common files for GRUB to tree
        copy_grub_common_files(grub_pkg_dir, self.iso_root)

        # Add IEEE1275 ppc boot files
        ppc_dir = self.iso_root.joinpath("ppc")
        ppc_dir.mkdir()

        src_grub_dir = grub_pkg_dir.joinpath("usr", "lib", "grub", "powerpc-ieee1275")

        # Copy bootinfo.txt to ppc directory
        shutil.copy(
            src_grub_dir.joinpath("bootinfo.txt"), ppc_dir.joinpath("bootinfo.txt")
        )

        # Copy eltorito.elf to boot/grub as powerpc.elf
        shutil.copy(
            src_grub_dir.joinpath("eltorito.elf"),
            self.iso_root.joinpath("boot", "grub", "powerpc.elf"),
        )

        # Copy GRUB modules
        copy_grub_modules(
            grub_pkg_dir, self.iso_root, "powerpc-ieee1275", ["*.mod", "*.lst"]
        )

    def generate_grub_config(self) -> str:
        """Generate grub.cfg for PPC64EL."""
        kernel_params = default_kernel_params(self.project)

        result = self.grub_header()

        # Main menu entry
        result += f"""\
menuentry "Try or Install {self.humanproject}" {{
    set gfxpayload=keep
    linux /casper/vmlinux quiet {kernel_params}
    initrd /casper/initrd
}}
"""

        # HWE kernel option if available
        result += self.hwe_menu_entry("vmlinux", kernel_params, extra_params="quiet ")

        return result
