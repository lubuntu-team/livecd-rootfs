"""ARM 64-bit architecture boot configuration."""

import pathlib

from .uefi import UEFIBootConfigurator
from .base import default_kernel_params


class ARM64BootConfigurator(UEFIBootConfigurator):
    """Boot setup for ARM 64-bit architecture."""

    efi_suffix = "aa64"
    grub_target = "arm64"
    arch = "arm64"

    def mkisofs_opts(self) -> list[str | pathlib.Path]:
        """Return mkisofs options for ARM64."""
        opts: list[str | pathlib.Path] = [
            "-J",
            "-joliet-long",
            "-l",
            "-c",
            "boot/boot.cat",
        ]
        # Add common UEFI options
        opts.extend(self.get_uefi_mkisofs_opts())
        # ARM64-specific: partition cylinder alignment
        opts.extend(["-partition_cyl_align", "all"])
        return opts

    def extract_files(self) -> None:
        """Download and extract bootloader packages for ARM64."""
        with self.logger.logged("extracting ARM64 boot files"):
            self.extract_uefi_files()

    def generate_grub_config(self) -> str:
        """Generate grub.cfg for ARM64."""
        kernel_params = default_kernel_params(self.project)

        result = self.grub_header()

        # ARM64-specific: Snapdragon workarounds
        result += f"""\
set cmdline=
smbios --type 4 --get-string 5 --set proc_version
regexp "Snapdragon.*" "$proc_version"
if [ $? = 0 ]; then
  # Work around Snapdragon X firmware bug. cutmem is not allowed in lockdown mode.
  if [ $lockdown != "y" ]; then
    cutmem 0x8800000000 0x8fffffffff
  fi
  # arm64.nopauth works around 8cx Gen 3 firmware bug
  cmdline="clk_ignore_unused pd_ignore_unused arm64.nopauth"
fi

menuentry "Try or Install {self.humanproject}" {{
    set gfxpayload=keep
    linux  /casper/vmlinuz $cmdline {kernel_params} console=tty0
    initrd /casper/initrd
}}
"""

        # HWE kernel option if available
        result += self.hwe_menu_entry(
            "vmlinuz",
            f"{kernel_params} console=tty0",
            extra_params="$cmdline ",
        )

        # Note: ARM64 HWE also includes $dtb in the original shell script,
        # but it's not actually set anywhere in the grub.cfg, so we omit it here

        # UEFI Entries (ARM64 is UEFI-only, no grub_platform check needed)
        result += self.uefi_menu_entries()

        return result
