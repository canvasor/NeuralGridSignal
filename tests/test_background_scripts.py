from pathlib import Path


def test_background_scheduler_scripts_exist_and_are_executable():
    scripts = [
        Path("scripts/start_scheduler.sh"),
        Path("scripts/stop_scheduler.sh"),
        Path("scripts/status_scheduler.sh"),
    ]

    for script in scripts:
        assert script.exists(), f"{script} missing"
        assert script.stat().st_mode & 0o111, f"{script} is not executable"


def test_start_scheduler_uses_nohup_schedule_and_pidfile():
    content = Path("scripts/start_scheduler.sh").read_text(encoding="utf-8")

    assert "nohup" in content
    assert "python3 -m neural_grid_signal --schedule" in content
    assert "run/grid_signal.pid" in content
    assert "logs/grid_signal.log" in content
    assert "logs/grid_signal.out" in content


def test_stop_and_status_use_same_pidfile():
    stop = Path("scripts/stop_scheduler.sh").read_text(encoding="utf-8")
    status = Path("scripts/status_scheduler.sh").read_text(encoding="utf-8")

    assert "run/grid_signal.pid" in stop
    assert "run/grid_signal.pid" in status
