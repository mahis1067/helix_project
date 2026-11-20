from pathlib import Path

import openpyxl
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
WORKBOOK = ROOT / "dining_hall_mock_data.xlsx"
PLOTS = ROOT / "plots"
PLOTS.mkdir(exist_ok=True)


def font(size=22, bold=False):
    candidates = [
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def workbook_rows(sheet):
    wb = openpyxl.load_workbook(WORKBOOK, data_only=True)
    ws = wb[sheet]
    headers = [cell.value for cell in ws[1]]
    return [dict(zip(headers, [cell.value for cell in row]))
            for row in ws.iter_rows(min_row=2)]


def horizontal_bars(path, title, subtitle, values, colors):
    image = Image.new("RGB", (1000, 650), "white")
    draw = ImageDraw.Draw(image)
    draw.text((45, 25), title, fill="#17233c", font=font(34, True))
    draw.text((45, 72), subtitle, fill="#667085", font=font(18))

    max_value = max(values.values()) if values else 1
    y = 125
    for label, value in values.items():
        draw.text((45, y - 2), label, fill="#17233c", font=font(20))
        bar_x = 260
        width = int(620 * value / max_value)
        draw.rounded_rectangle((bar_x, y, bar_x + 620, y + 34),
                               radius=17, fill="#edf0f5")
        draw.rounded_rectangle((bar_x, y, bar_x + width, y + 34),
                               radius=17, fill=colors[label])
        draw.text((900, y), f"{value:.1f}",
                  fill="#17233c", font=font(20, True))
        y += 58
    image.save(path)


dishes = workbook_rows("table2_dishes")

period_leftovers = {}
for period in ("morning", "afternoon", "evening"):
    ratios = [
        row["leftover"] / row["amount_made"] for row in dishes
        if row["time_of_day_served"] == period and row["amount_made"]
    ]
    period_leftovers[period] = sum(ratios) / len(ratios) * 100

horizontal_bars(
    PLOTS / "leftover_by_time_of_day.png",
    "Leftover share by time of day",
    "Lower is better",
    dict(period_leftovers),
    {"morning": "#E8A52B", "afternoon": "#0D7A63", "evening": "#2E73B8"},
)

dish_stats = {}
for row in dishes:
    name = row["dish"]
    consumed = max(row["amount_made"] - row["leftover"], 0)
    made = row["amount_made"]
    stats = dish_stats.setdefault(name, [0, 0])
    stats[0] += consumed
    stats[1] += made

consumed = {
    name: values[0] for name, values in sorted(
        dish_stats.items(), key=lambda item: item[1][0], reverse=True
    )
}
horizontal_bars(
    PLOTS / "most_consumed_dishes.png",
    "Most consumed dishes",
    "Total portions consumed",
    consumed,
    {name: "#2E73B8" for name in consumed},
)

print("Generated chart assets")
