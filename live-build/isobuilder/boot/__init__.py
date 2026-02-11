"""Boot configuration package for ISO builder.

This package contains architecture-specific boot configurators for building
bootable ISOs for different architectures.
"""

import pathlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..apt_state import AptStateManager
    from ..builder import Logger
    from .base import BaseBootConfigurator


def make_boot_configurator_for_arch(
    arch: str,
    logger: "Logger",
    apt_state: "AptStateManager",
    iso_root: pathlib.Path,
) -> "BaseBootConfigurator":
    """Factory function to create boot configurator for a specific architecture."""
    from .amd64 import AMD64BootConfigurator
    from .arm64 import ARM64BootConfigurator
    from .ppc64el import PPC64ELBootConfigurator
    from .riscv64 import RISCV64BootConfigurator
    from .s390x import S390XBootConfigurator

    if arch == "amd64":
        return AMD64BootConfigurator(logger, apt_state, iso_root)
    elif arch == "arm64":
        return ARM64BootConfigurator(logger, apt_state, iso_root)
    elif arch == "ppc64el":
        return PPC64ELBootConfigurator(logger, apt_state, iso_root)
    elif arch == "riscv64":
        return RISCV64BootConfigurator(logger, apt_state, iso_root)
    elif arch == "s390x":
        return S390XBootConfigurator(logger, apt_state, iso_root)
    else:
        raise ValueError(f"Unsupported architecture: {arch}")


__all__ = ["make_boot_configurator_for_arch"]
