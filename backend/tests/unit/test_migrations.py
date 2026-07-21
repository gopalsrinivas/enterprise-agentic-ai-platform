"""Database-independent Alembic structure tests."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_has_single_phase_four_head() -> None:
    backend_root = Path(__file__).parents[2]
    config = Config(str(backend_root / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)

    assert scripts.get_heads() == ["20260721_0003"]
    phase_three = scripts.get_revision("20260721_0002")
    assert phase_three is not None
    assert phase_three.down_revision == "20260721_0001"
    phase_four = scripts.get_revision("20260721_0003")
    assert phase_four is not None
    assert phase_four.down_revision == "20260721_0002"
    revision = scripts.get_revision("20260721_0001")
    assert revision is not None
    assert revision.down_revision is None
