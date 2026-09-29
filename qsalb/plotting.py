from __future__ import annotations

import html
from pathlib import Path
from typing import Iterable


COLORS = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#000000", "#7A5195"]


def _ticks(low: float, high: float, count: int = 5) -> list[float]:
    if high <= low:
        high = low + 1.0
    return [low + i * (high - low) / count for i in range(count + 1)]


def line_chart(path: Path, rows: list[dict[str, str]], x_key: str, y_key: str,
               group_key: str, title: str, x_label: str, y_label: str,
               ci_key: str | None = None) -> None:
    width, height = 900, 560
    left, right, top, bottom = 92, 28, 55, 78
    plot_w, plot_h = width - left - right, height - top - bottom
    groups: dict[str, list[tuple[float, float, float]]] = {}
    for row in rows:
        group = row[group_key]
        groups.setdefault(group, []).append((float(row[x_key]), float(row[y_key]), float(row.get(ci_key, 0.0)) if ci_key else 0.0))
    for values in groups.values():
        values.sort()
    all_x = [point[0] for values in groups.values() for point in values]
    all_y = [point[1] - point[2] for values in groups.values() for point in values] + [point[1] + point[2] for values in groups.values() for point in values]
    xmin, xmax = min(all_x), max(all_x)
    ymin, ymax = min(all_y), max(all_y)
    pad = 0.08 * (ymax - ymin or 1.0)
    ymin, ymax = max(0.0, ymin - pad), ymax + pad

    def sx(value: float) -> float:
        return left + (value - xmin) / (xmax - xmin or 1.0) * plot_w

    def sy(value: float) -> float:
        return top + (ymax - value) / (ymax - ymin or 1.0) * plot_h

    content = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
               '<rect width="100%" height="100%" fill="white"/>',
               f'<text x="{width/2}" y="30" text-anchor="middle" font-family="sans-serif" font-size="20">{html.escape(title)}</text>']
    for value in _ticks(ymin, ymax):
        y = sy(value)
        content.append(f'<line x1="{left}" y1="{y:.2f}" x2="{width-right}" y2="{y:.2f}" stroke="#dddddd"/>')
        content.append(f'<text x="{left-10}" y="{y+4:.2f}" text-anchor="end" font-family="sans-serif" font-size="12">{value:.2f}</text>')
    for value in sorted(set(all_x)):
        x = sx(value)
        content.append(f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" y2="{height-bottom}" stroke="#eeeeee"/>')
        content.append(f'<text x="{x:.2f}" y="{height-bottom+22}" text-anchor="middle" font-family="sans-serif" font-size="12">{value:g}</text>')
    content.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}" stroke="black"/>')
    content.append(f'<line x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{height-bottom}" stroke="black"/>')
    for index, (group, values) in enumerate(groups.items()):
        color = COLORS[index % len(COLORS)]
        if ci_key:
            upper = " ".join(f"{sx(x):.2f},{sy(y+ci):.2f}" for x, y, ci in values)
            lower = " ".join(f"{sx(x):.2f},{sy(y-ci):.2f}" for x, y, ci in reversed(values))
            content.append(f'<polygon points="{upper} {lower}" fill="{color}" opacity="0.12"/>')
        points = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y, _ in values)
        content.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2.5"/>')
        for x, y, _ in values:
            content.append(f'<circle cx="{sx(x):.2f}" cy="{sy(y):.2f}" r="4" fill="{color}"/>')
        lx, ly = width - right - 155, top + 18 + index * 22
        content.append(f'<line x1="{lx}" y1="{ly}" x2="{lx+25}" y2="{ly}" stroke="{color}" stroke-width="3"/>')
        content.append(f'<text x="{lx+32}" y="{ly+4}" font-family="sans-serif" font-size="12">{html.escape(group)}</text>')
    content.append(f'<text x="{left+plot_w/2}" y="{height-20}" text-anchor="middle" font-family="sans-serif" font-size="14">{html.escape(x_label)}</text>')
    content.append(f'<text transform="translate(22 {top+plot_h/2}) rotate(-90)" text-anchor="middle" font-family="sans-serif" font-size="14">{html.escape(y_label)}</text>')
    content.append('</svg>')
    path.write_text("\n".join(content), encoding="utf-8")


def make_figures(aggregate_rows: list[dict[str, str]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    specifications = [
        ("average_queue", "Average total backlog vs load", "Average tasks/node"),
        ("estimated_latency_ms", "Estimated end-to-end latency vs load", "Latency (ms)"),
        ("energy_j_per_slot", "Energy consumption vs load", "Energy (J/slot)"),
        ("queue_variance", "Queue variance vs load", "Queue variance"),
        ("cloud_ratio", "Cloud dependency vs load", "Cloud task ratio"),
        ("drop_ratio", "Task drop ratio vs load", "Dropped task ratio"),
    ]
    baseline = [row for row in aggregate_rows if row["experiment"] == "baseline"]
    ablation = [row for row in aggregate_rows if row["experiment"] == "ablation"]
    for metric, title, y_label in specifications:
        if baseline:
            line_chart(output_dir / f"baseline_{metric}.svg", baseline, "arrival_rate", f"{metric}_mean", "policy", title, "Arrival rate (tasks/device/slot)", y_label, f"{metric}_ci95")
        if ablation and metric in {"average_queue", "estimated_latency_ms", "energy_j_per_slot", "cloud_ratio"}:
            line_chart(output_dir / f"ablation_{metric}.svg", ablation, "arrival_rate", f"{metric}_mean", "policy", f"Ablation: {title.lower()}", "Arrival rate (tasks/device/slot)", y_label, f"{metric}_ci95")

