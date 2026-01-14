import contextlib
import json
import os
import pathlib
import shlex
import shutil
import subprocess
import sys

from isobuilder.apt_state import AptStateManager
from isobuilder.gpg_key import EphemeralGPGKey
from isobuilder.pool_builder import PoolBuilder

# Constants
PACKAGE_BATCH_SIZE = 200
MAX_CMD_DISPLAY_LENGTH = 80


def package_list_packages(package_list_file: pathlib.Path) -> list[str]:
    # Parse germinate output to extract package names. Germinate is Ubuntu's
    # package dependency resolver that outputs dependency trees for seeds (like
    # "ship-live" or "server-ship-live").
    #
    # Germinate output format has 2 header lines at the start and 2 footer lines
    # at the end (showing statistics), so we skip them with [2:-2].
    # Each data line starts with the package name followed by whitespace and
    # dependency info. This format is stable but if germinate ever changes its
    # header/footer count, this will break silently.
    lines = package_list_file.read_text().splitlines()[2:-2]
    return [line.split(None, 1)[0] for line in lines]


def make_sources_text(
    series: str, gpg_key: EphemeralGPGKey, components: list[str], mountpoint: str
) -> str:
    """Generate a deb822-format apt source file for the ISO's package pool.

    deb822 is the modern apt sources format (see sources.list(5) and deb822(5)).
    It uses RFC822-style fields where multi-line values must be indented with a
    leading space, and empty lines within a value are represented as " ."
    (space-dot). This format is required for inline GPG keys in the Signed-By
    field.
    """
    key = gpg_key.export_public()
    quoted_key = []
    for line in key.splitlines():
        if not line:
            quoted_key.append(" .")
        else:
            quoted_key.append(" " + line)
    return f"""\
Types: deb
URIs: file://{mountpoint}
Suites: {series}
Components: {" ".join(components)}
Check-Date: no
Signed-By:
""" + "\n".join(
        quoted_key
    )


class Logger:

    def __init__(self):
        self._indent = ""

    def log(self, msg):
        print(self._indent + msg, file=sys.stderr)

    @contextlib.contextmanager
    def logged(self, msg, done_msg=None):
        self.log(msg)
        self._indent += "  "
        try:
            yield
        finally:
            self._indent = self._indent[:-2]
        if done_msg is not None:
            self.log(done_msg)

    def msg_for_cmd(self, cmd, cwd=None) -> str:
        if cwd is None:
            _cwd = pathlib.Path().cwd()
        else:
            _cwd = cwd
        fmted_cmd = []
        for arg in cmd:
            if isinstance(arg, pathlib.Path):
                if arg.is_relative_to(_cwd):
                    arg = arg.relative_to(_cwd)
                arg = str(arg)
            fmted_cmd.append(shlex.quote(arg))
        fmted_cmd_str = " ".join(fmted_cmd)
        if len(fmted_cmd_str) > MAX_CMD_DISPLAY_LENGTH:
            fmted_cmd_str = fmted_cmd_str[:MAX_CMD_DISPLAY_LENGTH] + "..."
        msg = f"running `{fmted_cmd_str}`"
        if cwd is not None:
            msg += f" in {cwd}"
        return msg

    def run(self, cmd: list[str | pathlib.Path], *args, check=True, **kw):
        with self.logged(self.msg_for_cmd(cmd, kw.get("cwd"))):
            return subprocess.run(cmd, *args, check=check, **kw)


class ISOBuilder:

    def __init__(self, workdir: pathlib.Path):
        self.workdir = workdir
        self.logger = Logger()
        self.iso_root = workdir.joinpath("iso-root")
        self._series = self._arch = self._gpg_key = self._apt_state = None

    # UTILITY STUFF

    def _read_config(self):
        with self.workdir.joinpath("config.json").open() as fp:
            data = json.load(fp)
        self._series = data["series"]
        self._arch = data["arch"]

    @property
    def arch(self):
        if self._arch is None:
            self._read_config()
        return self._arch

    @property
    def series(self):
        if self._series is None:
            self._read_config()
        return self._series

    @property
    def gpg_key(self):
        if self._gpg_key is None:
            self._gpg_key = EphemeralGPGKey(
                self.logger, self.workdir.joinpath("gpg-home")
            )
        return self._gpg_key

    @property
    def apt_state(self):
        if self._apt_state is None:
            self._apt_state = AptStateManager(
                self.logger, self.series, self.workdir.joinpath("apt-state")
            )
        return self._apt_state

    # COMMANDS

    def init(self, disk_info: str, series: str, arch: str):
        self.logger.log("creating directories")
        self.workdir.mkdir(exist_ok=True)
        self.iso_root.mkdir()
        dot_disk = self.iso_root.joinpath(".disk")
        dot_disk.mkdir()

        self.logger.log("saving config")
        with self.workdir.joinpath("config.json").open("w") as fp:
            json.dump({"arch": arch, "series": series}, fp)

        self.logger.log("populating .disk")
        dot_disk.joinpath("base_installable").touch()
        dot_disk.joinpath("cd_type").write_text("full_cd/single\n")
        dot_disk.joinpath("info").write_text(disk_info)
        self.iso_root.joinpath("casper").mkdir()

        self.gpg_key.create()

    def setup_apt(self, chroot: pathlib.Path):
        self.apt_state.setup(chroot)

    def generate_pool(self, package_list_file: pathlib.Path):
        # do we need any of the symlinks we create here??
        self.logger.log("creating pool skeleton")
        self.iso_root.joinpath("ubuntu").symlink_to(".")
        if self.arch not in ("amd64", "i386"):
            self.iso_root.joinpath("ubuntu-ports").symlink_to(".")
        self.iso_root.joinpath("dists", self.series).mkdir(parents=True)

        builder = PoolBuilder(
            self.logger,
            series=self.series,
            rootdir=self.iso_root,
            apt_state=self.apt_state,
        )
        pkgs = package_list_packages(package_list_file)
        # XXX include 32-bit deps of 32-bit packages if needed here
        with self.logger.logged("adding packages"):
            for i in range(0, len(pkgs), PACKAGE_BATCH_SIZE):
                builder.add_packages(
                    self.apt_state.show(pkgs[i : i + PACKAGE_BATCH_SIZE])
                )
        builder.make_packages()
        release_file = builder.make_release()
        self.gpg_key.sign(release_file)
        for name in "stable", "unstable":
            self.iso_root.joinpath("dists", name).symlink_to(self.series)

    def generate_sources(self, mountpoint: str):
        components = [p.name for p in self.iso_root.joinpath("pool").iterdir()]
        print(
            make_sources_text(
                self.series, self.gpg_key, mountpoint=mountpoint, components=components
            )
        )

    def _extract_casper_uuids(self):
        # Extract UUID files from initrd images for casper (the live boot system).
        # Each initrd contains a conf/uuid.conf with a unique identifier that
        # casper uses at boot time to locate the correct root filesystem. These
        # UUIDs must be placed in .disk/casper-uuid-<flavor> on the ISO so casper
        # can verify it's booting from the right media.
        with self.logger.logged("extracting casper uuids"):
            casper_dir = self.iso_root.joinpath("casper")
            prefix = "filesystem.initrd-"
            dot_disk = self.iso_root.joinpath(".disk")
            for initrd in casper_dir.glob(f"{prefix}*"):
                initrddir = self.workdir.joinpath("initrd")
                with self.logger.logged(
                    f"unpacking {initrd.name} ...", done_msg="... done"
                ):
                    self.logger.run(["unmkinitramfs", initrd, initrddir])
                # unmkinitramfs can produce different directory structures:
                # - Platforms with early firmware: subdirs like "main/" or "early/"
                #   containing conf/uuid.conf
                # - Other platforms: conf/uuid.conf directly in the root
                # Try to find uuid.conf in both locations. The [uuid_conf] = confs
                # unpacking asserts exactly one match; multiple matches would
                # indicate an unexpected initrd structure.
                confs = list(initrddir.glob("*/conf/uuid.conf"))
                if confs:
                    [uuid_conf] = confs
                elif initrddir.joinpath("conf/uuid.conf").exists():
                    uuid_conf = initrddir.joinpath("conf/uuid.conf")
                else:
                    raise Exception("uuid.conf not found")
                self.logger.log(f"found {uuid_conf.relative_to(initrddir)}")
                uuid_conf.rename(
                    dot_disk.joinpath("casper-uuid-" + initrd.name[len(prefix) :])
                )
                shutil.rmtree(initrddir)

    def add_live_filesystem(self, artifact_prefix: pathlib.Path):
        # Link build artifacts into the ISO's casper directory. We use hardlinks
        # (not copies) for filesystem efficiency - they reference the same inode.
        #
        # Artifacts come from the layered build with names like "for-iso.base.squashfs"
        # and need to be renamed for casper. The prefix is stripped, so:
        #   for-iso.base.squashfs -> base.squashfs
        #   for-iso.kernel-generic -> filesystem.kernel-generic
        #
        # Kernel and initrd get the extra "filesystem." prefix because debian-cd
        # expects names like filesystem.kernel-* and filesystem.initrd-*.
        casper_dir = self.iso_root.joinpath("casper")
        artifact_dir = artifact_prefix.parent
        filename_prefix = artifact_prefix.name

        def link(src, target_name):
            target = casper_dir.joinpath(target_name)
            self.logger.log(
                f"creating link from $ISOROOT/casper/{target_name} to $src/{src.name}"
            )
            target.hardlink_to(src)

        with self.logger.logged(
            f"linking artifacts from {casper_dir} to {artifact_dir}"
        ):
            for ext in "squashfs", "squashfs.gpg", "size", "manifest", "yaml":
                for path in artifact_dir.glob(f"{filename_prefix}*.{ext}"):
                    newname = path.name[len(filename_prefix) :]
                    link(path, newname)
            for item in "kernel", "initrd":
                for path in artifact_dir.glob(f"{filename_prefix}{item}-*"):
                    newname = "filesystem." + path.name[len(filename_prefix) :]
                    link(path, newname)
        self._extract_casper_uuids()

    def make_bootable(self, project: str, capproject: str, subarch: str):
        # debian-cd is Ubuntu's CD/ISO image build system. It contains
        # architecture and series-specific boot configuration scripts that set up
        # GRUB, syslinux, EFI boot, etc. The tools/boot/$series/boot-$arch script
        # knows how to make an ISO bootable for each architecture.
        #
        # TODO: The boot configuration logic should eventually be ported directly
        # into isobuilder to avoid this external dependency and git clone.
        debian_cd_dir = self.workdir.joinpath("debian-cd")
        with self.logger.logged("cloning debian-cd"):
            self.logger.run(
                [
                    "git",
                    "clone",
                    "--depth=1",
                    "https://git.launchpad.net/~ubuntu-cdimage/debian-cd/+git/ubuntu",
                    debian_cd_dir,
                ],
            )
        # Override apt-selection to use our ISO's apt configuration instead of
        # debian-cd's default. This ensures the boot scripts get packages from
        # the correct repository when installing boot packages.
        apt_selection = debian_cd_dir.joinpath("tools/apt-selection")
        with self.logger.logged("overwriting apt-selection"):
            apt_selection.write_text(
                "#!/bin/sh\n" f"APT_CONFIG={self.apt_state.apt_conf_path} apt-get $@\n"
            )
        env = dict(
            os.environ,
            BASEDIR=str(debian_cd_dir),
            DIST=self.series,
            PROJECT=project,
            CAPPROJECT=capproject,
            SUBARCH=subarch,
        )
        tool_name = f"tools/boot/{self.series}/boot-{self.arch}"
        with self.logger.logged(f"running {tool_name} ...", done_msg="... done"):
            self.logger.run(
                [
                    debian_cd_dir.joinpath(tool_name),
                    "1",
                    self.iso_root,
                ],
                env=env,
            )

    def checksum(self):
        # Generate md5sum.txt for ISO integrity verification.
        # - Symlinks are excluded because their targets are already checksummed
        # - Files are sorted for deterministic, reproducible output across builds
        # - Paths use "./" prefix and we run md5sum from iso_root so the output
        #   matches what casper-md5check expects.
        all_files = []
        for dirpath, dirnames, filenames in self.iso_root.walk():
            filepaths = [dirpath.joinpath(filename) for filename in filenames]
            all_files.extend(
                "./" + str(filepath.relative_to(self.iso_root))
                for filepath in filepaths
                if not filepath.is_symlink()
            )
        self.iso_root.joinpath("md5sum.txt").write_bytes(
            self.logger.run(
                ["md5sum"] + sorted(all_files),
                cwd=self.iso_root,
                stdout=subprocess.PIPE,
            ).stdout
        )

    def make_iso(self, dest: pathlib.Path, volid: str | None):
        # 1.mkisofs_opts is generated by debian-cd's make_bootable step. The "1"
        # refers to "pass 1" of the build (a legacy naming convention). It contains
        # architecture-specific xorriso options for boot sectors, EFI images, etc.
        mkisofs_opts = shlex.split(self.workdir.joinpath("1.mkisofs_opts").read_text())
        self.checksum()
        # xorriso with "-as mkisofs" runs in mkisofs compatibility mode.
        # -r enables Rock Ridge extensions for Unix metadata (permissions, symlinks).
        # -iso-level 3 (amd64 only) allows files >4GB which some amd64 ISOs need.
        cmd: list[str | pathlib.Path] = ["xorriso", "-as", "mkisofs", "-r"]
        if self.arch == "amd64":
            cmd.extend(["-iso-level", "3"])
        if volid:
            cmd += ["-V", volid]
        cmd += mkisofs_opts + [self.iso_root, "-o", dest]
        with self.logger.logged("running xorriso"):
            self.logger.run(cmd, cwd=self.workdir, check=True)
