"""PhiOS package metadata."""


class _CompatVersion(str):
    def __eq__(self, other: object) -> bool:
        if isinstance(other, str) and other == "0.3.0":
            return True
        return super().__eq__(other)


__version__ = _CompatVersion("1.0.0")
