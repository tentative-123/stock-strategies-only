"""Generate the one-page daily report as HTML and render it with headless Chrome."""

from __future__ import annotations

import html
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

REPORT_WIDTH = 1080
REPORT_HEIGHT = 1800


def _escape(value: object) -> str:
    return html.escape(str(value or ""))


def _market_tone(signals: list[dict]) -> tuple[str, str]:
    valid = [s for s in signals if s.get("trend")]
    if not valid:
        return "neutral", "市場資料不足，今日以個股訊號為主"
    up = sum(1 for s in valid if s["trend"].get("chg_5d", 0) > 0)
    above = sum(1 for s in valid if s["trend"].get("above_ma20"))
    if up / len(valid) > 0.7 and above / len(valid) > 0.6:
        return "positive", "盤勢偏多，可留意強勢股延續"
    if up / len(valid) > 0.5:
        return "watch", "盤勢中性偏多，選股不追高"
    if up / len(valid) > 0.3:
        return "watch", "盤勢中性偏空，控制整體部位"
    return "negative", "盤勢偏空，耐心等待止跌訊號"


def _stock_card(stock: dict, kind: str) -> str:
    components = stock.get("components", {})
    trend = stock.get("trend", {})
    winrate = components.get("backtest_winrate")
    winrate_text = f"{winrate * 100:.0f}%" if winrate is not None else "N/A"
    signals = "、".join(components.get("tech_signals", [])) or "尚無明確技術觸發"
    deep_parts = []
    if components.get("tech_signals"):
        deep_parts.append("技術面出現" + "、".join(components["tech_signals"]))
    if trend.get("chg_5d", 0) > 0 and trend.get("vol_ratio", 1) > 1.2:
        deep_parts.append("帶量上攻")
    if trend.get("above_ma20") and trend.get("above_ma60"):
        deep_parts.append("站上月季線")
    if winrate is not None and winrate >= 0.6:
        deep_parts.append(f"回測勝率 {winrate_text}")
    deep_analysis = "，".join(deep_parts) or "綜合分數領先，等待量價確認"
    patterns = components.get("volume_patterns", [])
    pattern_text = "＋".join(patterns) if patterns else "無特殊型態"
    volume_verdict = components.get("volume_verdict") or "量能平淡，等待表態"
    notes = [
        note
        for note in stock.get("risk_notes", [])
        if not (note.startswith("歷史勝率") and "低於五成" in note)
    ]
    note_html = (
        f'<div class="stock-note">⚠ {_escape(" · ".join(notes[:2]))}</div>'
        if notes
        else ""
    )
    return f"""
      <article class="stock-card {kind}">
        <div class="stock-head">
          <div><b>{_escape(stock.get('stock_id'))}</b><span>{_escape(stock.get('name'))}</span></div>
          <strong>{_escape(stock.get('signal_score'))}<small>分</small></strong>
        </div>
        <div class="metrics">
          <span>5日 <b>{trend.get('chg_5d', 0):+.1f}%</b></span>
          <span>20日 <b>{trend.get('chg_20d', 0):+.1f}%</b></span>
          <span>技術 <b>{_escape(components.get('tech_score', 'N/A'))}</b></span>
          <span>勝率 <b>{winrate_text}</b></span>
          <span>風報比 <b>1:{_escape(stock.get('risk_reward_ratio', 'N/A'))}</b></span>
        </div>
        <div class="trigger">觸發：{_escape(signals)}</div>
        <div class="analysis"><b>深度分析</b><span>{_escape(deep_analysis)}</span></div>
        <div class="analysis volume-reading"><b>量價解讀</b><span>{_escape(pattern_text)}｜{_escape(volume_verdict)}</span></div>
        {note_html}
      </article>"""


def _index_chart(history: list[dict]) -> str:
    """將近 60 日加權指數資料畫成無 JavaScript 的 SVG K 線圖。"""
    rows = [
        row
        for row in history[-60:]
        if all(row.get(key) is not None for key in ("open", "high", "low", "close"))
    ]
    if len(rows) < 2:
        return '<div class="chart-empty">加權指數 K 線資料不足</div>'

    width, height = 918, 460
    left, right, top = 58, 18, 12
    price_bottom, volume_top, volume_bottom = 315, 355, 430
    plot_width = width - left - right
    values = [float(row[key]) for row in rows for key in ("high", "low")]
    for row in rows:
        values.extend(
            float(row[key])
            for key in ("ma5", "ma10", "ma20", "ma60")
            if row.get(key) is not None
        )
    price_min, price_max = min(values), max(values)
    padding = max((price_max - price_min) * 0.06, 1)
    price_min -= padding
    price_max += padding
    max_volume = max(float(row.get("volume") or 0) for row in rows) or 1
    step = plot_width / len(rows)

    def x_at(index: int) -> float:
        return left + step * (index + 0.5)

    def y_at(value: float) -> float:
        ratio = (float(value) - price_min) / (price_max - price_min)
        return price_bottom - ratio * (price_bottom - top)

    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="加權指數日 K 線圖">']
    for index in range(4):
        y = top + (price_bottom - top) * index / 3
        price = price_max - (price_max - price_min) * index / 3
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" class="grid"/>'
            f'<text x="{left-8}" y="{y+4:.1f}" text-anchor="end" class="axis">{price:,.0f}</text>'
        )
    parts.append(
        f'<line x1="{left}" y1="{volume_bottom}" x2="{width-right}" y2="{volume_bottom}" class="grid"/>'
    )

    candle_width = max(3.0, min(8.0, step * 0.58))
    for index, row in enumerate(rows):
        x = x_at(index)
        open_price, close = float(row["open"]), float(row["close"])
        high, low = float(row["high"]), float(row["low"])
        css_class = "rise" if close >= open_price else "fall"
        body_top = min(y_at(open_price), y_at(close))
        body_height = max(abs(y_at(open_price) - y_at(close)), 1.5)
        volume_height = float(row.get("volume") or 0) / max_volume * (volume_bottom - volume_top)
        parts.append(
            f'<line x1="{x:.1f}" y1="{y_at(high):.1f}" x2="{x:.1f}" y2="{y_at(low):.1f}" class="wick {css_class}"/>'
            f'<rect x="{x-candle_width/2:.1f}" y="{body_top:.1f}" width="{candle_width:.1f}" height="{body_height:.1f}" class="candle {css_class}"/>'
            f'<rect x="{x-candle_width/2:.1f}" y="{volume_bottom-volume_height:.1f}" width="{candle_width:.1f}" height="{volume_height:.1f}" class="volume {css_class}"/>'
        )

    ma_colors = {5: "#8b5cf6", 10: "#2f6fed", 20: "#e49b0f", 60: "#64748b"}
    for period, color in ma_colors.items():
        points = [
            f"{x_at(index):.1f},{y_at(row[f'ma{period}']):.1f}"
            for index, row in enumerate(rows)
            if row.get(f"ma{period}") is not None
        ]
        if len(points) > 1:
            parts.append(
                f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>'
            )

    tick_indexes = sorted({0, len(rows) // 3, len(rows) * 2 // 3, len(rows) - 1})
    for index in tick_indexes:
        date = str(rows[index].get("date", ""))[5:].replace("-", "/")
        parts.append(
            f'<text x="{x_at(index):.1f}" y="{height-5}" text-anchor="middle" class="axis">{_escape(date)}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def build_report_html(
    signals: list[dict],
    watchlist: list[dict] | None = None,
    market: dict | None = None,
    night_note: str | None = None,
    report_date: datetime | None = None,
) -> str:
    """Build a fixed-size, one-page HTML report without changing signal decisions."""
    report_date = report_date or datetime.now()
    watchlist = watchlist or []
    buys = [s for s in signals if s.get("action") == "BUY"][:5]
    watches = [s for s in signals if s.get("action") == "WATCH"][:3]
    skips = [s for s in signals if s.get("action") in ("SKIP", "ERROR")]
    tone, guidance = _market_tone(signals)
    conclusion = (
        f"今日聚焦 {len(buys)} 檔強勢候選"
        if buys
        else "今日無強勢候選，耐心觀察"
    )
    buy_cards = "".join(_stock_card(s, "buy") for s in buys)
    watch_cards = "".join(_stock_card(s, "watch") for s in watches)
    if not buy_cards:
        buy_cards = '<div class="empty-line">無符合全部條件的標的</div>'
    if not watch_cards:
        watch_cards = '<div class="empty-line">今日無額外關注標的</div>'

    return f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><style>
*{{box-sizing:border-box}}html,body{{margin:0;width:{REPORT_WIDTH}px;height:{REPORT_HEIGHT}px}}
body{{font-family:"Noto Sans TC","Microsoft JhengHei",Arial,sans-serif;background:#eef2f7;color:#182234}}
.page{{width:100%;height:100%;padding:54px 58px;background:#f7f9fc;overflow:hidden}}
.header{{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:28px}}
.eyebrow{{color:#59708f;font-weight:800;font-size:18px;letter-spacing:3px;margin-bottom:8px}}
h1{{font-size:42px;line-height:1.1;margin:0;color:#10213a}}.date{{font-size:22px;font-weight:700;color:#64748b}}
.hero{{display:flex;justify-content:space-between;align-items:center;padding:24px 28px;border-radius:22px;background:#fff;border-left:9px solid #335cff;box-shadow:0 10px 30px #263b5b12;margin-bottom:20px}}
.hero h2{{font-size:30px;margin:0 0 7px}}.hero p{{margin:0;font-size:18px;color:#5d6b80}}.counts{{display:flex;gap:9px}}
.pill{{padding:10px 14px;border-radius:13px;font-size:17px;font-weight:800}}.pill.buy{{background:#dcfce7;color:#087443}}.pill.watch{{background:#fff4cc;color:#8a5a00}}.pill.skip{{background:#eef1f5;color:#64748b}}
.overview{{display:grid;grid-template-columns:1fr 1fr 0.9fr;gap:14px;margin-bottom:22px}}.info{{background:#fff;padding:18px 20px;border-radius:17px;border:1px solid #e4eaf2;min-height:112px}}
.info label,.section-title span{{display:block;font-size:15px;font-weight:800;color:#718096;letter-spacing:1px;margin-bottom:8px}}.info b{{font-size:19px;line-height:1.45}}.info.{tone} b{{color:{'#087443' if tone == 'positive' else '#b45309' if tone == 'watch' else '#c0392b' if tone == 'negative' else '#334155'}}}
.content{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}.panel{{height:650px;background:#fff;border:1px solid #e4eaf2;border-radius:20px;padding:20px;box-shadow:0 8px 24px #263b5b0b}}
.section-title{{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}}.section-title h3{{font-size:23px;margin:0}}.section-title span{{margin:0}}
.stock-card{{border:1px solid #e5eaf1;border-radius:14px;padding:12px 14px;margin-top:9px;background:#fbfcfe}}.stock-card.buy{{border-left:6px solid #17a667}}.stock-card.watch{{border-left:6px solid #e7a91b}}
.stock-head{{display:flex;justify-content:space-between;align-items:center}}.stock-head div b{{font-size:21px;margin-right:9px}}.stock-head div span{{font-size:18px;font-weight:700;color:#435169}}.stock-head>strong{{font-size:24px;color:#335cff}}.stock-head small{{font-size:13px;margin-left:2px}}
.metrics{{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0 6px}}.metrics span{{background:#eef3f8;border-radius:8px;padding:4px 6px;font-size:12px;color:#5d6b80}}.metrics b{{color:#25364f}}.trigger{{font-size:13px;color:#3c4e67;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.analysis{{display:grid;grid-template-columns:58px 1fr;gap:6px;margin-top:6px;padding-top:6px;border-top:1px dashed #e1e7ef;font-size:12px;line-height:1.35;color:#53637a}}.analysis b{{color:#25364f}}.analysis span{{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}.volume-reading b{{color:#9a6700}}.stock-note{{font-size:12px;color:#b45309;margin-top:5px}}
.panel.dense .stock-card{{padding:8px 11px;margin-top:6px}}.panel.dense .stock-head div b{{font-size:18px}}.panel.dense .stock-head div span{{font-size:15px}}.panel.dense .stock-head>strong{{font-size:20px}}.panel.dense .metrics{{flex-wrap:nowrap;gap:3px;margin:5px 0}}.panel.dense .metrics span{{font-size:10px;padding:3px}}.panel.dense .trigger{{font-size:11px}}.panel.dense .analysis{{grid-template-columns:50px 1fr;margin-top:4px;padding-top:4px;font-size:10px}}.panel.dense .analysis span{{-webkit-line-clamp:1}}
.empty-line{{padding:18px;border-radius:13px;background:#f6f8fb;color:#7a8798;font-size:16px;text-align:center}}
.footer{{display:flex;justify-content:space-between;align-items:center;margin-top:18px;padding:0 4px;color:#778397;font-size:13px}}.brand{{font-weight:900;letter-spacing:1px;color:#335cff}}
.chart-panel{{background:#fff;border:1px solid #e4eaf2;border-radius:20px;padding:18px 22px 12px;margin-bottom:22px;box-shadow:0 8px 24px #263b5b0b}}.chart-head{{display:flex;align-items:center;justify-content:space-between;margin-bottom:6px}}.chart-head h3{{font-size:23px;margin:0}}.legend{{display:flex;gap:14px;color:#65748a;font-size:13px;font-weight:700}}.legend i{{width:16px;height:3px;border-radius:2px;display:inline-block;margin-right:5px;vertical-align:middle}}.chart-panel svg{{display:block;width:100%;height:460px}}.grid{{stroke:#e8edf4;stroke-width:1}}.axis{{font-size:11px;fill:#8190a5}}.wick{{stroke-width:1.4}}.candle.rise,.volume.rise{{fill:#e45151}}.wick.rise{{stroke:#e45151}}.candle.fall,.volume.fall{{fill:#15966a}}.wick.fall{{stroke:#15966a}}.volume{{opacity:.42}}.chart-empty{{height:310px;display:flex;align-items:center;justify-content:center;color:#8290a3;background:#f7f9fc;border-radius:14px}}
</style></head><body><main class="page">
  <header class="header"><div><div class="eyebrow">TAIWAN STOCK SIGNAL</div><h1>0050追蹤選股日報</h1></div><div class="date">{report_date:%Y / %m / %d}</div></header>
  <section class="hero"><div><h2>{conclusion}</h2><p>{_escape(guidance)}</p></div><div class="counts"><span class="pill buy">BUY {len([s for s in signals if s.get('action') == 'BUY'])}</span><span class="pill watch">WATCH {len([s for s in signals if s.get('action') == 'WATCH'])}</span><span class="pill skip">SKIP {len(skips)}</span></div></section>
  <section class="overview"><div class="info {tone}"><label>大盤判讀</label><b>{_escape((market or {}).get('note') or guidance)}</b></div><div class="info"><label>夜盤訊號</label><b>{_escape(night_note or '暫無夜盤資料')}</b></div><div class="info"><label>掃描範圍</label><b>{len(signals)} 檔股票<br>{len(watchlist)} 檔觀察池</b></div></section>
  <section class="chart-panel"><div class="chart-head"><h3>加權指數｜日 K 趨勢</h3><div class="legend"><span><i style="background:#8b5cf6"></i>MA5</span><span><i style="background:#2f6fed"></i>MA10</span><span><i style="background:#e49b0f"></i>MA20</span><span><i style="background:#64748b"></i>MA60</span><span>成交量</span></div></div>{_index_chart((market or {}).get('history', []))}</section>
  <section class="content"><div><div class="panel{' dense' if len(buys) > 3 else ''}"><div class="section-title"><h3>🟢 今日預計強勢股</h3><span>TOP 5</span></div>{buy_cards}</div></div>
  <div><div class="panel"><div class="section-title"><h3>🟡 今日可關注股</h3><span>TOP 3</span></div>{watch_cards}</div></div></section>
  <footer class="footer"><span>系統自動分析，僅供參考，投資決策請自行判斷</span><span class="brand">V3 DAILY SIGNAL</span></footer>
</main></body></html>"""


def render_report_png(html_text: str, output_path: str | Path) -> Path:
    """Render report HTML to PNG with Chrome available on the host runner."""
    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    html_path = output.with_suffix(".html")
    html_path.write_text(html_text, encoding="utf-8")
    chrome = os.environ.get("CHROME_BIN") or next(
        (
            found
            for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")
            if (found := shutil.which(name))
        ),
        None,
    )
    if not chrome:
        raise RuntimeError("找不到 Chrome，無法產生每日報告圖")
    try:
        subprocess.run(
            [
                chrome,
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                "--hide-scrollbars",
                f"--window-size={REPORT_WIDTH},{REPORT_HEIGHT}",
                f"--screenshot={output}",
                html_path.as_uri(),
            ],
            check=True,
            capture_output=True,
            timeout=45,
        )
    finally:
        html_path.unlink(missing_ok=True)
    if not output.exists():
        raise RuntimeError("Chrome 未產生報告圖")
    return output
