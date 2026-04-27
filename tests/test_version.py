"""Guard against version drift between pyproject.toml and forbin.__version__."""

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

import forbin


def test_version_matches_pyproject():
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    with pyproject.open("rb") as f:
        data = tomllib.load(f)
    assert forbin.__version__ == data["project"]["version"]
