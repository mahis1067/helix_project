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

INVENTORY_SHEET = "kitchen_inventory"
SCORING_CONFIG = ROOT / "recommendation_scoring.json"

DEFAULT_SCORING_CONFIG = {
    "tree_influence": 0.5,
    "components": {
        "meal_fit": {
            "weight": 35,
            "model": "leftovers",
            "factors": ["time_of_day_served", "time_period"],
        },
        "popularity": {
            "weight": 25,
            "model": "leftovers",
            "factors": ["dish"],
        },
        "low_waste": {
            "weight": 20,
            "model": "leftovers",
            "factors": ["dish", "made_per_student"],
        },
        "ingredient_coverage": {
            "weight": 20,
            "model": None,
            "factors": [],
        },
    },
}


def load_scoring_config():
    if not SCORING_CONFIG.exists():
        return DEFAULT_SCORING_CONFIG
    with SCORING_CONFIG.open(encoding="utf-8") as handle:
        config = json.load(handle)
    return validate_scoring_config(config)


def validate_scoring_config(config):
    if not isinstance(config, dict):
        raise ValueError("Scoring config must be a JSON object")
    influence = float(config.get("tree_influence", 0))
    if not 0 <= influence <= 1:
        raise ValueError("tree_influence must be between 0 and 1")

    components = config.get("components")
    if not isinstance(components, dict) or not components:
        raise ValueError("components must be a non-empty object")

    cleaned = {"tree_influence": influence, "components": {}}
    for name, component in components.items():
        if not isinstance(component, dict):
            raise ValueError("Each component must be a JSON object")
        weight = float(component.get("weight", 0))
        if weight < 0:
            raise ValueError("Component weights cannot be negative")
        factors = component.get("factors", [])
        if not isinstance(factors, list) or not all(isinstance(item, str) for item in factors):
            raise ValueError("Component factors must be a list of names")
        model = component.get("model")
        if model is not None and not isinstance(model, str):
            raise ValueError("Component model must be a string or null")
        cleaned["components"][name] = {
            "weight": weight,
            "model": model,
            "factors": factors,
        }

    if sum(item["weight"] for item in cleaned["components"].values()) <= 0:
        raise ValueError("At least one component weight must be greater than zero")
    return cleaned


def ensure_inventory_sheet():
    workbook = openpyxl.load_workbook(WORKBOOK)
    if INVENTORY_SHEET not in workbook.sheetnames:
        sheet = workbook.create_sheet(INVENTORY_SHEET)
        sheet.append(["ingredient", "quantity_kg", "last_updated"])
        totals = {}
        for row in rows("table3_ingredients"):
            ingredient = str(row["ingredient_bought"] or "").strip().lower()
            totals[ingredient] = totals.get(ingredient, 0) + float(row["amount_kg"] or 0)
        for ingredient, quantity in totals.items():
            sheet.append([
                ingredient,
                quantity,
                datetime.now(),
            ])
        workbook.save(WORKBOOK)


def inventory_rows():
    ensure_inventory_sheet()
    workbook = openpyxl.load_workbook(WORKBOOK, data_only=True)
    sheet = workbook[INVENTORY_SHEET]
    headers = [cell.value for cell in sheet[1]]
    return [dict(zip(headers, [cell.value for cell in row]))
            for row in sheet.iter_rows(min_row=2)]


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


def inventory_data():
    data = dashboard_data()
    emission_lookup = {
        row["ingredient"]: row["kg_co2e_per_kg"]
        for row in data["emission_factors"]
        if row["kg_co2e_per_kg"] is not None
    }
    inventory = []
    for row in inventory_rows():
        quantity = float(row["quantity_kg"] or 0)
        ingredient = str(row["ingredient"] or "").strip().lower()
        if not ingredient:
            continue
        inventory.append({
            "ingredient": ingredient,
            "quantity_kg": round(quantity, 3),
            "kg_co2e_per_kg": float(emission_lookup.get(ingredient, 0) or 0),
            "stock_kg_co2e": round(quantity * float(emission_lookup.get(ingredient, 0) or 0), 3),
            "last_updated": row["last_updated"].isoformat() if isinstance(row["last_updated"], datetime) else str(row["last_updated"] or ""),
        })
    inventory.sort(key=lambda item: item["quantity_kg"], reverse=True)
    return inventory


def update_inventory(ingredient, quantity_kg, action="set"):
    ensure_inventory_sheet()
    ingredient = ingredient.strip().lower()
    if not ingredient:
        raise ValueError("Ingredient is required")
    quantity = float(quantity_kg)
    if quantity < 0:
        raise ValueError("Quantity cannot be negative")

    workbook = openpyxl.load_workbook(WORKBOOK)
    sheet = workbook[INVENTORY_SHEET]
    matching_row = None
    for row in range(2, sheet.max_row + 1):
        if str(sheet.cell(row, 1).value or "").strip().lower() == ingredient:
            matching_row = row
            break

    if matching_row:
        current = float(sheet.cell(matching_row, 2).value or 0)
        updated = quantity if action == "set" else current + quantity if action == "add" else max(current - quantity, 0)
        sheet.cell(matching_row, 2).value = round(updated, 3)
        sheet.cell(matching_row, 3).value = datetime.now()
    else:
        if action == "remove":
            raise ValueError("Ingredient is not in inventory")
        sheet.append([ingredient, round(quantity, 3), datetime.now()])
    workbook.save(WORKBOOK)
    updated_row = next((item for item in inventory_rows() if item["ingredient"] == ingredient), None)
    return {
        "ingredient": ingredient,
        "quantity_kg": round(float(updated_row["quantity_kg"] or 0), 3) if updated_row else 0,
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


def effective_scoring_weights(config, insights):
    influence = config["tree_influence"]
    effective = {}

    for name, component in config["components"].items():
        base_weight = component["weight"]
        model = component["model"]
        importance_values = [
            insights.get(model, {}).get(factor, 0)
            for factor in component["factors"]
        ]
        factor_importance = max(importance_values) if importance_values else 0
        factor_share = max(0, min(factor_importance, 100)) / 100
        effective[name] = base_weight * (1 - influence + influence * factor_share)

    total = sum(effective.values())
    if total:
        effective = {
            name: weight * 100 / total
            for name, weight in effective.items()
        }
    return effective


def recommend(period="afternoon", day=None, available=None):
    period = period.lower()
    if period not in PERIODS:
        period = "afternoon"
    inventory = inventory_data()
    inventory_lookup = {item["ingredient"]: item["quantity_kg"] for item in inventory}
    available = {name for name, quantity in inventory_lookup.items() if quantity > 0}
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
    config = load_scoring_config()
    weights = effective_scoring_weights(config, insights)
    recommendations = []

    for dish in data["popular_dishes"]:
        ingredients = [
            item.strip().lower()
            for item in dish["ingredients"].split(",")
            if item.strip()
        ]
        available_count = sum(item in available for item in ingredients)
        missing = [item for item in ingredients if item not in available]
        ingredient_coverage = available_count / len(ingredients) if ingredients else 0

        meal_fit = 1 if dish["dish"] in MEAL_DISHES[period] else 0
        if period in dish["periods"]:
            meal_fit += 0.5
        meal_fit_score = min(meal_fit / 1.5, 1)

        low_leftover_bonus = 1 - dish["avg_leftover_pct"]
        popularity = dish["consumed_pct"]

        score_breakdown = {
            "meal_fit": weights.get("meal_fit", 0) * meal_fit_score,
            "popularity": weights.get("popularity", 0) * popularity,
            "low_waste": weights.get("low_waste", 0) * low_leftover_bonus,
            "ingredient_coverage": weights.get("ingredient_coverage", 0) * ingredient_coverage,
        }
        score = sum(score_breakdown.values())

        emission_lookup = {
            row["ingredient"]: row["kg_co2e_per_kg"]
            for row in data["emission_factors"]
            if row["kg_co2e_per_kg"] is not None
        }
        carbon_breakdown = [
            {
                "ingredient": ingredient,
                "kg_co2e_per_kg": float(emission_lookup.get(ingredient, 0) or 0),
            }
            for ingredient in ingredients
        ]
        dish_carbon = sum(item["kg_co2e_per_kg"] for item in carbon_breakdown)

        recommendations.append({
            **dish,
            "predicted_turnout": predicted_turnout,
            "missing_ingredients": missing,
            "ingredient_coverage": round(ingredient_coverage * 100),
            "meal_fit": period if period in dish["periods"] or dish["dish"] in MEAL_DISHES[period] else "cross-period",
            "score": round(score, 1),
            "score_breakdown": {
                name: round(value, 1)
                for name, value in score_breakdown.items()
            },
            "score_weights": {
                name: round(value, 1)
                for name, value in weights.items()
            },
            "carbon_breakdown": carbon_breakdown,
            "estimated_kg_co2e": round(dish_carbon, 3),
        })

    recommendations.sort(key=lambda item: item["score"], reverse=True)
    top = recommendations[:5]
    total_score = sum(max(item["score"], 0) for item in top)
    allocated = 0
    for index, item in enumerate(top):
        if index == len(top) - 1:
            item["amount_to_make"] = max(predicted_turnout - allocated, 0)
        else:
            share = max(item["score"], 0) / total_score if total_score else 1 / len(top)
            item["amount_to_make"] = int(round(predicted_turnout * share))
            allocated += item["amount_to_make"]
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
        body = json.dumps(
            payload,
            default=lambda value: value.isoformat() if isinstance(value, datetime) else str(value),
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/data":
            self.send_json(200, dashboard_data())
        elif parsed.path == "/api/inventory":
            self.send_json(200, {"inventory": inventory_data()})
        elif parsed.path == "/api/databases":
            workbook = openpyxl.load_workbook(WORKBOOK, data_only=True)
            tables = {}
            for sheet in workbook.sheetnames:
                worksheet = workbook[sheet]
                headers = [str(cell.value) if cell.value is not None else "" for cell in worksheet[1]]
                rows_out = []
                for row in worksheet.iter_rows(min_row=2, values_only=True):
                    if not any(value is not None for value in row):
                        continue
                    item = {}
                    for index, header in enumerate(headers):
                        if not header:
                            continue
                        value = row[index]
                        if isinstance(value, datetime):
                            value = value.isoformat()
                        item[header] = value
                    rows_out.append(item)
                tables[sheet] = {"headers": [h for h in headers if h], "rows": rows_out}
            self.send_json(200, {"tables": tables})
        elif parsed.path == "/api/recommend":
            params = parse_qs(parsed.query)
            period = params.get("period", ["morning"])[0]
            day = params.get("day", [None])[0]
            self.send_json(200, recommend(period, day))
        elif parsed.path == "/api/scoring-config":
            try:
                insights = r_tree_insights()
                config = load_scoring_config()
                self.send_json(200, {
                    "config": config,
                    "tree_insights": insights,
                    "effective_weights": effective_scoring_weights(config, insights),
                })
            except Exception as exc:
                self.send_json(400, {"error": str(exc)})
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
        length = int(self.headers.get("Content-Length", "0"))
        if parsed.path == "/api/scoring-config":
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                config = validate_scoring_config(payload)
                with SCORING_CONFIG.open("w", encoding="utf-8") as handle:
                    json.dump(config, handle, indent=2)
                    handle.write("\n")
                insights = r_tree_insights()
                self.send_json(200, {
                    "ok": True,
                    "config": config,
                    "effective_weights": effective_scoring_weights(config, insights),
                })
            except Exception as exc:
                self.send_json(400, {"ok": False, "error": str(exc)})
            return
        if parsed.path == "/api/inventory":
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                updated = update_inventory(
                    payload["ingredient"],
                    payload["quantity_kg"],
                    payload.get("action", "set"),
                )
                self.send_json(200, {"ok": True, "item": updated})
            except Exception as exc:
                self.send_json(400, {"ok": False, "error": str(exc)})
            return
        if parsed.path != "/api/add":
            self.send_json(404, {"error": "Not found"})
            return
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
    ensure_inventory_sheet()
    server = ThreadingHTTPServer(("127.0.0.1", 8010), Handler)
    print("Dining Hall Dashboard: http://127.0.0.1:8010")
    server.serve_forever()
