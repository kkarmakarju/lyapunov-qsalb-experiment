from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


COLORS = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#000000", "#7A5195"]


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = ["arialbd.ttf" if bold else "arial.ttf", "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def line_chart_png(path: Path, rows: list[dict[str, str]], x_key: str, y_key: str,
                   group_key: str, title: str, x_label: str, y_label: str,
                   ci_key: str | None = None) -> None:
    width, height = 900, 560
    left, right, top, bottom = 95, 35, 60, 80
    plot_w, plot_h = width - left - right, height - top - bottom
    groups: dict[str, list[tuple[float, float, float]]] = {}
    for row in rows:
        groups.setdefault(row[group_key], []).append((
            float(row[x_key]), float(row[y_key]),
            float(row.get(ci_key, 0.0)) if ci_key else 0.0,
        ))
    for values in groups.values():
        values.sort()
    all_x = [x for values in groups.values() for x, _, _ in values]
    all_y = [y - ci for values in groups.values() for _, y, ci in values] + [y + ci for values in groups.values() for _, y, ci in values]
    xmin, xmax = min(all_x), max(all_x)
    ymin, ymax = min(all_y), max(all_y)
    pad = 0.08 * (ymax - ymin or 1.0)
    ymin, ymax = max(0.0, ymin - pad), ymax + pad

    def sx(value: float) -> float:
        return left + (value - xmin) / (xmax - xmin or 1.0) * plot_w

    def sy(value: float) -> float:
        return top + (ymax - value) / (ymax - ymin or 1.0) * plot_h

    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image, "RGBA")
    title_font, label_font, tick_font = _font(20, True), _font(14), _font(12)
    title_box = draw.textbbox((0, 0), title, font=title_font)
    draw.text(((width - (title_box[2] - title_box[0])) / 2, 20), title, fill="black", font=title_font)
    for index in range(6):
        value = ymin + index * (ymax - ymin) / 5
        y = sy(value)
        draw.line((left, y, width - right, y), fill="#dddddd", width=1)
        label = f"{value:.2f}"
        box = draw.textbbox((0, 0), label, font=tick_font)
        draw.text((left - 10 - (box[2] - box[0]), y - 7), label, fill="black", font=tick_font)
    x_ticks = sorted(set(all_x))
    if len(x_ticks) > 12:
        stride = max(1, len(x_ticks) // 8)
        x_ticks = x_ticks[::stride]
        if x_ticks[-1] != xmax:
            x_ticks.append(xmax)
    for value in x_ticks:
        x = sx(value)
        draw.line((x, top, x, height - bottom), fill="#eeeeee", width=1)
        label = f"{value:g}"
        box = draw.textbbox((0, 0), label, font=tick_font)
        draw.text((x - (box[2] - box[0]) / 2, height - bottom + 10), label, fill="black", font=tick_font)
    draw.line((left, top, left, height - bottom), fill="black", width=2)
    draw.line((left, height - bottom, width - right, height - bottom), fill="black", width=2)
    for index, (group, values) in enumerate(groups.items()):
        color = COLORS[index % len(COLORS)]
        if ci_key:
            polygon = [(sx(x), sy(y + ci)) for x, y, ci in values] + [(sx(x), sy(y - ci)) for x, y, ci in reversed(values)]
            draw.polygon(polygon, fill=color + "24")
        points = [(sx(x), sy(y)) for x, y, _ in values]
        draw.line(points, fill=color, width=3, joint="curve")
        if len(points) <= 12:
            for x, y in points:
                draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=color)
    # Draw the legend last so subsequent uncertainty polygons cannot obscure it.
    for index, group in enumerate(groups):
        color = COLORS[index % len(COLORS)]
        lx, ly = width - right - 185, top + 15 + index * 22
        draw.rectangle((lx - 8, ly - 11, width - right - 2, ly + 10), fill=(255, 255, 255, 215))
        draw.line((lx, ly, lx + 27, ly), fill=color, width=3)
        draw.text((lx + 34, ly - 7), group, fill="black", font=tick_font)
    x_box = draw.textbbox((0, 0), x_label, font=label_font)
    draw.text((left + (plot_w - (x_box[2] - x_box[0])) / 2, height - 30), x_label, fill="black", font=label_font)
    rotated = Image.new("RGBA", (plot_h, 35), (255, 255, 255, 0))
    rdraw = ImageDraw.Draw(rotated)
    y_box = rdraw.textbbox((0, 0), y_label, font=label_font)
    rdraw.text(((plot_h - (y_box[2] - y_box[0])) / 2, 5), y_label, fill="black", font=label_font)
    rotated = rotated.rotate(90, expand=True)
    image.paste(rotated, (18, top), rotated)
    image.save(path, format="PNG", optimize=True)
