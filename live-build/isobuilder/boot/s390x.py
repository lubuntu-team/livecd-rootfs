"""IBM S/390 architecture boot configuration."""

import pathlib
import shutil
import struct

from .base import BaseBootConfigurator

README_dot_boot = """\
About the S/390 installation CD
===============================

It is possible to "boot" the installation system off this CD using
the files provided in the /boot directory.

Although you can boot the installer from this CD, the installation
itself is *not* actually done from the CD. Once the initrd is loaded,
the installer will ask you to configure your network connection and
uses the network-console component to allow you to continue the
installation over SSH. The rest of the installation is done over the
network: all installer components and Debian packages are retrieved
from a mirror.

Instead of SSH, one can also use the ASCII terminal available in HMC.

Exporting full .iso contents (including the hidden .disk directory)
allows one to use the result as a valid mirror for installation.
"""

ubuntu_dot_exec = """\
/* REXX EXEC TO IPL Ubuntu for        */
/* z Systems FROM THE VM READER.      */
/*                                    */
'CP CLOSE RDR'
'PURGE RDR ALL'
'SPOOL PUNCH * RDR'
'PUNCH KERNEL    UBUNTU   * (NOHEADER'
'PUNCH PARMFILE  UBUNTU   * (NOHEADER'
'PUNCH INITRD    UBUNTU   * (NOHEADER'
'CHANGE RDR ALL KEEP NOHOLD'
'CP IPL 000C CLEAR'
"""

ubuntu_dot_ins = """\
* Ubuntu for IBM Z (default kernel)
kernel.ubuntu 0x00000000
initrd.off 0x0001040c
initrd.siz 0x00010414
parmfile.ubuntu 0x00010480
initrd.ubuntu 0x01000000
"""


def gen_s390_cd_kernel(
    kernel: pathlib.Path, initrd: pathlib.Path, cmdline: str, outfile: pathlib.Path
) -> None:
    """Generate a bootable S390X CD kernel image.

    This is a Python translation of gen-s390-cd-kernel.pl from debian-cd.
    It creates a bootable image for S/390 architecture by combining kernel,
    initrd, and boot parameters in a specific format.
    """
    # Calculate sizes
    initrd_size = initrd.stat().st_size

    # The initrd is placed at a fixed offset of 16 MiB
    initrd_offset = 0x1000000

    # Calculate total boot image size (rounded up to 4K blocks)
    boot_size = ((initrd_offset + initrd_size) >> 12) + 1
    boot_size = boot_size << 12

    # Validate cmdline length (max 896 bytes)
    if len(cmdline) >= 896:
        raise ValueError(f"Kernel commandline too long ({len(cmdline)} bytes)")

    # Create output file and fill with zeros
    with outfile.open("wb") as out_fh:
        # Fill entire file with zeros
        out_fh.write(b"\x00" * boot_size)

        # Copy kernel to offset 0
        out_fh.seek(0)
        with kernel.open("rb") as kernel_fh:
            out_fh.write(kernel_fh.read())

        # Copy initrd to offset 0x1000000 (16 MiB)
        out_fh.seek(initrd_offset)
        with initrd.open("rb") as initrd_fh:
            out_fh.write(initrd_fh.read())

        # Write boot loader control value at offset 4
        # This tells the S/390 boot loader where to find the kernel
        out_fh.seek(4)
        out_fh.write(struct.pack("!I", 0x80010000))

        # Write kernel command line at offset 0x10480
        out_fh.seek(0x10480)
        out_fh.write(cmdline.encode("utf-8"))

        # Write initrd parameters
        # Initrd offset at 0x1040C
        out_fh.seek(0x1040C)
        out_fh.write(struct.pack("!I", initrd_offset))

        # Initrd size at 0x10414
        out_fh.seek(0x10414)
        out_fh.write(struct.pack("!I", initrd_size))


class S390XBootConfigurator(BaseBootConfigurator):
    """Boot setup for IBM S/390 architecture."""

    def mkisofs_opts(self) -> list[str | pathlib.Path]:
        """Return mkisofs options for S390X."""
        return [
            "-J",
            "-no-emul-boot",
            "-b",
            "boot/ubuntu.ikr",
        ]

    def extract_files(self) -> None:
        """Set up boot files for S390X."""
        self.logger.log("extracting S390X boot files")
        boot_dir = self.iso_root.joinpath("boot")
        boot_dir.mkdir(parents=True, exist_ok=True)

        # Copy static .ins & exec scripts, docs from data directory
        self.iso_root.joinpath("README.boot").write_text(README_dot_boot)
        boot_dir.joinpath("ubuntu.exec").write_text(ubuntu_dot_exec)
        boot_dir.joinpath("ubuntu.ins").write_text(ubuntu_dot_ins)

        # Move kernel image to the name used in .ins & exec scripts
        kernel_src = self.iso_root.joinpath("casper", "vmlinuz")
        kernel_dst = boot_dir.joinpath("kernel.ubuntu")
        kernel_src.replace(kernel_dst)

        # Move initrd to the name used in .ins & exec scripts
        initrd_src = self.iso_root.joinpath("casper", "initrd")
        initrd_dst = boot_dir.joinpath("initrd.ubuntu")
        initrd_src.replace(initrd_dst)

        # Compute initrd offset & size, store in files used by .ins & exec scripts
        # Offset is always 0x1000000 (16 MiB)
        initrd_offset_file = boot_dir.joinpath("initrd.off")
        with initrd_offset_file.open("wb") as f:
            f.write(struct.pack("!I", 0x1000000))

        # Size is the actual size of the initrd
        initrd_size = initrd_dst.stat().st_size
        initrd_size_file = boot_dir.joinpath("initrd.siz")
        with initrd_size_file.open("wb") as f:
            f.write(struct.pack("!I", initrd_size))

        # Compute cmdline, store in parmfile used by .ins & exec scripts
        parmfile = boot_dir.joinpath("parmfile.ubuntu")
        with parmfile.open("w") as f:
            f.write(" --- ")

        # Generate secondary top-level ubuntu.ins file
        # This transforms lines not starting with * by prepending "boot/"
        ubuntu_ins_src = boot_dir.joinpath("ubuntu.ins")
        ubuntu_ins_dst = self.iso_root.joinpath("ubuntu.ins")
        if ubuntu_ins_src.exists():
            self.logger.run(
                ["sed", "-e", "s,^[^*],boot/&,g", ubuntu_ins_src],
                stdout=ubuntu_ins_dst.open("w"),
                check=True,
            )

        # Generate QEMU-KVM boot image using gen_s390_cd_kernel
        cmdline = parmfile.read_text().strip()
        ikr_file = boot_dir.joinpath("ubuntu.ikr")
        gen_s390_cd_kernel(kernel_dst, initrd_dst, cmdline, ikr_file)

        # Extract bootloader signing certificate
        installed_pem = pathlib.Path("/usr/lib/s390-tools/stage3.pem")
        squashfs_root = self.iso_root.joinpath("squashfs-root")
        squashfs_path = self.iso_root.joinpath(
            "casper", "ubuntu-server-minimal.squashfs"
        )

        if squashfs_path.exists():
            self.logger.run(
                [
                    "unsquashfs",
                    "-no-xattrs",
                    "-i",
                    "-d",
                    squashfs_root,
                    squashfs_path,
                    installed_pem,
                ],
                check=True,
            )

            # Move certificate to iso root
            cert_src = squashfs_root.joinpath(str(installed_pem).lstrip("/"))
            cert_dst = self.iso_root.joinpath("ubuntu.pem")
            if cert_src.exists():
                cert_src.replace(cert_dst)

            # Clean up squashfs extraction
            shutil.rmtree(squashfs_root)
