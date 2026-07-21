"""Database-independent Alembic structure tests."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_has_single_phase_two_baseline_head() -> None:
    backend_root = Path(__file__).parents[2]
    config = Config(str(backend_root / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)

    assert scripts.get_heads() == ["20260721_0001"]
    revision = scripts.get_revision("20260721_0001")
    assert revision is not None
    assert revision.down_revision is None
