from unittest.mock import Mock

from stock_strategies.notify import (
    DISCORD_MESSAGE_LIMIT,
    format_messages,
    format_premarket,
    send_discord,
    send_discord_image,
)


def test_send_discord_posts_webhook_content(monkeypatch, mocker):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/webhook")
    post = mocker.patch("stock_strategies.notify.requests.post")
    post.return_value = Mock(ok=True)

    send_discord("每日選股報告")

    post.assert_called_once_with(
        "https://discord.test/webhook",
        json={"content": "每日選股報告"},
        timeout=10,
    )


def test_send_discord_splits_messages_at_discord_limit(monkeypatch, mocker):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/webhook")
    post = mocker.patch("stock_strategies.notify.requests.post")
    post.return_value = Mock(ok=True)
    text = "a" * DISCORD_MESSAGE_LIMIT + "\n" + "b" * 10

    send_discord(text)

    chunks = [call.kwargs["json"]["content"] for call in post.call_args_list]
    assert chunks == ["a" * DISCORD_MESSAGE_LIMIT, "b" * 10]
    assert all(len(chunk) <= DISCORD_MESSAGE_LIMIT for chunk in chunks)


def test_send_discord_image_uploads_png(tmp_path, monkeypatch, mocker):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/webhook")
    monkeypatch.delenv("DISCORD_REPORT_WEBHOOK_URL", raising=False)
    image_path = tmp_path / "report.png"
    image_path.write_bytes(b"png")
    post = mocker.patch("stock_strategies.notify.requests.post")
    post.return_value = Mock(ok=True)

    send_discord_image(str(image_path))

    call = post.call_args
    assert call.args[0] == "https://discord.test/webhook"
    assert call.kwargs["data"] == {"content": "🖼️ 0050追蹤選股日報"}
    assert call.kwargs["files"]["file"][0] == "daily-report.png"
    assert call.kwargs["files"]["file"][2] == "image/png"
    assert call.kwargs["timeout"] == 30


def test_send_discord_image_also_posts_to_report_channel(tmp_path, monkeypatch, mocker):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/main")
    monkeypatch.setenv(
        "DISCORD_REPORT_WEBHOOK_URL", "https://discord.test/report"
    )
    image_path = tmp_path / "report.png"
    image_path.write_bytes(b"png-content")
    uploads = []

    def capture_upload(url, **kwargs):
        uploads.append((url, kwargs["files"]["file"][1].read()))
        return Mock(ok=True)

    mocker.patch(
        "stock_strategies.notify.requests.post", side_effect=capture_upload
    )

    send_discord_image(str(image_path))

    assert uploads == [
        ("https://discord.test/main", b"png-content"),
        ("https://discord.test/report", b"png-content"),
    ]


def test_send_discord_image_does_not_duplicate_same_webhook(tmp_path, monkeypatch, mocker):
    webhook = "https://discord.test/same"
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", webhook)
    monkeypatch.setenv("DISCORD_REPORT_WEBHOOK_URL", webhook)
    image_path = tmp_path / "report.png"
    image_path.write_bytes(b"png")
    post = mocker.patch("stock_strategies.notify.requests.post")
    post.return_value = Mock(ok=True)

    send_discord_image(str(image_path))

    post.assert_called_once()


def _signal(stock_id: str, action: str) -> dict:
    return {
        "stock_id": stock_id,
        "name": f"股票{stock_id}",
        "action": action,
        "signal_score": 70,
        "entry_price": 100,
        "stop_loss_price": 92,
        "target_price": 110,
        "risk_reward_ratio": 1.25,
        "position_size_pct": 20,
        "risk_notes": ["歷史勝率 49% 低於五成", "其他風險"],
        "components": {
            "fundamental_pass": True,
            "tech_score": 60,
            "backtest_winrate": 0.49,
            "backtest_samples": 20,
            "tech_signals": ["MACD多頭"],
        },
        "trend": {
            "chg_5d": 1,
            "chg_20d": 2,
            "pct_from_high": -3,
            "above_ma20": True,
            "above_ma60": True,
            "vol_ratio": 1,
        },
    }


def test_report_uses_compact_labels_and_limits_stock_counts():
    buys = [_signal(f"B{i}", "BUY") for i in range(6)]
    watches = [_signal(f"W{i}", "WATCH") for i in range(4)]

    messages = format_messages(buys + watches)
    detail = messages[1]

    assert "今日預計強勢股 (5)" in detail
    assert "今日可關注股 (3)" in detail
    assert "B4" in detail and "B5" not in detail
    assert "W2" in detail and "W3" not in detail


def test_report_keeps_winrate_and_risk_reward_but_removes_trade_prices_and_notes():
    messages = format_messages([_signal("2330", "BUY")])
    report = "\n".join(messages)

    assert "勝率 49% (20次)" in report
    assert "風報比 1:1.25" in report
    assert "其他風險" in report
    assert "歷史勝率 49% 低於五成" not in report
    assert "為何買" not in report
    assert "明日開盤進場" not in report
    assert "參考價" not in report
    assert "停損 92" not in report
    assert "目標 110" not in report


def test_premarket_uses_new_labels_and_limits_stock_counts():
    buys = [_signal(f"B{i}", "BUY") | {"date": "2026-08-21"} for i in range(6)]
    watches = [
        _signal(f"W{i}", "WATCH") | {"date": "2026-08-21"} for i in range(4)
    ]

    report = format_premarket(None, buys + watches)

    assert "今日預計強勢股" in report
    assert "今日可關注股" in report
    assert "B4" in report and "B5" not in report
    assert "W2" in report and "W3" not in report
