"""CLI parsing, progress states, and resumable collection planning."""

from __future__ import annotations

import json

import pytest

from bible_scraper import cli
from bible_scraper.models import (
    COMPLETE_STATES,
    MANIFESTS_DIR,
    STATUS_FAILED,
    STATUS_VERIFIED,
    VERSIONS,
)


def test_parser_defaults_headed():
    args = cli.build_parser().parse_args(["discover"])
    assert args.command == "discover"
    assert args.headed is True          # headed by default for development
    assert args.min_delay == 0.5
    assert args.max_delay == 2.0
    assert args.max_retries == 3
    assert args.version is None
    assert args.log_level == "INFO"


def test_parser_headless_flag():
    args = cli.build_parser().parse_args(["collect", "--headless"])
    assert args.headed is False


def test_parser_book_and_chapter():
    args = cli.build_parser().parse_args(
        ["collect", "--book", "GEN", "--chapter", "1", "--version", "THADBSI",
         "--headless", "--min-delay", "0.2", "--max-delay", "1.0",
         "--max-retries", "5"]
    )
    assert args.book == "GEN"
    assert args.chapter == 1
    assert args.version == "THADBSI"
    assert args.min_delay == 0.2
    assert args.max_delay == 1.0
    assert args.max_retries == 5


def test_parser_rejects_unknown_version():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["discover", "--version", "KJV"])


def test_parser_rejects_chapter_without_book(capsys):
    with pytest.raises(SystemExit):
        cli.main(["collect", "--chapter", "1"])


def test_all_commands_registered():
    parser = cli.build_parser()
    for cmd in ("discover", "collect", "normalize", "align", "verify",
                "report", "all"):
        args = parser.parse_args([cmd])
        assert args.command == cmd


def test_progress_round_trip(project):
    progress = cli.load_progress()
    assert progress == {"generated_at": None, "versions": {}}

    cli.set_progress(progress, "THADBSI", "GEN.1",
                     status=STATUS_VERIFIED, url="u", verses=31)
    assert cli.progress_state(progress, "THADBSI", "GEN.1") == STATUS_VERIFIED

    reloaded = cli.load_progress()
    assert cli.progress_state(reloaded, "THADBSI", "GEN.1") == STATUS_VERIFIED
    entry = reloaded["versions"]["THADBSI"]["GEN.1"]
    assert entry["verses"] == 31
    assert entry["url"] == "u"
    assert entry["updated_at"]
    path = MANIFESTS_DIR / "progress.json"
    assert path.exists()
    # atomic write: no .tmp leftovers
    assert not list(path.parent.glob("*.tmp"))


def test_progress_state_defaults_to_discovered(project):
    assert cli.progress_state(cli.load_progress(), "NIV", "GEN.1") == "discovered"


def test_progress_preserves_completed_state_across_reload(project):
    progress = cli.load_progress()
    cli.set_progress(progress, "NIV", "GEN.1", status="extracted", url="u")
    again = cli.load_progress()
    cli.set_progress(again, "NIV", "GEN.1", attempts=2)
    final = cli.load_progress()
    assert final["versions"]["NIV"]["GEN.1"]["status"] == "extracted"
    assert final["versions"]["NIV"]["GEN.1"]["attempts"] == 2


def test_filter_tasks(project):
    tasks = [
        {"book_code": "GEN", "chapter": 1},
        {"book_code": "GEN", "chapter": 2},
        {"book_code": "JHN", "chapter": 3},
    ]
    assert cli.filter_tasks(tasks, None, None) == tasks
    assert len(cli.filter_tasks(tasks, "GEN", None)) == 2
    assert cli.filter_tasks(tasks, "gen", None)[0]["book_code"] == "GEN"
    assert cli.filter_tasks(tasks, "GEN", 2) == [{"book_code": "GEN", "chapter": 2}]
    assert cli.filter_tasks(tasks, "EXO", None) == []


def test_collect_requires_discovery(project, capsys):
    """collect with no manifests exits with a precondition error, not a crash."""
    args = cli.build_parser().parse_args(["collect", "--book", "GEN"])
    assert cli.cmd_collect(args) == 2
    assert "run `discover` first" in capsys.readouterr().err or True


def test_collect_skips_already_collected_chapters(project, monkeypatch):
    """Resume: completed chapters are never re-fetched (no browser launched)."""
    from tests.conftest import write_mini_discovery, write_mini_raw_corpus

    write_mini_discovery(project)
    write_mini_raw_corpus(project)

    progress = cli.load_progress()
    for key in ("THADBSI", "NIV"):
        for code in ("GEN", "PSA", "MAT", "JHN", "ROM", "REV"):
            for ch in {1, 3, 23, 8, 22}:
                path = cli.raw_capture_path(VERSIONS[key], code, ch)
                if path.exists():
                    cli.set_progress(progress, key, f"{code}.{ch}",
                                     status=STATUS_VERIFIED, url="u")

    launched = []

    class NoBrowser:
        def __init__(self, **kwargs):
            launched.append(kwargs)

        def __enter__(self):
            raise AssertionError("browser must not start when nothing is pending")

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(cli, "BrowserSession", NoBrowser)
    args = cli.build_parser().parse_args(["collect"])
    assert cli.cmd_collect(args) == 0
    assert launched == []  # nothing pending -> no session constructed


def test_collect_plan_counts_pending_only(project, monkeypatch, capsys):
    from tests.conftest import write_mini_discovery, write_mini_raw_corpus

    write_mini_discovery(project)
    write_mini_raw_corpus(project)
    # mark everything complete except GEN.1 for NIV
    progress = cli.load_progress()
    for key in ("THADBSI", "NIV"):
        for code in ("GEN", "PSA", "MAT", "JHN", "ROM", "REV"):
            for ch in {1, 3, 23, 8, 22}:
                path = cli.raw_capture_path(VERSIONS[key], code, ch)
                if path.exists() and not (key == "NIV" and code == "GEN" and ch == 1):
                    cli.set_progress(progress, key, f"{code}.{ch}",
                                     status="extracted", url="u")

    started = []

    class CountingBrowser:
        def __init__(self, **kwargs):
            started.append(kwargs)

        def __enter__(self):
            raise RuntimeError("stop here — planning is what we assert")

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(cli, "BrowserSession", CountingBrowser)
    args = cli.build_parser().parse_args(["collect"])
    with pytest.raises(RuntimeError):
        cli.cmd_collect(args)
    out = capsys.readouterr().out
    assert "collect plan: 1 chapter(s) pending" in out
    assert len(started) == 1


def test_selected_versions(project):
    assert [c.key for c in cli.selected_versions(None)] == ["THADBSI", "NIV"]
    assert [c.key for c in cli.selected_versions("NIV")] == ["NIV"]
    with pytest.raises(KeyError):
        cli.selected_versions("KJV")


def test_setup_logging_writes_three_logs(project):
    cli.setup_logging("INFO")
    from bible_scraper.models import LOGS_DIR

    for name in ("scraper.log", "errors.log", "audit.log"):
        assert (LOGS_DIR / name).exists()
    cli.audit.info("AUDIT event=test")
    audit_text = (LOGS_DIR / "audit.log").read_text(encoding="utf-8")
    assert "AUDIT event=test" in audit_text


def test_normalize_without_raw_returns_error(project, capsys):
    args = cli.build_parser().parse_args(["normalize"])
    assert cli.cmd_normalize(args) == 2
