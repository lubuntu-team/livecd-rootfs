"""AMD64/x86_64 architecture boot configuration."""

import pathlib
import shutil

from .uefi import UEFIBootConfigurator
from .base import default_kernel_params


CALAMARES_PROJECTS = ["kubuntu", "lubuntu"]


class AMD64BootConfigurator(UEFIBootConfigurator):
    """Boot setup for AMD64/x86_64 architecture."""

    efi_suffix = "x64"
    grub_target = "x86_64"
    arch = "amd64"

    def mkisofs_opts(self) -> list[str | pathlib.Path]:
        # Boring mkisofs options that should be set somewhere architecture independent.
        opts: list[str | pathlib.Path] = ["-J", "-joliet-long", "-l"]

        # Generalities on booting
        #
        # There is a 2x2 matrix of boot modes we care about: legacy or UEFI
        # boot modes and having the installer be on a cdrom or a disk. Booting
        # from cdrom uses the el torito standard and booting from disk expects
        # a MBR or GPT partition table.
        #
        # https://wiki.osdev.org/El-Torito has a lot more background on this.

        # ## Set up the mkisofs options for legacy boot.

        # Set the el torito boot image "name", i.e. the path on the ISO
        # containing the bootloader for legacy-cdrom boot.
        opts.extend(["-b", "boot/grub/i386-pc/eltorito.img"])

        # Back in the day, el torito booting worked by emulating a floppy
        # drive.  This hasn't been a useful way of operating for a long time.
        opts.append("-no-emul-boot")

        # Misc options to make the legacy-cdrom boot work.
        opts.extend(["-boot-load-size", "4", "-boot-info-table", "--grub2-boot-info"])

        # The bootloader to write to the MBR for legacy-disk boot.
        #
        # We use the grub stage1 bootloader, boot_hybrid.img, which then jumps
        # to the eltorito image based on the information xorriso provides it
        # via the --grub2-boot-info option.
        opts.extend(
            [
                "--grub2-mbr",
                self.grub_dir.joinpath("usr/lib/grub/i386-pc/boot_hybrid.img"),
            ]
        )

        # ## Set up the mkisofs options for UEFI boot.
        opts.extend(self.get_uefi_mkisofs_opts())

        # ## Add cd-boot-tree to the ISO
        opts.append(str(self.boot_tree))

        return opts

    def extract_files(self) -> None:
        with self.logger.logged("extracting AMD64 boot files"):

            # Extract UEFI files (common with ARM64)
            self.extract_uefi_files()

            # AMD64-specific: Add BIOS/legacy boot files
            with self.logger.logged("adding BIOS/legacy boot files"):
                self.download_and_extract_package("grub-pc-bin", self.grub_dir)

                grub_boot_dir = self.boot_tree.joinpath("boot", "grub", "i386-pc")
                grub_boot_dir.mkdir(parents=True, exist_ok=True)

                src_grub_dir = self.grub_dir.joinpath("usr", "lib", "grub", "i386-pc")

                shutil.copy(src_grub_dir.joinpath("eltorito.img"), grub_boot_dir)

                self.copy_grub_modules(
                    src_grub_dir, grub_boot_dir, ["*.mod", "*.lst", "*.o"]
                )

    def generate_grub_config(self) -> None:
        """Generate grub.cfg and loopback.cfg for the boot tree."""
        # Generate grub.cfg
        kernel_params = default_kernel_params(self.project)

        boot_grub_dir = self.boot_tree.joinpath("boot", "grub")
        boot_grub_dir.mkdir(parents=True, exist_ok=True)

        grub_cfg = boot_grub_dir.joinpath("grub.cfg")

        # Write common GRUB header
        self.write_grub_header(grub_cfg)

        # Main menu entry
        with grub_cfg.open("a") as f:
            f.write(
                f"""menuentry "Try or Install {self.humanproject}" {{
    set gfxpayload=keep
    linux    /casper/vmlinuz {kernel_params}
    initrd    /casper/initrd
}}
"""
            )

        # All but server get safe-graphics mode
        if self.project != "ubuntu-server":
            with grub_cfg.open("a") as f:
                f.write(
                    f"""menuentry "{self.humanproject} (safe graphics)" {{
    set gfxpayload=keep
    linux    /casper/vmlinuz nomodeset {kernel_params}
    initrd    /casper/initrd
}}
"""
                )

        # ubiquity based projects get OEM mode
        if "maybe-ubiquity" in kernel_params:
            oem_kernel_params = kernel_params.replace(
                "maybe-ubiquity", "only-ubiquity oem-config/enable=true"
            )
            with grub_cfg.open("a") as f:
                f.write(
                    f"""menuentry "OEM install (for manufacturers)" {{
    set gfxpayload=keep
    linux    /casper/vmlinuz {oem_kernel_params}
    initrd    /casper/initrd
}}
"""
                )

        # Calamares-based projects get OEM mode
        if self.project in CALAMARES_PROJECTS:
            with grub_cfg.open("a") as f:
                f.write(
                    f"""menuentry "OEM install (for manufacturers)" {{
    set gfxpayload=keep
    linux    /casper/vmlinuz {kernel_params} oem-config/enable=true
    initrd    /casper/initrd
}}
"""
                )

        # Currently only server is built with HWE, hence no safe-graphics/OEM
        if self.hwe:
            with grub_cfg.open("a") as f:
                f.write(
                    f"""menuentry "{self.humanproject} with the HWE kernel" {{
    set gfxpayload=keep
    linux    /casper/hwe-vmlinuz {kernel_params}
    initrd    /casper/hwe-initrd
}}
"""
                )

        # Create the loopback config, based on the main config
        with grub_cfg.open("r") as f:
            content = f.read()

        # sed: delete from line 1 to menu_color_highlight, delete from
        # grub_platform to end and replace '---' with
        # 'iso-scan/filename=${iso_path} ---' in lines with 'linux'
        lines = content.split("\n")
        start_idx = 0
        for i, line in enumerate(lines):
            if "menu_color_highlight" in line:
                start_idx = i + 1
                break

        end_idx = len(lines)
        for i, line in enumerate(lines):
            if "grub_platform" in line:
                end_idx = i
                break

        loopback_lines = lines[start_idx:end_idx]
        loopback_lines = [
            (
                line.replace("---", "iso-scan/filename=${iso_path} ---")
                if "linux" in line
                else line
            )
            for line in loopback_lines
        ]

        loopback_cfg = boot_grub_dir.joinpath("loopback.cfg")
        with loopback_cfg.open("w") as f:
            f.write("\n".join(loopback_lines))

        # UEFI Entries (wrapped in grub_platform check for dual BIOS/UEFI support)
        with grub_cfg.open("a") as f:
            f.write("grub_platform\n")
            f.write('if [ "$grub_platform" = "efi" ]; then\n')

        self.write_uefi_menu_entries(grub_cfg)

        with grub_cfg.open("a") as f:
            f.write("fi\n")
