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

    def generate_grub_config(self) -> None:
        """Generate grub.cfg for PPC64EL."""
        kernel_params = default_kernel_params(self.project)

        grub_cfg = self.iso_root.joinpath("boot", "grub", "grub.cfg")

        # Write common GRUB header
        self.write_grub_header(grub_cfg)

        # Main menu entry
        with grub_cfg.open("a") as f:
            f.write(
                f"""menuentry "Try or Install {self.humanproject}" {{
\tset gfxpayload=keep
\tlinux\t/casper/vmlinux quiet {kernel_params}
\tinitrd\t/casper/initrd
}}
"""
            )

        # HWE kernel option if available
        self.write_hwe_menu_entry(
            grub_cfg, "vmlinux", kernel_params, extra_params="quiet "
        )
