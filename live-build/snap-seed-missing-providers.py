#!/usr/bin/python3

"""
Usage: snap-seed-add-providers $SEED_DIR

Check the snaps referenced by the $SEED_DIR/seed.yaml and print any
missing providers.

"""

import contextlib
import pathlib
import subprocess
import sys
import tempfile
import yaml


@contextlib.contextmanager
def mounted(thing, target):
    subprocess.run(["mount", "-r", thing, target], check=True)
    try:
        yield
    finally:
        subprocess.run(["umount", target], check=True)


def main(argv):
    seed_dir = pathlib.Path(argv[0])
    assert seed_dir.is_dir()
    with seed_dir.joinpath("seed.yaml").open() as fp:
        seed = yaml.safe_load(fp)
    snap_files = set()
    snap_names = set()
    for snap_info in seed["snaps"]:
        snap_files.add(snap_info["file"])
        snap_names.add(snap_info["name"])
    tempdir = pathlib.Path(tempfile.mkdtemp())
    for snap_file in snap_files:
        snap = seed_dir.joinpath("snaps", snap_file)
        with mounted(snap, tempdir):
            with tempdir.joinpath("meta/snap.yaml").open() as fp:
                metadata = yaml.safe_load(fp)
        for plug_name, plug_info in metadata.get("plugs", {}).items():
            if plug_info.get("interface") == "content":
                default_provider = plug_info.get("default-provider")
                if default_provider and default_provider not in snap_names:
                    print(default_provider)
                    snap_names.add(default_provider)


if __name__ == "__main__":
    main(sys.argv[1:])
