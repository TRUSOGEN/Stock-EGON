"""美股持仓邮件图表。

本模块负责把单票历史 OHLC 数据绘制成适合邮件正文内嵌的 PNG 图片。当前输出是一张
价格折线、浅色面积和成交量柱组成的报价图，重点服务邮件快速阅读。
"""

from __future__ import annotations

from io import BytesIO

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

from .market_data import MarketDataProvider
from .notifications import EmailAttachment


PRICE_VOLUME_PERIOD = "3mo"


def build_symbol_chart_images(
    symbols: list[str],
    *,
    market_provider: MarketDataProvider,
) -> list[EmailAttachment]:
    """为每个 ticker 生成一张价格和成交量报价图。"""
    images: list[EmailAttachment] = []
    for symbol in symbols:
        frame = market_provider.fetch_history(symbol, period=PRICE_VOLUME_PERIOD)
        payload = render_symbol_price_volume_png(symbol, frame)
        images.append(
            EmailAttachment(
                filename=f"{symbol}-price-volume.png",
                content_type="image/png",
                data=payload,
            )
        )
    return images


def render_symbol_price_volume_png(symbol: str, frame: pd.DataFrame) -> bytes:
    """把单票历史行情渲染成报价图 PNG。"""
    frame = _normalize_frame(frame)
    canvas = Image.new("RGB", (1280, 900), "#fbfcff")
    draw = ImageDraw.Draw(canvas)
    title_font = _load_font(size=42)
    tab_font = _load_font(size=34)
    body_font = _load_font(size=28)
    small_font = _load_font(size=24)

    draw.rectangle((0, 0, 1280, 900), fill="#fbfcff")
    _draw_header(draw, title_font, tab_font, symbol)
    if frame.empty:
        draw.text((80, 390), "No price history available", fill="#7b8794", font=body_font)
    else:
        _draw_price_volume_chart(draw, body_font, small_font, frame)

    buffer = BytesIO()
    canvas.save(buffer, format="PNG")
    return buffer.getvalue()


def _normalize_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
    """标准化图表输入列。"""
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    required = ["date", "open", "high", "low", "close", "volume"]
    return frame[required].dropna().reset_index(drop=True)


def _draw_header(
    draw: ImageDraw.ImageDraw,
    title_font: ImageFont.ImageFont,
    tab_font: ImageFont.ImageFont,
    symbol: str,
) -> None:
    """绘制类似行情页的顶部标签。"""
    draw.text((52, 30), symbol, fill="#111827", font=title_font)
    draw.text((52, 96), "Quote", fill="#111827", font=tab_font)
    draw.text((190, 96), "Options", fill="#6b7280", font=tab_font)
    draw.text((390, 96), "News", fill="#6b7280", font=tab_font)
    draw.rounded_rectangle((42, 142, 154, 150), radius=4, fill="#1e66b2")


def _draw_price_volume_chart(
    draw: ImageDraw.ImageDraw,
    body_font: ImageFont.ImageFont,
    small_font: ImageFont.ImageFont,
    frame: pd.DataFrame,
) -> None:
    """绘制价格折线、浅色面积和成交量柱。"""
    price_left, price_top, price_right, price_bottom = 56, 180, 1148, 665
    volume_top, volume_bottom = 690, 840
    low_price = float(frame["low"].min())
    high_price = float(frame["high"].max())
    if high_price <= low_price:
        high_price = low_price + 1.0
    span = high_price - low_price

    for index in range(6):
        ratio = index / 5
        y = price_top + int((price_bottom - price_top) * ratio)
        price = high_price - span * ratio
        draw.line((price_left, y, price_right, y), fill="#e5e9f0", width=1)
        draw.text((price_right + 14, y - 14), f"{price:.2f}", fill="#6b7280", font=small_font)

    points = []
    closes = list(frame["close"].astype(float))
    for index, close in enumerate(closes):
        x = _index_to_x(index, len(frame), price_left, price_right)
        y = _price_to_y(close, price_top, price_bottom, low_price, span)
        points.append((x, y))
    if len(points) >= 2:
        area = [(points[0][0], price_bottom), *points, (points[-1][0], price_bottom)]
        draw.polygon(area, fill="#e7f0fb")
        draw.line(points, fill="#1f67b2", width=4, joint="curve")

    volume_max = max(float(value) for value in frame["volume"]) or 1.0
    bar_width = max(4, int((price_right - price_left) / max(len(frame) * 1.8, 1)))
    for index, row in frame.iterrows():
        x = _index_to_x(index, len(frame), price_left, price_right)
        height = int((float(row["volume"]) / volume_max) * (volume_bottom - volume_top))
        draw.rectangle((x - bar_width // 2, volume_bottom - height, x + bar_width // 2, volume_bottom), fill="#aeb5bf")

    draw.line((price_left, volume_bottom, price_right, volume_bottom), fill="#d5dae1", width=1)
    for position in _date_label_positions(len(frame)):
        x = _index_to_x(position, len(frame), price_left, price_right)
        label = _format_date(frame["date"].iloc[position])
        draw.text((x - 28, volume_bottom + 18), label, fill="#6b7280", font=small_font)

    last_close = float(frame["close"].iloc[-1])
    last_volume = float(frame["volume"].iloc[-1])
    marker_x, marker_y = points[-1]
    draw.ellipse((marker_x - 8, marker_y - 8, marker_x + 8, marker_y + 8), fill="#1f67b2")
    tooltip_left, tooltip_top = 770, 235
    draw.rectangle((tooltip_left, tooltip_top, tooltip_left + 330, tooltip_top + 104), fill="#f8fafc", outline="#4b5563", width=1)
    draw.text((tooltip_left + 24, tooltip_top + 20), f"Price   {last_close:.2f}", fill="#1f2937", font=body_font)
    draw.text((tooltip_left + 24, tooltip_top + 60), f"Volume  {_format_volume(last_volume)}", fill="#1f2937", font=body_font)


def _price_to_y(price: float, top: int, bottom: int, low_price: float, span: float) -> int:
    """把价格投影到像素 y 坐标。"""
    ratio = (price - low_price) / span
    return bottom - int((bottom - top) * ratio)


def _index_to_x(index: int, count: int, left: int, right: int) -> int:
    """把序号投影到像素 x 坐标。"""
    if count <= 1:
        return left
    return left + int((right - left) * index / (count - 1))


def _date_label_positions(count: int) -> list[int]:
    """返回横轴日期标签位置。"""
    if count <= 1:
        return [0]
    step = max(1, count // 6)
    positions = list(range(0, count, step))
    if positions[-1] != count - 1:
        positions.append(count - 1)
    return positions[:7]


def _format_date(value: object) -> str:
    """格式化横轴日期。"""
    timestamp = pd.to_datetime(value)
    return f"{timestamp.month}/{timestamp.day}"


def _format_volume(value: float) -> str:
    """格式化成交量。"""
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{value:.0f}"


def _load_font(*, size: int) -> ImageFont.ImageFont:
    """加载跨平台字体，缺失时回退到默认字体。"""
    for candidate in (
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()
