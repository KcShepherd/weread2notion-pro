"""生成微信读书年度热力图 SVG（通过 API Key 鉴权）"""
import os
from datetime import datetime, timedelta

from weread2notionpro.weread_api import WeReadApi


# 默认颜色（匹配 github-heatmap 风格）
DEFAULT_COLORS = {
    0: "#EBEDF0",
    1: "#ACE7AE",
    2: "#69C16E",
    3: "#549F57",
    4: "#2B7239",
}


def fetch_yearly_daily_data(year):
    """通过 API Key 获取整年每日阅读时长（秒）"""
    api = WeReadApi()
    if not api.api_key:
        raise Exception("WEREAD_API_KEY not set, cannot fetch heatmap data")

    # 尝试年度模式（可能返回 dailyReadTimes）
    base_time = int(datetime(year, 1, 1, tzinfo=None).timestamp())
    r = api._gateway_post(
        "/readdata/detail",
        params={"mode": "annually", "baseTime": base_time},
    )
    daily = {}
    if r.ok:
        data = r.json()
        daily = data.get("dailyReadTimes", {})
        if daily:
            return {int(k): int(v) for k, v in daily.items()}

    # 年度模式无日明细，逐月查询
    print("年度模式无 dailyReadTimes，逐月查询...")
    for month in range(1, 13):
        bt = int(datetime(year, month, 1, tzinfo=None).timestamp())
        r = api._gateway_post(
            "/readdata/detail",
            params={"mode": "monthly", "baseTime": bt},
        )
        if r.ok:
            month_data = r.json()
            month_daily = month_data.get("readTimes", {})
            daily.update({int(k): int(v) for k, v in month_daily.items()})
    return daily


def generate_svg(daily_data, year, name, colors):
    """生成 GitHub 风格的热力图 SVG"""
    import calendar

    start_date = datetime(year, 1, 1)
    end_date = datetime(year, 12, 31)
    total_days = (end_date - start_date).days + 1

    # 找到第一个周日作为起点（GitHub 风格：列从周日开始）
    first_sunday = start_date
    while first_sunday.weekday() != 6:
        first_sunday -= timedelta(days=1)
    total_weeks = ((end_date - first_sunday).days // 7) + 1

    cell_size = 12
    cell_gap = 2
    label_width = 40
    header_height = 28
    bottom_margin = 8
    cols = total_weeks
    rows = 7

    width = label_width + cols * (cell_size + cell_gap) + 10
    height = header_height + rows * (cell_size + cell_gap) + bottom_margin + 14

    month_names = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]
    day_labels = ["", "Mon", "", "Wed", "", "Fri", ""]

    def color_for(seconds):
        if seconds <= 0:
            return colors.get(0, DEFAULT_COLORS[0])
        minutes = seconds / 60
        if minutes < 30:
            return colors.get(1, DEFAULT_COLORS[1])
        elif minutes < 60:
            return colors.get(2, DEFAULT_COLORS[2])
        elif minutes < 120:
            return colors.get(3, DEFAULT_COLORS[3])
        else:
            return colors.get(4, DEFAULT_COLORS[4])

    lines = []
    lines.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
    )
    lines.append(f'<rect width="{width}" height="{height}" fill="#FFFFFF"/>')

    # 年份 + 总时长
    total_seconds = sum(daily_data.values())
    total_hours = round(total_seconds / 3600, 1)
    lines.append(
        f'<text x="{label_width}" y="14" style="font-size:11px;font-family:Arial;'
        f'font-weight:bold;" fill="#333">{year}: {total_hours} hours'
        f'</text>'
    )

    y_offset = header_height

    # 月份标签
    month_positions = {}
    for m in range(1, 13):
        d = datetime(year, m, 1)
        # 找到该月第一天在哪些周
        week_num = (d - first_sunday).days // 7
        month_positions[m] = week_num
    last_label_end = -99
    for m in range(1, 13):
        cx = label_width + month_positions[m] * (cell_size + cell_gap)
        if cx - last_label_end < 20:
            continue
        lines.append(
            f'<text x="{cx}" y="{y_offset - 4}" '
            f'style="font-size:9px;font-family:Arial;" fill="#666">{month_names[m - 1]}</text>'
        )
        last_label_end = cx

    # 周标签
    for r in range(rows):
        cy = y_offset + r * (cell_size + cell_gap) + cell_size - 2
        lines.append(
            f'<text x="2" y="{cy}" style="font-size:8px;font-family:Arial;" '
            f'fill="#666" text-anchor="end">{day_labels[r]}</text>'
        )

    # 每天一个矩形
    for day_offset in range((end_date - first_sunday).days + 1):
        d = first_sunday + timedelta(days=day_offset)
        if d < start_date or d > end_date:
            continue
        col = day_offset // 7
        row = d.weekday()  # 0=Mon, 6=Sun
        # 把周日放到底部（GitHub 风格）
        display_row = (row + 1) % 7
        ts = int(d.timestamp())
        seconds = daily_data.get(ts, 0)
        c = color_for(seconds)
        x = label_width + col * (cell_size + cell_gap)
        y = y_offset + display_row * (cell_size + cell_gap)
        title = f"{d.strftime('%Y-%m-%d')}: {round(seconds / 60)} min"
        lines.append(
            f'<rect x="{x}" y="{y}" width="{cell_size}" height="{cell_size}" '
            f'rx="2" ry="2" fill="{c}"><title>{title}</title></rect>'
        )

    # 图例
    legend_y = height - 12
    legend_x = label_width
    lines.append(
        f'<text x="{legend_x}" y="{legend_y}" style="font-size:8px;font-family:Arial;" '
        f'fill="#666">Less</text>'
    )
    for level in range(5):
        rx = legend_x + 30 + level * (cell_size + 2)
        lines.append(
            f'<rect x="{rx}" y="{legend_y - 9}" width="{10}" height="{10}" '
            f'fill="{colors.get(level, DEFAULT_COLORS[level])}"/>'
        )
    lines.append(
        f'<text x="{legend_x + 30 + 5 * (cell_size + 2)}" y="{legend_y}" '
        f'style="font-size:8px;font-family:Arial;" fill="#666">More</text>'
    )

    lines.append("</svg>")
    return "\n".join(lines)


def main():
    year = int(os.getenv("YEAR", datetime.now().year))
    name = os.getenv("NAME", "")

    colors = {
        0: os.getenv("DOM_COLOR", DEFAULT_COLORS[0]),
        1: os.getenv("TRACK_COLOR", DEFAULT_COLORS[1]),
        2: os.getenv("SPECIAL_COLOR", DEFAULT_COLORS[2]),
        3: os.getenv("SPECIAL_COLOR2", DEFAULT_COLORS[3]),
        4: "#2B7239",
    }

    print(f"Fetching reading data for {year}...")
    daily = fetch_yearly_daily_data(year)
    print(f"Got {len(daily)} days of reading data, total {sum(daily.values())} seconds")

    print("Generating SVG...")
    svg = generate_svg(daily, year, name, colors)

    os.makedirs("OUT_FOLDER", exist_ok=True)
    # 固定文件名 weread.svg，兼容 workflow 后续的 rename 步骤
    filename = "weread.svg"
    filepath = os.path.join("OUT_FOLDER", filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"Generated: {filepath} ({len(svg)} bytes)")


if __name__ == "__main__":
    main()
