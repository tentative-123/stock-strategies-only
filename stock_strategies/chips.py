"""外資／投信籌碼評分與 point-in-time 回測。"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _ratio_score(series: pd.Series, cap: float) -> pd.Series:
    """將買賣超占成交量比映射為 0..100；0 為中性 50。"""
    return (50 + series.fillna(0).clip(-cap, cap) / cap * 50).clip(0, 100)


def build_chip_scores(prices: pd.DataFrame, institutional: pd.DataFrame) -> pd.DataFrame:
    """一次使用整批法人資料，逐日產生不偷看未來的籌碼分數。

    買賣超（股）除以同期成交量（股），避免高股本股票天然占優。
    外資占 55 分、投信占 40 分、兩者同向加 5 分。
    """
    base = prices[["date", "volume"]].copy()
    base["date"] = pd.to_datetime(base["date"])
    if institutional is None or institutional.empty:
        base["foreign_net"] = base["trust_net"] = 0.0
    else:
        inst = institutional[["date", "foreign_net", "trust_net"]].copy()
        inst["date"] = pd.to_datetime(inst["date"])
        base = base.merge(inst, on="date", how="left")
    for col in ("volume", "foreign_net", "trust_net"):
        base[col] = pd.to_numeric(base[col], errors="coerce").fillna(0)

    volume5 = base["volume"].rolling(5, min_periods=1).sum().replace(0, np.nan)
    volume20 = base["volume"].rolling(20, min_periods=1).sum().replace(0, np.nan)
    for owner in ("foreign", "trust"):
        net = base[f"{owner}_net"]
        base[f"{owner}_ratio_5d"] = net.rolling(5, min_periods=1).sum() / volume5
        base[f"{owner}_ratio_20d"] = net.rolling(20, min_periods=1).sum() / volume20
        positive = net.gt(0).astype(int)
        negative = net.lt(0).astype(int)
        base[f"{owner}_streak_5d"] = (
            positive.rolling(5, min_periods=1).sum()
            - negative.rolling(5, min_periods=1).sum()
        )

    foreign = (
        _ratio_score(base["foreign_ratio_5d"], .08) * .25
        + _ratio_score(base["foreign_ratio_20d"], .08) * .20
        + ((base["foreign_streak_5d"] + 5) * 10).clip(0, 100) * .10
    )
    trust = (
        _ratio_score(base["trust_ratio_5d"], .03) * .20
        + _ratio_score(base["trust_ratio_20d"], .03) * .12
        + ((base["trust_streak_5d"] + 5) * 10).clip(0, 100) * .08
    )
    agreement = pd.Series(2.5, index=base.index)
    agreement[(base["foreign_ratio_5d"] > 0) & (base["trust_ratio_5d"] > 0)] = 5
    agreement[(base["foreign_ratio_5d"] < 0) & (base["trust_ratio_5d"] < 0)] = 0
    base["chip_score"] = (foreign + trust + agreement).round(1).clip(0, 100)
    return base


def chip_signals(row: pd.Series | dict) -> list[str]:
    signals: list[str] = []
    f5, t5 = float(row.get("foreign_ratio_5d", 0) or 0), float(row.get("trust_ratio_5d", 0) or 0)
    fs, ts = int(row.get("foreign_streak_5d", 0) or 0), int(row.get("trust_streak_5d", 0) or 0)
    if f5 > 0:
        signals.append(f"外資5日買超占量 {f5:+.1%}")
    if t5 > 0:
        signals.append(f"投信5日買超占量 {t5:+.1%}")
    if fs >= 3:
        signals.append(f"外資近5日淨買 {fs}日")
    if ts >= 3:
        signals.append(f"投信近5日淨買 {ts}日")
    if f5 > 0 and t5 > 0:
        signals.append("外資投信同步買超")
    return signals or ["法人籌碼中性"]


def adjusted_winrate(winrate: float | None, samples: int, prior_samples: int = 8) -> float:
    """小樣本向 50% 收縮，避免少數交易讓回測分數失真。"""
    if winrate is None or samples <= 0:
        return .5
    return (float(winrate) * samples + .5 * prior_samples) / (samples + prior_samples)


def backtest_chips(prices: pd.DataFrame, scores: pd.DataFrame, params: dict) -> dict:
    """籌碼分達門檻後，次日開盤進場；沿用技術回測的停利停損。"""
    hold = int(params.get("hold_days", 20))
    threshold = float(params.get("min_chip_score_for_signal", 60))
    target = float(params.get("target_return", .10))
    stop = float(params.get("stop_loss", .08))
    wins = losses = 0
    returns: list[float] = []
    for i in range(20, len(prices) - hold - 1):
        if float(scores.iloc[i]["chip_score"]) < threshold:
            continue
        entry = prices.iloc[i + 1].get("open")
        if pd.isna(entry) or entry <= 0:
            continue
        future = prices.iloc[i + 2:i + 2 + hold]
        if len(future) < hold:
            continue
        if future["low"].min() <= entry * (1 - stop):
            ret = -stop
        elif future["high"].max() >= entry * (1 + target):
            ret = target
        else:
            ret = (future.iloc[-1]["close"] - entry) / entry
        returns.append(float(ret))
        wins += ret > 0
        losses += ret <= 0
    total = wins + losses
    return {"winrate": round(wins / total, 3) if total else None,
            "samples": total, "avg_return": round(float(np.mean(returns)), 4) if returns else None}
