# Understanding the parameters used by livecd-rootfs

`livecd-rootfs` is a confusing codebase. One of the confusing things is how
information flows into and around the image build process. There is
`IMAGEFORMAT` and `IMAGE_TARGETS` and `PROJECT` and many other variables. It
is not obvious when looking at the code if a given variable is something
passed as a parameter or something derived from it.

All (or almost all) production use of `livecd-rootfs` is via
`launchpad-buildd`, so the set of potential parameters is limited by the set
of environment variables `launchpad-buildd` can set in response to the build
request.

This document describes those parameters: what each one means, how it gets
from a Launchpad build request into the live-build environment, and how to
set it when invoking `build-livefs` (or `build-livefs-lxd`, which forwards
extra arguments through to `build-livefs` inside an LXD VM). For the
local-build workflow itself -- prerequisites, fetching artifacts, apt
caching, and features that only exist in the local path -- see
[README.local](README.local.md).

## From build request to live-build environment

The process from build request to the environment `live-build` runs in is a
little convoluted. The build request takes:

- **archive** -- where to get `livecd-rootfs` from.
- **distro_arch_series** -- the series to get `livecd-rootfs` from and to
  build.
- **pocket** -- pocket to get `livecd-rootfs` from; also influences whether
  `proposed` is used as a package source for the image being built.
- **unique_key** -- you cannot have more than one pending livefs build with
  the same `unique_key`. Does not affect the build at all.
- **version** -- optional version string (see [`NOW`](#now) below). Often a
  serial like `20250525.1`.
- **metadata_override** -- combined with the metadata on the livefs itself
  to make the metadata for this build.

(See the [Launchpad API
reference](https://launchpad.net/+apidoc/devel.html#livefs-requestBuild).)

These parameters are stored on the
[`LiveFSBuild`](https://git.launchpad.net/launchpad/tree/lib/lp/soyuz/model/livefsbuild.py#n372)
object and converted into a set of args passed to `launchpad-buildd` by the
[`LiveFSBuildBehaviour`](https://git.launchpad.net/launchpad/tree/lib/lp/soyuz/model/livefsbuildbehaviour.py#n99)
class.

Inside `launchpad-buildd`, these arguments are inspected by
[`LiveFilesystemBuildManager.initiate`](https://git.launchpad.net/launchpad-buildd/tree/lpbuildd/livefs.py#n24),
which turns them into arguments for the
[`BuildLiveFS`](https://git.launchpad.net/launchpad-buildd/tree/lpbuildd/target/build_livefs.py#n167)
`lpbuild` operation, which is what creates the environment `live-build` runs
in.

## Variables set for both `lb config` and `lb build`

- **`PROJECT`** -- mandatory; comes from `project` in the metadata.
- **`ARCH`** -- set to the ABI tag of the distroarchseries being built for.
- **`ARCH_VARIANT`** -- set to the ISA tag of the distroarchseries being
  built for, if it is different from the ABI tag.
- **`SUBPROJECT`** -- optional; comes from `subproject` in the metadata.
- **`SUBARCH`** -- optional; comes from `subarch` in the metadata.
- **`CHANNEL`** -- optional; comes from `channel` in the metadata.
- **`IMAGE_TARGETS`** -- optional; comes from `image_targets` in the
  metadata. `image_targets` is a list; `IMAGE_TARGETS` is set to
  `" ".join(image_targets)`.
- **`REPO_SNAPSHOT_STAMP`** -- optional; comes from `repo_snapshot_stamp` in
  the metadata.
- **`SNAPSHOT_SERVICE_TIMESTAMP`** -- optional; comes from
  `snapshot_service_timestamp` in the metadata.
- **`COHORT_KEY`** -- optional; comes from `cohort-key` in the metadata.

`launchpad-buildd` also contains code to set `http_proxy` / `HTTP_PROXY` /
`LB_APT_HTTP_PROXY`, but there does not appear to be any way to trigger this
when requesting a build.

## Variables set for `lb config` only

(Why are some things set for `lb config` only? No idea.)

- **`SUITE`** -- set to the name of the distroarchseries being built for.
- **`NOW`** -- set to the value of the `version` argument to the build
  request; defaults to `strftime("%Y%m%d-%H%M%S")`.
- **`IMAGEFORMAT`** -- optional; comes from `image_format` in the metadata.
- **`PROPOSED`** -- set to `"1"` if the pocket passed to the build request
  is `proposed`.
- **`EXTRA_PPAS`** -- optional; comes from `extra_ppas` in the metadata.
  `extra_ppas` is a list; `EXTRA_PPAS` is set to `" ".join(extra_ppas)`.
- **`EXTRA_SNAPS`** -- optional; comes from `extra_snaps` in the metadata.
  `extra_snaps` is a list; `EXTRA_SNAPS` is set to `" ".join(extra_snaps)`.
- **`BUILD_TYPE`** -- optional; the type (e.g. `Daily` or `Release`) of ISO
  being built. Goes into `.disk/info` on the ISO. Defaults to `Daily`.

What follows is an opinionated and slightly angry attempt to describe what
each of these is for. Each entry also lists the `build-livefs` flag that
sets the corresponding variable.

Finally, if you pass a true value for `debug` in the build metadata,
`launchpad-buildd` (or `build-livefs`, as appropriate) writes a
`local/functions/debug.sh` containing `set -x`, which causes live-build's
`auto` scripts to print every command they run. This can be useful to
understand what exactly happened when something has gone wrong.

## `PROJECT`

**Set with `build-livefs`:** `--project` (required)

This is the big one, the main variable that defines what is being built. It
can be `ubuntu`, `ubuntu-server`, `xubuntu`, `ubuntu-mini-iso`, that sort of
thing. Generally `PROJECT` determines the set of packages installed, but it
(unfortunately?) has a bit more impact than that.

It's unarguable that we need a parameter like this.

## `ARCH`

**Set with `build-livefs`:** `--arch` (defaults to the host architecture)

The architecture being built for. This is always the same as
`dpkg --print-architecture` for us; we don't do any cross builds.

It's kind of redundant, but it's not really a problem that this exists.

## `ARCH_VARIANT`

**Set with `build-livefs`:** `--arch-variant`

The variant being built for, i.e. the ISA tag of the distroarchseries. Only
set if this is different from the ABI tag.

This is definitely needed to be able to build images for variants.

## `SUBPROJECT`

**Set with `build-livefs`:** `--subproject`

This is used for some builds to build a different sort of build of the
project. It can be set to:

- `minimized` for `ubuntu-cpc` builds, to make a minimal cloud image.
- `minimal` for `xubuntu` builds, to make a smaller ISO.
- `desktop-preinstalled` for `ubuntu` builds, to make a preinstalled image
  instead an installer.
- `buildd` for images to be used as build images by craft tools, and also
  buildd chroots used on Launchpad builders?
- `live` for `ubuntu-server` builds, historically to distinguish d-i style
  installers from subiquity style installers.
- `desktop` for `ubuntu-core-installer` builds, to influence which model is
  used to build the Ubuntu Core system that will be installed.

_This_ parameter is a total mess. The `desktop-preinstalled` use feels
particularly egregious.

## `SUBARCH`

**Set with `build-livefs`:** `--subarch`

This identifies the target machine more specifically than `ARCH`,
e.g. `tegra-jetson` or `licheerv`. Used mostly but not exclusively for
preinstalled builds.

We probably do need something like this.

## `CHANNEL`

**Set with `build-livefs`:** `--channel`

Influences which channel snaps included in the build are taken from (via a
few different mechanisms).

## `IMAGE_TARGETS`

**Set with `build-livefs`:** `--image-target` (may be repeated; the values
are joined with spaces into `IMAGE_TARGETS`)

Passed for CPC (and `ubuntu-oem`, for some reason) builds to
`config/hooks.d/make-hooks`, which uses it to select which binary hooks to
run (and so determines which artifacts get produced).

It is probably reasonable that this exists.

## `REPO_SNAPSHOT_STAMP`

**Set with `build-livefs`:** `--repo-snapshot-stamp`

Currently unused.

## `SNAPSHOT_SERVICE_TIMESTAMP`

**Set with `build-livefs`:** `--snapshot-service-timestamp`

Also currently unused, and unclear how it differs from `REPO_SNAPSHOT_STAMP`.

## `COHORT_KEY`

**Set with `build-livefs`:** `--cohort-key`

Used to make sure that different builds run at the same time don't get
different versions of snaps due to phasing differences.

This is a totally valid thing to need to supply.

## `http_proxy` / `HTTP_PROXY` / `LB_APT_HTTP_PROXY`

**Set with `build-livefs`:** `--http-proxy` (or set `http-proxy` in the
`[defaults]` section of `~/.config/livecd-rootfs/build-livefs.conf`; see
[README.local](README.local.md))

Nothing complex here! Note that there is no way to set this through a
Launchpad build request -- it is only reachable via the local path.

## `SUITE`

**Set with `build-livefs`:** `--suite` (required)

This is the series being built (e.g. `noble`, `questing`). It is misnamed
really -- a suite is usually a combination of a series and a pocket
(`noble-proposed`, `questing-security`).

As with `ARCH` this is sort of redundant, as we do builds in a chroot of the
series being built, but on the other hand it is definitely information the
build needs to know!

## `NOW`

**Set with `build-livefs`:** `--datestamp`

The serial for the build, e.g. `20250519` or `20240418.4`.

It is a totally reasonable parameter.

## `IMAGEFORMAT`

**Set with `build-livefs`:** `--image-format`

This is one of the more incoherently handled parameters. In rough outline it
is the filesystem of the image we produce.

Installer builds do not produce raw images, so this ends up being set to
`plain` (which causes live-build to just leave the rootfs as a directory
tree) or `none` (which causes live-build to do roughly the same thing but in
a different way?).

Image builds that use `ubuntu-image` set it to `ubuntu-image`. These builds
do not call `lb build` or `lb binary`.

Other preinstalled images (mostly CPC images) set it to `ext4` (but then use
`live-build/ubuntu-cpc/hooks.d/remove-implicit-artifacts` to remove the
output file that this causes live-build to produce...). Some projects rely
on this being set via metadata when building the project, it seems.

It can be set when starting an image build, but most builds do not, and the
behavior when it is not set explicitly is pretty confusing.

This place is not a place of honor.

## `PROPOSED`

**Set with `build-livefs`:** `--proposed` (flag, no value)

Should packages from `proposed` be included?

This is not really as useful as it used to be for a bunch of reasons but it
conceptually makes sense.

## `EXTRA_PPAS`

**Set with `build-livefs`:** `--extra-ppa` (may be repeated; the values are
joined with spaces into `EXTRA_PPAS`)

Extra archives to get packages from.

This is a space-separated list by the time it gets to `livecd-rootfs`. Each
element of the list is of the form `USER/NAME[:PIN]`, where `USER` is a
Launchpad user/team name, `NAME` is the name of the PPA to add, and the
optional `:PIN` at the end is the value to pin (in the
`apt_preferences(5)` sense) packages from this PPA at.

Production builds shouldn't really use this, but it's definitely useful for
development.

## `EXTRA_SNAPS`

**Set with `build-livefs`:** `--extra-snap` (may be repeated; the values are
joined with spaces into `EXTRA_SNAPS`)

Extra snaps to include (but only for `ubuntu-image`-based builds).

## `BUILD_TYPE`

**Set with `build-livefs`:** `--build-type`

Before release, the `.disk/info` on an ISO looks like:

```
Ubuntu-Server 26.04 LTS "Resolute Raccoon" - Daily amd64 (20260210)
```

After release it looks like:

```
Ubuntu-Server 26.04 LTS "Resolute Raccoon" - Release amd64 (20270210)
```

We could do a `livecd-rootfs` upload to change this (it only changes once
per cycle), but it's quicker and easier to manage this from the code that
triggers the livefs builds.
