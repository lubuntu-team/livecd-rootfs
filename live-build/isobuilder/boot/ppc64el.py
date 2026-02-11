"""PowerPC 64-bit Little Endian architecture boot configuration."""

import pathlib
import shutil

from .grub import GrubBootConfigurator
from .base import default_kernel_params


class PPC64ELBootConfigurator(GrubBootConfigurator):
    """Boot setup for PowerPC 64-bit Little Endian architecture."""

    def mkisofs_opts(self) -> list[str | pathlib.Path]:
        """Return mkisofs options for PPC64EL."""
        # Add cd-boot-tree to the ISO
        return [self.boot_tree]

    def extract_files(self) -> None:
        """Download and extract bootloader packages for PPC64EL."""
        self.logger.log("extracting PPC64EL boot files")

        # Download and extract bootloader packages
        self.download_and_extract_package("grub2-common", self.grub_dir)
        self.download_and_extract_package("grub-ieee1275-bin", self.grub_dir)

        # Add common files for GRUB to tree
        self.setup_grub_common_files()

        # Add IEEE1275 ppc boot files
        ppc_dir = self.boot_tree.joinpath("ppc")
        ppc_dir.mkdir(parents=True, exist_ok=True)

        grub_boot_dir = self.boot_tree.joinpath("boot", "grub", "powerpc-ieee1275")
        grub_boot_dir.mkdir(parents=True, exist_ok=True)

        src_grub_dir = self.grub_dir.joinpath("usr", "lib", "grub", "powerpc-ieee1275")

        # Copy bootinfo.txt to ppc directory
        shutil.copy(
            src_grub_dir.joinpath("bootinfo.txt"), ppc_dir.joinpath("bootinfo.txt")
        )

        # Copy eltorito.elf to boot/grub as powerpc.elf
        shutil.copy(
            src_grub_dir.joinpath("eltorito.elf"),
            self.boot_tree.joinpath("boot", "grub", "powerpc.elf"),
        )

        # Copy GRUB modules
        self.copy_grub_modules(src_grub_dir, grub_boot_dir, ["*.mod", "*.lst"])

    def generate_grub_config(self) -> None:
        """Generate grub.cfg for PPC64EL."""
        kernel_params = default_kernel_params(self.project)

        grub_cfg = self.grub_dir.joinpath("grub.cfg")

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
