"""AMD64/x86_64 architecture boot configuration."""

import pathlib
import shutil

from .base import default_kernel_params
from .grub import copy_grub_modules
from .uefi import UEFIBootConfigurator

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
                self.scratch.joinpath("boot_hybrid.img"),
            ]
        )

        # ## Set up the mkisofs options for UEFI boot.
        opts.extend(self.get_uefi_mkisofs_opts())

        return opts

    def extract_files(self) -> None:
        with self.logger.logged("extracting AMD64 boot files"):

            # Extract UEFI files (common with ARM64)
            self.extract_uefi_files()

            # AMD64-specific: Add BIOS/legacy boot files
            with self.logger.logged("adding BIOS/legacy boot files"):
                grub_pc_pkg_dir = self.scratch.joinpath("grub-pc-pkg")
                self.download_and_extract_package("grub-pc-bin", grub_pc_pkg_dir)

                grub_boot_dir = self.iso_root.joinpath("boot", "grub", "i386-pc")
                grub_boot_dir.mkdir(parents=True, exist_ok=True)

                src_grub_dir = grub_pc_pkg_dir.joinpath("usr", "lib", "grub", "i386-pc")

                shutil.copy(src_grub_dir.joinpath("eltorito.img"), grub_boot_dir)
                shutil.copy(src_grub_dir.joinpath("boot_hybrid.img"), self.scratch)

                copy_grub_modules(
                    grub_pc_pkg_dir,
                    self.iso_root,
                    "i386-pc",
                    ["*.mod", "*.lst", "*.o"],
                )

    def generate_grub_config(self) -> str:
        """Generate grub.cfg content for AMD64."""
        result = self.grub_header()

        if self.project == "ubuntu-mini-iso":
            result += """\
menuentry "Choose an Ubuntu version to install" {
    set gfxpayload=keep
    linux  /casper/vmlinuz iso-chooser-menu ip=dhcp ---
    initrd /casper/initrd
}
"""
            return result

        kernel_params = default_kernel_params(self.project)

        # Main menu entry
        result += f"""\
menuentry "Try or Install {self.humanproject}" {{
    set gfxpayload=keep
    linux  /casper/vmlinuz {kernel_params}
    initrd /casper/initrd
}}
"""

        # All but server get safe-graphics mode
        if self.project != "ubuntu-server":
            result += f"""\
menuentry "{self.humanproject} (safe graphics)" {{
    set gfxpayload=keep
    linux  /casper/vmlinuz nomodeset {kernel_params}
    initrd /casper/initrd
}}
"""

        # ubiquity based projects get OEM mode
        if "maybe-ubiquity" in kernel_params:
            oem_kernel_params = kernel_params.replace(
                "maybe-ubiquity", "only-ubiquity oem-config/enable=true"
            )
            result += f"""\
menuentry "OEM install (for manufacturers)" {{
    set gfxpayload=keep
    linux  /casper/vmlinuz {oem_kernel_params}
    initrd /casper/initrd
}}
"""

        # Calamares-based projects get OEM mode
        if self.project in CALAMARES_PROJECTS:
            result += f"""\
menuentry "OEM install (for manufacturers)" {{
    set gfxpayload=keep
    linux  /casper/vmlinuz {kernel_params} oem-config/enable=true
    initrd /casper/initrd
}}
"""

        # Currently only server is built with HWE, hence no safe-graphics/OEM
        if self.hwe:
            result += f"""\
menuentry "{self.humanproject} with the HWE kernel" {{
    set gfxpayload=keep
    linux  /casper/hwe-vmlinuz {kernel_params}
    initrd /casper/hwe-initrd
}}
"""

        # UEFI Entries (wrapped in grub_platform check for dual BIOS/UEFI support)
        uefi_menu_entries = self.uefi_menu_entries()

        result += f"""\
grub_platform
if [ "$grub_platform" = "efi" ]; then
{uefi_menu_entries}\
fi
"""

        return result

    @staticmethod
    def generate_loopback_config(grub_content: str) -> str:
        """Derive loopback.cfg from grub.cfg content.

        Strips the header (up to menu_color_highlight) and the UEFI
        trailer (from grub_platform to end), and adds iso-scan/filename
        to linux lines.
        """
        lines = grub_content.split("\n")
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

        return "\n".join(loopback_lines)

    def make_bootable(
        self,
        project: str,
        capproject: str,
        subarch: str,
        hwe: bool,
        dtb_dir: pathlib.Path | None = None,
    ) -> None:
        """Make the ISO bootable, including generating loopback.cfg."""
        super().make_bootable(project, capproject, subarch, hwe, dtb_dir)
        grub_cfg = self.iso_root.joinpath("boot", "grub", "grub.cfg")
        grub_content = grub_cfg.read_text()
        self.iso_root.joinpath("boot", "grub", "loopback.cfg").write_text(
            self.generate_loopback_config(grub_content)
        )
