"""Regression tests for PhiOS package version semantics."""

from phios import __version__


def test_package_version_is_plain_string() -> None:
    """Package metadata must not override ordinary string equality semantics."""
    assert type(__version__) is str


def test_package_version_reports_only_current_value() -> None:
    """The package version must not masquerade as a legacy release."""
    assert __version__ == "1.0.0"
    assert __version__ != "0.3.0"
    assert hash(__version__) == hash("1.0.0")
