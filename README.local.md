# Running livecd-rootfs builds locally

`livecd-rootfs` is notoriously known to be... difficult? One question that
often comes back is "how do I run that locally?". This document covers the
two scripts in `live-build/` that are intended for local use:

- `build-livefs` runs an `lb config` / `lb build` cycle in the current working
  directory. It needs root (it uses `sudo` if you don't run it as root) and
  installs all of `livecd-rootfs`'s dependencies on the host machine.
- `build-livefs-lxd` is a wrapper that does the same thing inside a freshly
  launched LXD VM, so you don't have to touch your host. This is the one you
  almost always want.

For what each parameter (PROJECT, SUITE, SUBPROJECT, ...) actually means, see
[README.parameters](README.parameters.md). This document only covers the
mechanics of driving the local scripts.

## Quickstart with `build-livefs-lxd`

You need LXD installed and configured (https://canonical.com/lxd/install) and
a clone of this repository. `build-livefs-lxd`:

  * launches (or restarts) an LXD VM for the series you're targeting,
  * installs `livecd-rootfs` from the archive inside it (so all the build
    dependencies are present),
  * mounts your local checkout at `/srv/livecd-rootfs` inside the VM (so you
    can iterate on the code without rebuilding the VM),
  * runs `/srv/livecd-rootfs/live-build/build-livefs` inside `/build`, passing
    along any extra arguments you give.

Examples:

```console
# Very fast and lightweight "fake" ISO
❯ ./live-build/build-livefs-lxd --suite resolute --project ubuntu-test-iso

# Ubuntu Desktop -- the flagship, and probably the most complex ISO
❯ ./live-build/build-livefs-lxd --suite resolute --project ubuntu

# Ubuntu Server Live (lighter ISO)
❯ ./live-build/build-livefs-lxd --suite resolute --project ubuntu-server --subproject live

# Xubuntu Minimal (lighter desktop ISO)
❯ ./live-build/build-livefs-lxd --suite resolute --project xubuntu --subproject minimal
```

Every flag accepted by `build-livefs` other than `--suite` is forwarded
through; see [README.parameters](README.parameters.md) for the full list.
`--arch` defaults to the host architecture.

## Fetching artifacts out of the VM

The build runs in `/build` inside the VM (matching `launchpad-buildd`'s
layout). Pass `--output DIR` to have `build-livefs-lxd` copy every
`livecd.*` file from `/build` into `DIR` after the build:

```console
❯ ./live-build/build-livefs-lxd --suite resolute --project ubuntu-test-iso \
    --output ./out
❯ ls ./out
livecd.ubuntu-test-iso.iso  ...
```

If you'd rather do it by hand:

```console
❯ lxc file pull livefs-builder-resolute/build/livecd.ubuntu-test-iso.iso ./
```

The VM is named `livefs-builder-{suite}` by default; override with `--vm-name`
if you want to keep multiple VMs around simultaneously.

To boot the resulting ISO:

```console
❯ kvm -m 3G -smp 2 -cdrom ./out/livecd.ubuntu-test-iso.iso
```

## Cleaning up

The VM keeps running between invocations (so subsequent builds can reuse the
installed packages and any apt cache). When you're done:

```console
❯ lxc stop livefs-builder-resolute
❯ lxc delete livefs-builder-resolute
```

## Speeding things up with `apt-cacher-ng`

Iteration time is dominated by package downloads. Running `apt-cacher-ng` on
the host and pointing the build at it speeds things up dramatically,
especially if you're not in one of Canonical's datacenters.

```console
❯ sudo apt install apt-cacher-ng
```

Configure the build to use it via `~/.config/livecd-rootfs/build-livefs.conf`
on the host (it's pushed into the VM automatically):

```ini
[defaults]
mirror = http://192.168.0.42:3142/archive.ubuntu.com/ubuntu
```

`192.168.0.42` is your host's IP on a network the LXD VM can reach. You can
also point this at squid running in a container of its own, or probably several
other ways of running a caching HTTP proxy.

## Running `build-livefs` directly (without LXD)

You can run `build-livefs` on the host if you really want to -- e.g. you're
already inside a disposable VM, or you're debugging the wrapper itself. It
needs to run as root (or via `sudo`, which it will arrange itself if needed)
because the build does `mount` and `chroot`, and it will install
`livecd-rootfs`'s dependencies on whatever system it runs on.

```console
❯ mkdir build && cd build
❯ /path/to/livecd-rootfs/live-build/build-livefs --suite resolute --project ubuntu-test-iso
```

`--work-dir DIR` lets you point at a build directory other than the current
one.

## Features only available in the local path

A few `build-livefs` flags have no equivalent in the Launchpad build request
path:

- `--mirror URL` sets the `MIRROR` environment variable, overriding the
  archive URL the build would otherwise pick. Without it, the build
  auto-detects: it uses `http://ftpmaster.internal/ubuntu/` if reachable,
  otherwise `http://archive.ubuntu.com/ubuntu/` (or `ports.ubuntu.com` for
  non-x86 architectures). Set this to point at an `apt-cacher-ng` instance
  (see above) or a local mirror.
- `--http-proxy URL` sets `http_proxy`, `HTTP_PROXY`, and `LB_APT_HTTP_PROXY`
  for the build. `launchpad-buildd` has code that can set these but no way
  to trigger it from a build request, so in practice the local path is the
  only way to do it. `build-livefs-lxd` also accepts `--http-proxy` and uses
  it to configure apt inside the VM via cloud-init when the VM is first
  launched.
- `--work-dir DIR` lets `build-livefs` operate in a directory other than the
  current one.

## Config file defaults

`~/.config/livecd-rootfs/build-livefs.conf` is read by both `build-livefs`
and `build-livefs-lxd`. It uses INI format with a `[defaults]` section:

```ini
[defaults]
http-proxy = http://squid.internal:3128/
mirror = http://ftpmaster.internal/ubuntu/
```

Any value here is used when the corresponding command-line flag is not
passed. `build-livefs-lxd` pushes this file into the VM before running the
build, so the same defaults apply there.
