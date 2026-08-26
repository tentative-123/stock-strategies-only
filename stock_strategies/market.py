"""大盤狀態濾鏡

抓加權指數 (TAIEX) 的日 K 線，判斷目前是否站上 20 日均線。
若跌破月線，main.py 會把所有 BUY 訊號降級為 WATCH，避免在空頭市場
被連續洗損。
"""

from .datasources import get_index_history


def _chart_history(df) -> list[dict]:
    """整理報告圖所需的近 80 日 K 線、成交量與均線資料。"""
    chart = df.copy()
    for period in (5, 10, 20, 60):
        chart[f"ma{period}"] = chart["close"].rolling(period).mean()
    if "volume" not in chart.columns:
        chart["volume"] = 0
    columns = [
        "date", "open", "high", "low", "close", "volume",
        "ma5", "ma10", "ma20", "ma60",
    ]
    records = chart[columns].tail(80).copy()
    records["date"] = records["date"].astype(str).str[:10]
    records = records.astype(object).where(records.notna(), None)
    return records.to_dict("records")


def get_market_state(ma_period: int = 20) -> dict:
    """回傳大盤狀態 dict（可指定均線天數，預設 20=月線）"""
    try:
        df = get_index_history("TAIEX")
        if len(df) < ma_period + 1:
            return {"bullish": True, "close": None, "ma20": None, "history": [],
                    "note": "⚠️ 大盤資料不足，暫不套用濾鏡"}
        df = df.copy()
        df["ma20"] = df["close"].rolling(ma_period).mean()
        latest = df.iloc[-1]
        close = float(latest["close"]); ma20 = float(latest["ma20"])
        bullish = close > ma20
        pct = (close / ma20 - 1) * 100
        if bullish:
            note = f"🟢 加權 {close:.0f} 站上 {ma_period} 日線 ({pct:+.1f}%)，BUY 訊號照常發出"
        else:
            note = f"🔴 加權 {close:.0f} 跌破 {ma_period} 日線 ({pct:+.1f}%)，BUY 全數降為 WATCH"
        return {
            "bullish": bullish,
            "close": close,
            "ma20": ma20,
            "history": _chart_history(df),
            "note": note,
        }
    except Exception as e:
        return {"bullish": True, "close": None, "ma20": None, "history": [],
                "note": f"⚠️ 大盤狀態取得失敗（{str(e)[:60]}），暫不套用濾鏡"}


def apply_market_filter(results: list[dict], market: dict) -> int:
    """若空頭，把 BUY 降為 WATCH。回傳被降級的數量。"""
    if market.get("bullish", True):
        return 0
    downgraded = 0
    for r in results:
        if r.get("action") == "BUY":
            r["action"] = "WATCH"
            r.setdefault("risk_notes", []).append("大盤跌破月線，自動降為 WATCH")
            downgraded += 1
    return downgraded
