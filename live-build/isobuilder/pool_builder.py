import pathlib
import subprocess
import tempfile

from isobuilder.apt_state import AptStateManager, PackageInfo


generate_template = """
Dir::ArchiveDir "{root}";
Dir::CacheDir "{scratch}/apt-ftparchive-db";

TreeDefault::Contents " ";

Tree "dists/{series}" {{
    FileList "{scratch}/filelist_$(SECTION)";
    Sections "{components}";
    Architectures "{arches}";
}}
"""


class PoolBuilder:

    def __init__(
        self, logger, series: str, apt_state: AptStateManager, rootdir: pathlib.Path
    ):
        self.logger = logger
        self.series = series
        self.apt_state = apt_state
        self.rootdir = rootdir
        self.arches: set[str] = set()
        self._present_components: set[str] = set()

    def add_packages(self, pkglist: list[PackageInfo]):
        for pkg_info in pkglist:
            if pkg_info.architecture != "all":
                self.arches.add(pkg_info.architecture)
            self.apt_state.download(self.rootdir, pkg_info)

    def make_packages(self) -> None:
        with self.logger.logged("making Packages files"):
            with tempfile.TemporaryDirectory() as tmpdir:
                scratchdir = pathlib.Path(tmpdir)
                with self.logger.logged("scanning for packages"):
                    for component in ["main", "restricted", "universe", "multiverse"]:
                        if not self.rootdir.joinpath("pool", component).is_dir():
                            continue
                        self._present_components.add(component)
                        for arch in self.arches:
                            self.rootdir.joinpath(
                                "dists", self.series, component, f"binary-{arch}"
                            ).mkdir(parents=True)
                        proc = self.logger.run(
                            ["find", f"pool/{component}"],
                            stdout=subprocess.PIPE,
                            cwd=self.rootdir,
                            encoding="utf-8",
                            check=True,
                        )
                        scratchdir.joinpath(f"filelist_{component}").write_text(
                            "\n".join(sorted(proc.stdout.splitlines()))
                        )
                with self.logger.logged("writing apt-ftparchive config"):
                    scratchdir.joinpath("apt-ftparchive-db").mkdir()
                    generate_path = scratchdir.joinpath("generate-binary")
                    generate_path.write_text(
                        generate_template.format(
                            arches=" ".join(self.arches),
                            series=self.series,
                            root=self.rootdir.resolve(),
                            scratch=scratchdir.resolve(),
                            components=" ".join(self._present_components),
                        )
                    )
                with self.logger.logged("running apt-ftparchive generate"):
                    self.logger.run(
                        [
                            "apt-ftparchive",
                            "--no-contents",
                            "--no-md5",
                            "--no-sha1",
                            "--no-sha512",
                            "generate",
                            generate_path,
                        ],
                        check=True,
                    )

    def make_release(self) -> pathlib.Path:
        # Build the Release file by merging metadata from the mirror with
        # checksums for our pool. We can't just use apt-ftparchive's Release
        # output directly because:
        # 1. apt-ftparchive doesn't know about Origin, Label, Suite, Version,
        #    Codename, etc. - these come from the mirror and maintain package
        #    provenance
        # 2. We keep the mirror's Date (when packages were released) rather than
        #    apt-ftparchive's Date (when we ran the command)
        # 3. We need to override Architectures/Components to match our pool
        #
        # There may be a cleaner way (apt-get indextargets?) but this works.
        with self.logger.logged("making Release file"):
            in_release = self.apt_state.in_release_path()
            cp_mirror_release = self.logger.run(
                ["gpg", "--verify", "--output", "-", in_release],
                stdout=subprocess.PIPE,
                encoding="utf-8",
                check=False,
            )
            if cp_mirror_release.returncode not in (0, 2):
                # gpg returns code 2 when the public key the InRelease is
                # signed with is not available, which is most of the time.
                raise Exception("gpg failed")
            mirror_release_lines = cp_mirror_release.stdout.splitlines()
            release_dir = self.rootdir.joinpath("dists", self.series)
            af_release_lines = self.logger.run(
                [
                    "apt-ftparchive",
                    "--no-contents",
                    "--no-md5",
                    "--no-sha1",
                    "--no-sha512",
                    "release",
                    ".",
                ],
                stdout=subprocess.PIPE,
                encoding="utf-8",
                cwd=release_dir,
                check=True,
            ).stdout.splitlines()
            # Build the final Release file by merging mirror metadata with pool
            # checksums.
            # Strategy:
            # 1. Take metadata fields (Suite, Origin, etc.) from the mirror's InRelease
            # 2. Override Architectures and Components to match what's actually in our
            #    pool
            # 3. Skip the mirror's checksum sections (MD5Sum, SHA256, etc.) because they
            #    don't apply to our pool
            # 4. Skip Acquire-By-Hash since we don't use it
            # 5. Append checksums from apt-ftparchive (but not the Date field)
            release_lines = []
            skipping = False
            for line in mirror_release_lines:
                if line.startswith("Architectures:"):
                    line = "Architectures: " + " ".join(sorted(self.arches))
                elif line.startswith("Components:"):
                    line = "Components: " + " ".join(sorted(self._present_components))
                elif line.startswith("MD5") or line.startswith("SHA"):
                    # Start of a checksum section - skip this and indented lines below
                    # it
                    skipping = True
                elif not line.startswith(" "):
                    # Non-indented line means we've left the checksum section if we were
                    # in one.
                    skipping = False
                if line.startswith("Acquire-By-Hash"):
                    continue
                if not skipping:
                    release_lines.append(line)
            # Append checksums from apt-ftparchive, but skip its Date field
            # (we want to keep the Date from the mirror release)
            for line in af_release_lines:
                if not line.startswith("Date"):
                    release_lines.append(line)
            release_path = release_dir.joinpath("Release")
            release_path.write_text("\n".join(release_lines))
            return release_path
