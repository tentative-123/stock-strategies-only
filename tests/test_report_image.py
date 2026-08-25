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
            "chip_score": 73,
            "chip_backtest_winrate": 0.64,
            "chip_backtest_samples": 18,
            "chip_signals": ["外資投信同步買超"],
            "tech_signals": ["MACD多頭"],
            "volume_patterns": ["梯量柱"],
            "volume_verdict": "量能階梯推升，走勢健康",
        },
        "trend": {
            "chg_5d": 2.1,
            "chg_20d": 4.2,
            "vol_ratio": 1.3,
            "above_ma20": True,
            "above_ma60": True,
        },
    }


def test_build_report_html_has_stable_sections_and_limits():
    buys = [_signal(f"B{i}", "BUY") for i in range(6)]
    watches = [_signal(f"W{i}", "WATCH") for i in range(4)]
    watchlist = [
        {"stock_id": stock["stock_id"], "category": "AI伺服器"}
        for stock in buys + watches
    ]

    history = [
        {
            "date": f"2026-07-{index + 1:02d}",
            "open": 22000 + index,
            "high": 22100 + index,
            "low": 21900 + index,
            "close": 22050 + index,
            "volume": 100000 + index * 100,
            "ma5": 22040 + index,
            "ma10": 22030 + index,
            "ma20": 22020 + index,
            "ma60": 22010 + index,
        }
        for index in range(30)
    ]
    report = build_report_html(
        buys + watches,
        watchlist,
        market={"note": "大盤站上月線", "history": history},
        night_note="夜盤中性",
        report_date=datetime(2026, 8, 21),
    )

    assert "0050追蹤選股日報" in report
    assert "今日預計強勢股" in report
    assert "今日可關注股" in report
    assert "族群動能" not in report
    assert "加權指數｜日 K 趨勢" in report
    assert "MA5" in report and "MA10" in report and "MA20" in report and "MA60" in report
    assert "class=\"candle rise\"" in report
    assert "class=\"volume rise\"" in report
    assert "grid-template-columns:1fr 1fr" in report
    assert 'class="panel count-5"' in report
    assert 'class="panel count-3"' in report
    assert ".panel.count-5 .stock-card" in report
    assert "height:520px" in report
    assert "股市艾斯DC台股頻道" in report
    assert "本報告修改自" in report
    assert "https://github.com/kevin801221/stock-strategies-only" in report
    assert "V3 DAILY SIGNAL" not in report
    assert "深度分析" in report
    assert "量價解讀" in report
    assert "籌碼解讀" in report
    assert "外資投信同步買超｜回測 64%（18次）" in report
    assert "帶量上攻" in report
    assert "梯量柱｜量能階梯推升，走勢健康" in report
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
