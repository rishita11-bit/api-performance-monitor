import os
import sqlite3
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from flask import Flask, jsonify, redirect, render_template, request, url_for, flash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-for-production")
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(os.path.dirname(__file__), "monitor.db"))
REQUEST_TIMEOUT = 8


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS monitored_apis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                api_id INTEGER NOT NULL,
                checked_at TEXT NOT NULL,
                status_code INTEGER,
                response_time_ms REAL,
                is_success INTEGER NOT NULL,
                error TEXT,
                FOREIGN KEY(api_id) REFERENCES monitored_apis(id)
            )
        """)


def valid_http_url(url):
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def check_api(api_id, url):
    started = time.perf_counter()
    status_code = None
    error = None
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        status_code = response.status_code
        success = 200 <= response.status_code < 400
    except requests.RequestException as exc:
        success = False
        error = str(exc)[:500]
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with get_db() as conn:
        conn.execute(
            """INSERT INTO checks
               (api_id, checked_at, status_code, response_time_ms, is_success, error)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (api_id, checked_at, status_code, elapsed_ms, int(success), error),
        )
    return {
        "api_id": api_id,
        "checked_at": checked_at,
        "status_code": status_code,
        "response_time_ms": elapsed_ms,
        "is_success": success,
        "error": error,
    }


@app.route("/")
def dashboard():
    with get_db() as conn:
        apis = conn.execute("SELECT * FROM monitored_apis ORDER BY id DESC").fetchall()
        cards = []
        for api in apis:
            latest = conn.execute(
                "SELECT * FROM checks WHERE api_id=? ORDER BY id DESC LIMIT 1",
                (api["id"],),
            ).fetchone()
            totals = conn.execute(
                """SELECT COUNT(*) AS total,
                          SUM(CASE WHEN is_success=1 THEN 1 ELSE 0 END) AS successes,
                          AVG(response_time_ms) AS avg_ms
                   FROM checks WHERE api_id=?""",
                (api["id"],),
            ).fetchone()
            total = totals["total"] or 0
            successes = totals["successes"] or 0
            cards.append({
                "api": api,
                "latest": latest,
                "total": total,
                "success_rate": round(successes * 100 / total, 1) if total else None,
                "avg_ms": round(totals["avg_ms"], 2) if totals["avg_ms"] is not None else None,
            })
    return render_template("dashboard.html", cards=cards)


@app.post("/apis")
def add_api():
    name = request.form.get("name", "").strip()
    url = request.form.get("url", "").strip()
    if not name or not url or not valid_http_url(url):
        flash("Please enter a name and a valid http:// or https:// URL.", "error")
        return redirect(url_for("dashboard"))
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO monitored_apis (name, url, created_at) VALUES (?, ?, ?)",
                (name, url, datetime.now(timezone.utc).isoformat(timespec="seconds")),
            )
        flash("API added. Select Check now to record its first measurement.", "success")
    except sqlite3.IntegrityError:
        flash("That URL is already being monitored.", "error")
    return redirect(url_for("dashboard"))


@app.post("/apis/<int:api_id>/check")
def check_one(api_id):
    with get_db() as conn:
        api = conn.execute("SELECT * FROM monitored_apis WHERE id=?", (api_id,)).fetchone()
    if not api:
        flash("API not found.", "error")
    else:
        result = check_api(api["id"], api["url"])
        state = "success" if result["is_success"] else "failure"
        flash(f"Check complete: {state}, {result['response_time_ms']} ms.", "success" if result["is_success"] else "error")
    return redirect(url_for("dashboard"))


@app.post("/apis/<int:api_id>/delete")
def delete_api(api_id):
    with get_db() as conn:
        conn.execute("DELETE FROM checks WHERE api_id=?", (api_id,))
        conn.execute("DELETE FROM monitored_apis WHERE id=?", (api_id,))
    flash("API and its check history deleted.", "success")
    return redirect(url_for("dashboard"))


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "API Performance Monitor"})


@app.get("/api/metrics")
def metrics():
    with get_db() as conn:
        apis = conn.execute("SELECT * FROM monitored_apis ORDER BY id").fetchall()
        results = []
        for api in apis:
            latest = conn.execute(
                "SELECT * FROM checks WHERE api_id=? ORDER BY id DESC LIMIT 1",
                (api["id"],),
            ).fetchone()
            totals = conn.execute(
                """SELECT COUNT(*) AS total,
                          SUM(CASE WHEN is_success=1 THEN 1 ELSE 0 END) AS successes,
                          AVG(response_time_ms) AS avg_ms
                   FROM checks WHERE api_id=?""",
                (api["id"],),
            ).fetchone()
            total = totals["total"] or 0
            results.append({
                "id": api["id"],
                "name": api["name"],
                "url": api["url"],
                "latest_check": dict(latest) if latest else None,
                "checks_total": total,
                "success_rate_percent": round((totals["successes"] or 0) * 100 / total, 1) if total else None,
                "average_response_time_ms": round(totals["avg_ms"], 2) if totals["avg_ms"] is not None else None,
            })
    return jsonify({"count": len(results), "apis": results})


@app.get("/api/history/<int:api_id>")
def history(api_id):
    limit = request.args.get("limit", default=20, type=int)
    limit = max(1, min(limit or 20, 100))
    with get_db() as conn:
        api = conn.execute("SELECT id, name, url FROM monitored_apis WHERE id=?", (api_id,)).fetchone()
        if not api:
            return jsonify({"error": "API not found"}), 404
        rows = conn.execute(
            "SELECT checked_at, status_code, response_time_ms, is_success, error FROM checks WHERE api_id=? ORDER BY id DESC LIMIT ?",
            (api_id, limit),
        ).fetchall()
    return jsonify({"api": dict(api), "history": [dict(row) for row in rows]})


@app.errorhandler(404)
def not_found(_error):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Not found"}), 404
    return "Page not found", 404


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
