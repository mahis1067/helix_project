from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import openpyxl


ROOT = Path(__file__).resolve().parent
WORKBOOK = ROOT / "dining_hall_mock_data.xlsx"
PERIODS = ("morning", "afternoon", "evening")

MEAL_DISHES = {
    "morning": {
        "Oatmeal Bowl", "Pancakes", "Scrambled Eggs and Toast"
    },
    "afternoon": {
        "Chicken Caesar Salad", "Beef Burger", "Tomato Pasta",
        "Cheese Pizza", "Lentil Soup"
    },
    "evening": {
        "Beef Stew", "Chicken Alfredo Pasta", "Salmon with Rice",
        "Veggie Tofu Stir-fry"
    },
}


def rows(sheet_name):
    workbook = openpyxl.load_workbook(WORKBOOK, data_only=True)
    sheet = workbook[sheet_name]
    headers = [cell.value for cell in sheet[1]]
    return [dict(zip(headers, [cell.value for cell in row]))
            for row in sheet.iter_rows(min_row=2)]


def mean(values):
    values = [float(value) for value in values if value is not None]
    return sum(values) / len(values) if values else 0


def dashboard_data():
    attendance = rows("table1_attendance")
    dishes = rows("table2_dishes")
    purchases = rows("table3_ingredients")
    emission = rows("emission_factors")

    dish_stats = {}
    for dish in dishes:
        name = dish["dish"]
        ratio = dish["leftover"] / dish["amount_made"] if dish["amount_made"] else 0
        stats = dish_stats.setdefault(name, {
            "consumed": 0,
            "made": 0,
            "leftover_ratios": [],
            "ingredients": dish["ingredients"],
            "periods": set(),
        })
        stats["consumed"] += max(dish["amount_made"] - dish["leftover"], 0)
        stats["made"] += dish["amount_made"]
        stats["leftover_ratios"].append(ratio)
        stats["periods"].add(dish["time_of_day_served"])

    popular = []
    for name, stats in dish_stats.items():
        popular.append({
            "dish": name,
            "consumed": stats["consumed"],
            "made": stats["made"],
            "consumed_pct": stats["consumed"] / stats["made"] if stats["made"] else 0,
            "avg_leftover_pct": mean(stats["leftover_ratios"]),
            "ingredients": stats["ingredients"],
            "periods": sorted(stats["periods"]),
        })
    popular.sort(key=lambda item: item["consumed"], reverse=True)

    period_attendance = {}
    for period in PERIODS:
        period_attendance[period] = round(mean([
            row["number_of_students"] for row in attendance
            if row["time_period"] == period
        ]))

    period_leftovers = {}
    for period in PERIODS:
        ratios = [
            row["leftover"] / row["amount_made"] for row in dishes
            if row["time_of_day_served"] == period and row["amount_made"]
        ]
        period_leftovers[period] = mean(ratios)

    emission_lookup = {
        row["ingredient"]: row["kg_co2e_per_kg"] for row in emission
        if row["kg_co2e_per_kg"] is not None
    }
    purchase_totals = {}
    for row in purchases:
        name = row["ingredient_bought"]
        purchase_totals[name] = purchase_totals.get(name, 0) + row["amount_kg"]
    carbon = [
        {
            "ingredient": name,
            "total_kg": amount,
            "kg_co2e": amount * emission_lookup.get(name, 0),
        }
        for name, amount in purchase_totals.items()
    ]
    carbon.sort(key=lambda item: item["kg_co2e"], reverse=True)

    return {
        "attendance": attendance,
        "dishes": dishes,
        "purchases": purchases,
        "emission_factors": emission,
        "popular_dishes": popular,
        "period_attendance": period_attendance,
        "period_leftovers": period_leftovers,
        "carbon": carbon,
    }


def r_tree_insights():
    insights = {}
    for filename in ("r_turnout_tree_importance.csv", "r_leftover_tree_importance.csv"):
        path = ROOT / filename
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                insights.setdefault(row["model"], {})[row["factor"]] = float(row["importance_pct"])
    return insights


def recommend(period="afternoon", day=None, available=None):
    period = period.lower()
    if period not in PERIODS:
        period = "afternoon"
    available = {item.strip().lower() for item in (available or []) if item.strip()}
    data = dashboard_data()

    day = day or "Monday"
    matching_attendance = [
        row["number_of_students"] for row in data["attendance"]
        if row["time_period"] == period and row["day"] == day
    ]
    if matching_attendance:
        predicted_turnout = round(mean(matching_attendance))
    else:
        predicted_turnout = data["period_attendance"][period]

    insights = r_tree_insights()
    r_weight = 1 if insights else 0
    recommendations = []

    for dish in data["popular_dishes"]:
        ingredients = [
            item.strip().lower()
            for item in dish["ingredients"].split(",")
            if item.strip()
        ]
        available_count = sum(item in available for item in ingredients) if available else len(ingredients)
        missing = [item for item in ingredients if item not in available] if available else []
        ingredient_coverage = available_count / len(ingredients) if ingredients else 0

        meal_fit = 1 if dish["dish"] in MEAL_DISHES[period] else 0
        if period in dish["periods"]:
            meal_fit += 0.5

        low_leftover_bonus = 1 - dish["avg_leftover_pct"]
        popularity = dish["consumed_pct"]

        score = (
            35 * meal_fit
            + 25 * popularity
            + 20 * low_leftover_bonus
            + 20 * ingredient_coverage
        )
        if r_weight:
            dish_importance = insights.get("leftovers", {}).get("dish", 0)
            period_importance = insights.get("leftovers", {}).get("time_of_day_served", 0)
            score += 0.12 * dish_importance + 0.08 * period_importance

        recommendations.append({
            **dish,
            "predicted_turnout": predicted_turnout,
            "missing_ingredients": missing,
            "ingredient_coverage": round(ingredient_coverage * 100),
            "meal_fit": period if period in dish["periods"] or dish["dish"] in MEAL_DISHES[period] else "cross-period",
            "score": round(score, 1),
        })

    recommendations.sort(key=lambda item: item["score"], reverse=True)
    top = recommendations[:3]
    chosen = top[0] if top else None
    return {
        "period": period,
        "day": day,
        "predicted_turnout": predicted_turnout,
        "recommendations": top,
        "chosen": chosen,
        "tree_insights": insights,
        "decision_basis": {
            "popularity": "Higher share of portions consumed",
            "leftovers": "Lower historical share left over",
            "ingredients": "Higher share of ingredients marked available",
            "meal_fit": "Preferred breakfast, lunch, or dinner dishes",
            "turnout": "Historical attendance for the selected day and time",
        },
    }


def excel_date(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    return datetime.now()


def add_entry(table, payload):
    workbook = openpyxl.load_workbook(WORKBOOK)
    sheet = workbook[table]

    if table == "table1_attendance":
        date_value = excel_date(payload["date"])
        day_value = payload["day"]
        period = payload["time_period"].lower()
        row = [date_value, day_value, period, int(payload["number_of_students"])]
    elif table == "table2_dishes":
        date_value = excel_date(payload["date"])
        row = [
            date_value,
            payload["dish"].strip(),
            payload["ingredients"].strip(),
            int(payload["amount_made"]),
            payload["time_of_day_served"].lower(),
            int(payload["leftover"]),
        ]
    elif table == "table3_ingredients":
        date_value = excel_date(payload["purchase_date"])
        ingredient = payload["ingredient_bought"].strip().lower()
        amount = float(payload["amount_kg"])

        factor_sheet = workbook["emission_factors"]
        emission_lookup = {
            factor_sheet.cell(row, 1).value: factor_sheet.cell(row, 2).value
            for row in range(2, factor_sheet.max_row + 1)
        }
        carbon = amount * (emission_lookup.get(ingredient, 0) or 0)
        row = [date_value, ingredient, amount, round(carbon, 3)]
    else:
        raise ValueError("Unknown table")

    sheet.append(row)
    workbook.save(WORKBOOK)
    return row


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/data":
            self.send_json(200, dashboard_data())
        elif parsed.path == "/api/recommend":
            params = parse_qs(parsed.query)
            period = params.get("period", ["morning"])[0]
            day = params.get("day", [None])[0]
            available = params.get("available", [""])[0].split(",")
            self.send_json(200, recommend(period, day, available))
        elif parsed.path.startswith("/"):
            relative = parsed.path.lstrip("/")
            file_path = (ROOT / relative).resolve()
            if parsed.path == "/" or parsed.path == "":
                file_path = ROOT / "dashboard.html"
            if file_path == ROOT or ROOT not in file_path.parents:
                self.send_json(403, {"error": "Forbidden"})
                return
            if file_path.exists() and file_path.is_file():
                content_type = "text/html"
                if file_path.suffix == ".css":
                    content_type = "text/css"
                elif file_path.suffix == ".js":
                    content_type = "text/javascript"
                elif file_path.suffix == ".png":
                    content_type = "image/png"
                elif file_path.suffix == ".pdf":
                    content_type = "application/pdf"
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.end_headers()
                self.wfile.write(file_path.read_bytes())
            else:
                self.send_json(404, {"error": "Not found"})
        else:
            self.send_json(404, {"error": "Not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/add":
            self.send_json(404, {"error": "Not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            table = payload.pop("table")
            added = add_entry(table, payload)
            self.send_json(201, {"ok": True, "row": added})
        except Exception as exc:
            self.send_json(400, {"ok": False, "error": str(exc)})

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8000), Handler)
    print("Dining Hall Dashboard: http://127.0.0.1:8000")
    server.serve_forever()
