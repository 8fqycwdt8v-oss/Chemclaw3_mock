"""The warehouse fixture holds the seeded records, and answers the source eval as the key does."""

import duckdb

from app.config import settings
from app.eln import source_eval
from app.eln.seed import seed_all
from app.warehouse import COLUMNS, build_warehouse


def test_the_warehouse_holds_every_seeded_record(client):
    rows = build_warehouse(settings.warehouse_path)
    with duckdb.connect(str(settings.warehouse_path), read_only=True) as connection:
        assert connection.execute("SELECT count(*) FROM reactions").fetchone()[0] == rows
        names = [row[0] for row in connection.execute("DESCRIBE reactions").fetchall()]
        sources = dict(connection.execute(
            "SELECT source, count(*) FROM reactions GROUP BY source").fetchall())
    assert names == [name for name, _ in COLUMNS]
    assert set(sources) == {"eln-json", "eln-ord"}


def test_the_warehouse_answers_two_eval_questions_as_the_key_does(tmp_path, monkeypatch):
    """At full scale, so the numbers are the ones the probe file quotes."""
    monkeypatch.setattr(settings, "eln_export_dir", tmp_path / "eln")
    monkeypatch.setattr(settings, "ord_export_dir", tmp_path / "ord")
    monkeypatch.setattr(settings, "hte_max_records_per_dataset", 0)
    seed_all(reset=True)
    path = tmp_path / "reactions.duckdb"
    build_warehouse(path)
    key = source_eval.answer_key()
    with duckdb.connect(str(path), read_only=True) as connection:
        wells, at_least_50 = connection.execute(
            "SELECT count(*), count(*) FILTER (WHERE yield_percent >= 50) FROM reactions "
            "WHERE list_contains(reactants, ?) AND list_contains(reactants, ?)",
            [source_eval.BROMOANISOLE, source_eval.METHYLANILINE],
        ).fetchone()
        beta = dict(connection.execute(
            "SELECT record_id, yield_percent FROM reactions "
            "WHERE source = 'eln-json' AND project = 'PROJ-BETA'").fetchall())
    assert {"wells": wells, "at_least_50": at_least_50} == key["sq-01"]
    assert beta == key["ns-01"]


def test_a_rebuild_replaces_the_file_whole(client):
    first = build_warehouse(settings.warehouse_path)
    assert build_warehouse(settings.warehouse_path) == first
    assert not settings.warehouse_path.with_suffix(".building").exists()
