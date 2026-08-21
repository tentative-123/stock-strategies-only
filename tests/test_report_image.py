from datetime import datetime
from pathlib import Path

from stock_strategies.report_image import build_report_html, render_report_png


def _signal(stock_id: str, action: str) -> dict:
    return {
        "stock_id": stock_id,
        "name": f"<股票 {stock_id}>",
        "action": action,
        "signal_score": 72,
        "risk_reward_ratio": 1.25,
        "risk_notes": ["歷史勝率 49% 低於五成"],
        "components": {
            "tech_score": 65,
            "backtest_winrate": 0.61,
            "tech_signals": ["MACD多頭"],
        },
        "trend": {"chg_5d": 2.1, "chg_20d": 4.2, "above_ma20": True},
    }


def test_build_report_html_has_stable_sections_and_limits():
    buys = [_signal(f"B{i}", "BUY") for i in range(6)]
    watches = [_signal(f"W{i}", "WATCH") for i in range(4)]
    watchlist = [
        {"stock_id": stock["stock_id"], "category": "AI伺服器"}
        for stock in buys + watches
    ]

    report = build_report_html(
        buys + watches,
        watchlist,
        market={"note": "大盤站上月線"},
        night_note="夜盤中性",
        report_date=datetime(2026, 8, 21),
    )

    assert "每日選股一頁報" in report
    assert "今日預計強勢股" in report
    assert "今日可關注股" in report
    assert "族群動能" in report
    assert "2026 / 08 / 21" in report
    assert "B4" in report and "B5" not in report
    assert "W2" in report and "W3" not in report
    assert "&lt;股票 B0&gt;" in report
    assert "歷史勝率 49% 低於五成" not in report


def test_render_report_png_invokes_headless_chrome(tmp_path, monkeypatch, mocker):
    monkeypatch.setenv("CHROME_BIN", "/test/chrome")
    output = tmp_path / "report.png"

    def fake_run(command, **kwargs):
        screenshot_arg = next(arg for arg in command if arg.startswith("--screenshot="))
        Path(screenshot_arg.split("=", 1)[1]).write_bytes(b"png")

    run = mocker.patch(
        "stock_strategies.report_image.subprocess.run", side_effect=fake_run
    )

    result = render_report_png("<html><body>report</body></html>", output)

    assert result == output.resolve()
    assert output.read_bytes() == b"png"
    assert not output.with_suffix(".html").exists()
    assert "--headless=new" in run.call_args.args[0]
