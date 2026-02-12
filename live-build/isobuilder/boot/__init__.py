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
    match arch:
        case "amd64":
            from .amd64 import AMD64BootConfigurator

            return AMD64BootConfigurator(logger, apt_state, iso_root)
        case "arm64":
            from .arm64 import ARM64BootConfigurator

            return ARM64BootConfigurator(logger, apt_state, iso_root)
        case "ppc64el":
            from .ppc64el import PPC64ELBootConfigurator

            return PPC64ELBootConfigurator(logger, apt_state, iso_root)
        case "riscv64":
            from .riscv64 import RISCV64BootConfigurator

            return RISCV64BootConfigurator(logger, apt_state, iso_root)
        case "s390x":
            from .s390x import S390XBootConfigurator

            return S390XBootConfigurator(logger, apt_state, iso_root)
        case _:
            raise ValueError(f"Unsupported architecture: {arch}")


__all__ = ["make_boot_configurator_for_arch"]
