from flask import Flask, Response, jsonify, request, send_from_directory
from datetime import datetime

import recommend_dish


app = Flask(__name__)
app.json.sort_keys = False


def json_safe(value):
    if isinstance(value, dict):
        return {
            str(key) if key is not None else "": json_safe(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


@app.route("/api/data", methods=["GET"])
def api_data():
    return jsonify(json_safe(recommend_dish.dashboard_data()))


@app.route("/api/inventory", methods=["GET", "POST"])
def api_inventory():
    if request.method == "GET":
        return jsonify({"inventory": json_safe(recommend_dish.inventory_data())})

    payload = request.get_json(silent=True) or {}
    try:
        updated = recommend_dish.update_inventory(
            payload["ingredient"],
            payload["quantity_kg"],
            payload.get("action", "set"),
        )
        return jsonify({"ok": True, "item": updated})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/databases", methods=["GET"])
def api_databases():
    from openpyxl import load_workbook

    workbook = load_workbook(recommend_dish.WORKBOOK, data_only=True)
    tables = {}
    for sheet in workbook.sheetnames:
        worksheet = workbook[sheet]
        headers = [
            str(cell.value) if cell.value is not None else ""
            for cell in worksheet[1]
        ]
        rows_out = []
        for row in worksheet.iter_rows(min_row=2, values_only=True):
            if not any(value is not None for value in row):
                continue
            item = {}
            for index, header in enumerate(headers):
                if header:
                    value = row[index]
                    if hasattr(value, "isoformat"):
                        value = value.isoformat()
                    item[header] = value
            rows_out.append(item)
        tables[sheet] = {"headers": [h for h in headers if h], "rows": rows_out}
    return jsonify(json_safe({"tables": tables}))


@app.route("/api/recommend", methods=["GET"])
def api_recommend():
    period = request.args.get("period", "morning")
    day = request.args.get("day")
    return jsonify(json_safe(recommend_dish.recommend(period, day)))


@app.route("/api/scoring-config", methods=["GET", "POST"])
def api_scoring_config():
    if request.method == "GET":
        try:
            insights = recommend_dish.r_tree_insights()
            config = recommend_dish.load_scoring_config()
            return jsonify({
                "config": config,
                "tree_insights": insights,
                "effective_weights": recommend_dish.effective_scoring_weights(
                    config, insights
                ),
            })
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400

    try:
        payload = request.get_json(silent=True) or {}
        config = recommend_dish.validate_scoring_config(payload)
        recommend_dish.SCORING_CONFIG.write_text(
            __import__("json").dumps(config, indent=2) + "\n",
            encoding="utf-8",
        )
        insights = recommend_dish.r_tree_insights()
        return jsonify({
            "ok": True,
            "config": config,
            "effective_weights": recommend_dish.effective_scoring_weights(
                config, insights
            ),
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/add", methods=["POST"])
def api_add():
    payload = request.get_json(silent=True) or {}
    try:
        table = payload.pop("table")
        added = recommend_dish.add_entry(table, payload)
        return jsonify({"ok": True, "row": added}), 201
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
