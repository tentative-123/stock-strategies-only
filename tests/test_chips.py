import numpy as np
import pandas as pd

from stock_strategies.chips import build_chip_scores, chip_signals, backtest_chips


def _prices(n=100):
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    close = np.linspace(100, 140, n)
    return pd.DataFrame({"date": dates, "open": close, "high": close * 1.02,
                         "low": close * .99, "close": close, "volume": 1_000_000})


def test_chip_score_uses_volume_ratio_and_one_merged_history():
    px = _prices()
    inst = pd.DataFrame({"date": px.date, "foreign_net": 40_000,
                         "trust_net": 15_000, "dealer_net": 0, "total_net": 55_000})
    scores = build_chip_scores(px, inst)
    assert scores.iloc[-1].chip_score > 50
    assert "外資投信同步買超" in chip_signals(scores.iloc[-1])
    scaled = inst.copy()
    scaled[["foreign_net", "trust_net", "total_net"]] *= 10
    px_scaled = px.copy(); px_scaled["volume"] *= 10
    assert build_chip_scores(px_scaled, scaled).iloc[-1].chip_score == scores.iloc[-1].chip_score


def test_chip_backtest_reuses_precomputed_scores():
    px = _prices(120)
    inst = pd.DataFrame({"date": px.date, "foreign_net": 50_000,
                         "trust_net": 20_000, "dealer_net": 0, "total_net": 70_000})
    result = backtest_chips(px, build_chip_scores(px, inst), {
        "hold_days": 5, "min_chip_score_for_signal": 60,
        "target_return": .1, "stop_loss": .08,
    })
    assert result["samples"] > 0
    assert 0 <= result["winrate"] <= 1
