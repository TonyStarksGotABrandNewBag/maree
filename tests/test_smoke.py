"""Module-level smoke test: verify the package imports and exposes the expected version."""

import src


def test_version():
    assert src.__version__ == "0.0.1"
