from unittest.mock import Mock

from stock_strategies.notify import DISCORD_MESSAGE_LIMIT, send_discord


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
