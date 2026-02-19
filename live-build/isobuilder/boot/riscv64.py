"""RISC-V 64-bit architecture boot configuration."""

import pathlib
import shutil

from .grub import GrubBootConfigurator, copy_grub_common_files, copy_grub_modules


def copy_unsigned_monolithic_grub(
    grub_pkg_dir: pathlib.Path,
    efi_suffix: str,
    grub_target: str,
    iso_root: pathlib.Path,
) -> None:
    efi_boot_dir = iso_root.joinpath("EFI", "boot")
    efi_boot_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy(
        grub_pkg_dir.joinpath(
            "usr",
            "lib",
            "grub",
            grub_target,
            "monolithic",
            f"gcd{efi_suffix}.efi",
        ),
        efi_boot_dir.joinpath(f"boot{efi_suffix}.efi"),
    )

    copy_grub_modules(grub_pkg_dir, iso_root, grub_target, ["*.mod", "*.lst"])


class RISCV64BootConfigurator(GrubBootConfigurator):
    """Boot setup for RISC-V 64-bit architecture."""

    def mkisofs_opts(self) -> list[str | pathlib.Path]:
        """Return mkisofs options for RISC-V64."""
        efi_img = self.scratch.joinpath("efi.img")

        return [
            "-joliet",
            "on",
            "-compliance",
            "joliet_long_names",
            "--append_partition",
            "2",
            "0xef",
            efi_img,
            "-boot_image",
            "any",
            "partition_offset=10240",
            "-boot_image",
            "any",
            "partition_cyl_align=all",
            "-boot_image",
            "any",
            "efi_path=--interval:appended_partition_2:all::",
            "-boot_image",
            "any",
            "appended_part_as=gpt",
            "-boot_image",
            "any",
            "cat_path=/boot/boot.cat",
            "-fs",
            "64m",
        ]

    def extract_files(self) -> None:
        """Download and extract bootloader packages for RISC-V64."""
        self.logger.log("extracting RISC-V64 boot files")
        u_boot_dir = self.scratch.joinpath("u-boot-sifive")

        grub_pkg_dir = self.scratch.joinpath("grub-pkg")

        # Download and extract bootloader packages
        self.download_and_extract_package("grub2-common", grub_pkg_dir)
        self.download_and_extract_package("grub-efi-riscv64-bin", grub_pkg_dir)
        self.download_and_extract_package("grub-efi-riscv64-unsigned", grub_pkg_dir)
        self.download_and_extract_package("u-boot-sifive", u_boot_dir)

        # Add GRUB to tree
        copy_grub_common_files(grub_pkg_dir, self.iso_root)

        copy_unsigned_monolithic_grub(
            grub_pkg_dir, "riscv64", "riscv64-efi", self.iso_root
        )

        # Extract DTBs to tree
        self.logger.log("extracting device tree files")
        kernel_layer = self.scratch.joinpath("kernel-layer")
        squashfs_path = self.iso_root.joinpath(
            "casper", "ubuntu-server-minimal.squashfs"
        )

        # Extract device tree firmware from squashfs
        self.logger.run(
            [
                "unsquashfs",
                "-no-xattrs",
                "-d",
                kernel_layer,
                squashfs_path,
                "usr/lib/firmware",
            ],
            check=True,
        )

        # Copy DTBs if they exist
        dtb_dir = self.iso_root.joinpath("dtb")
        dtb_dir.mkdir(parents=True, exist_ok=True)

        firmware_dir = kernel_layer.joinpath("usr", "lib", "firmware")

        for dtb_file in firmware_dir.glob("*/device-tree/*"):
            if dtb_file.is_file():
                shutil.copy(dtb_file, dtb_dir)

        # Create ESP image with GRUB and dtbs
        efi_img = self.scratch.joinpath("efi.img")
        self.logger.run(
            ["mkfs.msdos", "-n", "ESP", "-C", "-v", efi_img, "32768"], check=True
        )

        # Add EFI files to ESP
        efi_dir = self.iso_root.joinpath("EFI")
        self.logger.run(["mcopy", "-s", "-i", efi_img, efi_dir, "::/."], check=True)

        # Add DTBs to ESP
        self.logger.run(["mcopy", "-s", "-i", efi_img, dtb_dir, "::/."], check=True)

    def generate_grub_config(self) -> str:
        """Generate grub.cfg for RISC-V64."""
        result = self.grub_header(include_loadfont=False)

        # Main menu entry
        result += f"""\
menuentry "Try or Install {self.humanproject}" {{
    set gfxpayload=keep
    linux  /casper/vmlinux efi=debug sysctl.kernel.watchdog_thresh=60 ---
    initrd /casper/initrd
}}
"""

        # HWE kernel option if available
        result += self.hwe_menu_entry(
            "vmlinux",
            "---",
            extra_params="efi=debug sysctl.kernel.watchdog_thresh=60 ",
        )

        return result

    def post_process_iso(self, iso_path: pathlib.Path) -> None:
        """Add GPT partitions with U-Boot for SiFive Unmatched board.

        The SiFive Unmatched board needs a GPT table containing U-Boot in
        order to boot. U-Boot does not currently support booting from a CD,
        so the GPT table also contains an entry pointing to the ESP so that
        U-Boot can find it.
        """
        u_boot_dir = self.scratch.joinpath(
            "u-boot-sifive", "usr", "lib", "u-boot", "sifive_unmatched"
        )
        self.logger.run(
            [
                "sgdisk",
                iso_path,
                "--set-alignment=2",
                "-d",
                "1",
                "-n",
                "1:2082:10273",
                "-c",
                "1:loader2",
                "-t",
                "1:2E54B353-1271-4842-806F-E436D6AF6985",
                "-n",
                "3:10274:12321",
                "-c",
                "3:loader1",
                "-t",
                "3:5B193300-FC78-40CD-8002-E86C45580B47",
                "-c",
                "2:ESP",
                "-r=2:3",
            ],
        )
        self.logger.run(
            [
                "dd",
                f"if={u_boot_dir / 'u-boot.itb'}",
                f"of={iso_path}",
                "bs=512",
                "seek=2082",
                "conv=notrunc",
            ],
        )
        self.logger.run(
            [
                "dd",
                f"if={u_boot_dir / 'u-boot-spl.bin'}",
                f"of={iso_path}",
                "bs=512",
                "seek=10274",
                "conv=notrunc",
            ],
        )
