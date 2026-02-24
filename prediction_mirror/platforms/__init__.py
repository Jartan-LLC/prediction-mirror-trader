from __future__ import annotations

from prediction_mirror.platforms.base import PlatformAdapter

_REGISTRY: dict[str, type[PlatformAdapter]] = {}


def register_adapter(name: str, cls: type[PlatformAdapter]) -> None:
    _REGISTRY[name] = cls


def get_adapter_class(platform_name: str) -> type[PlatformAdapter]:
    """Returns the adapter CLASS. Caller instantiates via cls.from_env()."""
    try:
        return _REGISTRY[platform_name]
    except KeyError:
        available = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise KeyError(
            f"Unknown platform: {platform_name!r}. Available: {available}"
        ) from None


__all__ = ["PlatformAdapter", "register_adapter", "get_adapter_class"]
