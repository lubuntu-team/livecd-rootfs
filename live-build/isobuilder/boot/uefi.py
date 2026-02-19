"""UEFI boot configuration for AMD64 and ARM64 architectures."""

import pathlib
import shutil

from ..builder import Logger
from .grub import copy_grub_common_files, GrubBootConfigurator


def copy_signed_shim_grub(
    shim_pkg_dir: pathlib.Path,
    grub_pkg_dir: pathlib.Path,
    efi_suffix: str,
    grub_target: str,
    iso_root: pathlib.Path,
) -> None:
    efi_boot_dir = iso_root.joinpath("EFI", "boot")
    efi_boot_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy(
        shim_pkg_dir.joinpath(
            "usr", "lib", "shim", f"shim{efi_suffix}.efi.signed.latest"
        ),
        efi_boot_dir.joinpath(f"boot{efi_suffix}.efi"),
    )
    shutil.copy(
        shim_pkg_dir.joinpath("usr", "lib", "shim", f"mm{efi_suffix}.efi"),
        efi_boot_dir.joinpath(f"mm{efi_suffix}.efi"),
    )
    shutil.copy(
        grub_pkg_dir.joinpath(
            "usr",
            "lib",
            "grub",
            f"{grub_target}-efi-signed",
            f"gcd{efi_suffix}.efi.signed",
        ),
        efi_boot_dir.joinpath(f"grub{efi_suffix}.efi"),
    )

    grub_boot_dir = iso_root.joinpath("boot", "grub", f"{grub_target}-efi")
    grub_boot_dir.mkdir(parents=True, exist_ok=True)

    src_grub_dir = grub_pkg_dir.joinpath("usr", "lib", "grub", f"{grub_target}-efi")
    for mod_file in src_grub_dir.glob("*.mod"):
        shutil.copy(mod_file, grub_boot_dir)
    for lst_file in src_grub_dir.glob("*.lst"):
        shutil.copy(lst_file, grub_boot_dir)


def create_eltorito_esp_image(
    logger: Logger, iso_root: pathlib.Path, target_file: pathlib.Path
) -> None:
    logger.log("creating El Torito ESP image")
    efi_dir = iso_root.joinpath("EFI")

    # Calculate size: du -s --apparent-size --block-size=1024 + 1024
    result = logger.run(
        ["du", "-s", "--apparent-size", "--block-size=1024", efi_dir],
        capture_output=True,
        text=True,
        check=True,
    )
    size_kb = int(result.stdout.split()[0]) + 1024

    # Create filesystem: mkfs.msdos -n ESP -C -v
    logger.run(
        ["mkfs.msdos", "-n", "ESP", "-C", "-v", target_file, str(size_kb)],
        check=True,
    )

    # Copy files: mcopy -s -i target_file EFI ::/.
    logger.run(["mcopy", "-s", "-i", target_file, efi_dir, "::/."], check=True)


class UEFIBootConfigurator(GrubBootConfigurator):
    """Base class for UEFI-based architectures (AMD64, ARM64).

    Subclasses should set:
    - efi_suffix: EFI binary suffix (e.g., "x64", "aa64")
    - grub_target: GRUB target name (e.g., "x86_64", "arm64")
    """

    # Subclasses must override these
    efi_suffix: str = ""
    grub_target: str = ""
    arch: str = ""

    def get_uefi_grub_packages(self) -> list[str]:
        """Return list of UEFI GRUB packages to download."""
        return [
            "grub2-common",
            f"grub-efi-{self.arch}-bin",
            f"grub-efi-{self.arch}-signed",
        ]

    def extract_uefi_files(self) -> None:
        """Extract common UEFI files to boot tree."""

        shim_pkg_dir = self.scratch.joinpath("shim-pkg")
        grub_pkg_dir = self.scratch.joinpath("grub-pkg")

        # Download UEFI packages
        self.download_and_extract_package("shim-signed", shim_pkg_dir)
        for pkg in self.get_uefi_grub_packages():
            self.download_and_extract_package(pkg, grub_pkg_dir)

        # Add common files for GRUB to tree
        copy_grub_common_files(grub_pkg_dir, self.iso_root)

        # Add EFI GRUB to tree
        copy_signed_shim_grub(
            shim_pkg_dir,
            grub_pkg_dir,
            self.efi_suffix,
            self.grub_target,
            self.iso_root,
        )

        # Create ESP image for El-Torito catalog and hybrid boot
        create_eltorito_esp_image(
            self.logger, self.iso_root, self.scratch.joinpath("cd-boot-efi.img")
        )

    def uefi_menu_entries(self) -> str:
        """Return UEFI firmware menu entries."""
        return """\
menuentry 'Boot from next volume' {
    exit 1
}
menuentry 'UEFI Firmware Settings' {
    fwsetup
}
"""

    def get_uefi_mkisofs_opts(self) -> list[str | pathlib.Path]:
        """Return common UEFI mkisofs options."""
        # To make our ESP / El-Torito image compliant with MBR/GPT standards,
        # we first append it as a partition and then point the El Torito at
        # it.  See https://lists.debian.org/debian-cd/2019/07/msg00007.html
        opts: list[str | pathlib.Path] = [
            "-append_partition",
            "2",
            "0xef",
            self.scratch.joinpath("cd-boot-efi.img"),
            "-appended_part_as_gpt",
        ]

        # Some BIOSes ignore removable disks with no partitions marked bootable
        # in the MBR.  Make sure our protective MBR partition is marked bootable.
        opts.append("--mbr-force-bootable")

        # Start a new entry in the el torito boot catalog
        opts.append("-eltorito-alt-boot")

        # Specify where the el torito UEFI boot image "name".  We use a special
        # syntax available in latest xorriso to point at our newly-created
        # partition.
        opts.extend(["-e", "--interval:appended_partition_2:all::"])

        # Whether to emulate a floppy or not is a per-boot-catalog-entry
        # thing, so we need to say it again.
        opts.append("-no-emul-boot")

        # Create a partition table entry that covers the iso9660 filesystem
        opts.extend(["-partition_offset", "16"])

        return opts
