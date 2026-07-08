"""美股持仓邮件图表。

本模块负责把单票历史 OHLC 数据绘制成适合邮件附件的 PNG 图片。当前输出是一张
三联图，分别展示 1 周、1 月、1 年三个时间窗，避免邮件里出现大量零散附件，也让
读者能一眼看到短中长期结构。
"""

from __future__ import annotations

from io import BytesIO
from typing import Mapping

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

from .market_data import MarketDataProvider
from .notifications import EmailAttachment


CHART_PERIODS = (
    ("1W", "5d"),
    ("1M", "1mo"),
    ("1Y", "1y"),
)


def build_symbol_chart_attachments(
    symbols: list[str],
    *,
    market_provider: MarketDataProvider,
) -> list[EmailAttachment]:
    """为每个 ticker 生成一张三联 K 线图附件。"""
    attachments: list[EmailAttachment] = []
    for symbol in symbols:
        frames = {
            label: market_provider.fetch_history(symbol, period=period)
            for label, period in CHART_PERIODS
        }
        payload = render_symbol_triptych_png(symbol, frames)
        attachments.append(
            EmailAttachment(
                filename=f"{symbol}-kline.png",
                content_type="image/png",
                data=payload,
            )
        )
    return attachments


def render_symbol_triptych_png(symbol: str, frames: Mapping[str, pd.DataFrame]) -> bytes:
    """把单票多个时间窗历史行情渲染成 PNG。"""
    canvas = Image.new("RGB", (1500, 620), "#f8faf8")
    draw = ImageDraw.Draw(canvas)
    title_font = ImageFont.load_default()
    body_font = ImageFont.load_default()

    draw.rounded_rectangle((24, 20, 1476, 596), radius=18, fill="#ffffff", outline="#d6e2db", width=2)
    draw.text((48, 40), f"{symbol} K 线概览", fill="#163227", font=title_font)

    for index, label in enumerate(("1W", "1M", "1Y")):
        left = 48 + index * 472
        top = 92
        right = left + 420
        bottom = 548
        draw.rounded_rectangle((left, top, right, bottom), radius=14, fill="#fbfcfb", outline="#d9e2dc", width=1)
        draw.text((left + 18, top + 14), label, fill="#35594c", font=title_font)
        frame = _normalize_frame(frames.get(label))
        _draw_panel(draw, body_font, frame, (left + 18, top + 46, right - 18, bottom - 24))

    buffer = BytesIO()
    canvas.save(buffer, format="PNG")
    return buffer.getvalue()


def _normalize_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
    """标准化图表输入列。"""
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    required = ["date", "open", "high", "low", "close", "volume"]
    return frame[required].dropna().reset_index(drop=True)


def _draw_panel(
    draw: ImageDraw.ImageDraw,
    font: ImageFont.ImageFont,
    frame: pd.DataFrame,
    bounds: tuple[int, int, int, int],
) -> None:
    """在单个面板中绘制 K 线、价格标签和小结。"""
    left, top, right, bottom = bounds
    if frame.empty:
        draw.text((left, top + 120), "暂无可用历史行情", fill="#7c8d84", font=font)
        return

    chart_bottom = bottom - 56
    low_price = float(frame["low"].min())
    high_price = float(frame["high"].max())
    if high_price <= low_price:
        high_price = low_price + 1.0
    span = high_price - low_price
    candle_count = len(frame)
    candle_width = max(4, min(14, int((right - left - 24) / max(candle_count * 1.8, 1))))
    gap = max(3, int(candle_width * 0.7))

    draw.line((left, chart_bottom, right, chart_bottom), fill="#c7d4cd", width=1)
    draw.line((left, top, left, chart_bottom), fill="#c7d4cd", width=1)
    _draw_price_grid(draw, font, left, top, right, chart_bottom, low_price, high_price)

    x = left + 18
    for _, row in frame.iterrows():
        open_price = float(row["open"])
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        color = "#14804a" if close >= open_price else "#b9382f"
        center_x = x + candle_width // 2
        high_y = _price_to_y(high, top, chart_bottom, low_price, span)
        low_y = _price_to_y(low, top, chart_bottom, low_price, span)
        open_y = _price_to_y(open_price, top, chart_bottom, low_price, span)
        close_y = _price_to_y(close, top, chart_bottom, low_price, span)
        draw.line((center_x, high_y, center_x, low_y), fill=color, width=1)
        rect_top = min(open_y, close_y)
        rect_bottom = max(open_y, close_y)
        if rect_top == rect_bottom:
            rect_bottom += 1
        draw.rectangle((x, rect_top, x + candle_width, rect_bottom), fill=color, outline=color)
        x += candle_width + gap

    first_close = float(frame["close"].iloc[0])
    last_close = float(frame["close"].iloc[-1])
    change_pct = (last_close / first_close - 1) * 100 if first_close else 0.0
    draw.text((left, bottom - 40), f"收盘 {last_close:.2f}", fill="#163227", font=font)
    draw.text((left + 120, bottom - 40), f"区间 {change_pct:+.2f}%", fill="#35594c", font=font)


def _draw_price_grid(
    draw: ImageDraw.ImageDraw,
    font: ImageFont.ImageFont,
    left: int,
    top: int,
    right: int,
    bottom: int,
    low_price: float,
    high_price: float,
) -> None:
    """绘制淡色价格网格，帮助肉眼估读。"""
    for index in range(4):
        ratio = index / 3
        price = high_price - (high_price - low_price) * ratio
        y = top + int((bottom - top) * ratio)
        draw.line((left, y, right, y), fill="#eef3f0", width=1)
        draw.text((right - 70, y - 8), f"{price:.2f}", fill="#7c8d84", font=font)


def _price_to_y(price: float, top: int, bottom: int, low_price: float, span: float) -> int:
    """把价格投影到像素 y 坐标。"""
    ratio = (price - low_price) / span
    return bottom - int((bottom - top) * ratio)
