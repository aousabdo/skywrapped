from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "headers"


def _fixture(name: str) -> bytes:
    return (FIXTURES / f"{name}.hdr").read_bytes()


@pytest.fixture
def fixture():
    """Return a function that loads tests/fixtures/headers/<name>.hdr as bytes."""
    return _fixture


@pytest.fixture
def fixture_dir(tmp_path):
    """A folder holding every header fixture as Light_<stem>.fit (the header plus 2880 zero bytes)."""
    d = tmp_path / "fixture_dir"
    d.mkdir()
    for hdr in sorted(FIXTURES.glob("*.hdr")):
        (d / f"Light_{hdr.stem}.fit").write_bytes(hdr.read_bytes() + b"\0" * 2880)
    return d
