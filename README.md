# API Performance Monitor

A beginner-friendly Flask project that checks HTTP endpoints and records response time, HTTP status code, success/failure, and errors in SQLite. It includes a responsive dashboard and JSON endpoints for metrics/history.

## Features
- Add and remove API endpoints from the dashboard.
- Manually run a check and record response time and HTTP status.
- Show latest result, average response time, and success rate.
- Save check history in a local SQLite database.
- JSON endpoints: `/api/health`, `/api/metrics`, `/api/history/<id>`.
- Responsive mobile-friendly layout.

## Requirements
- Python 3.10 or newer
- Internet access to install Python packages and reach the endpoint being checked

## Run locally
1. Download or clone this repository.
2. Open a terminal in the project folder.
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Start the server:
   ```bash
   python app.py
   ```
5. Open `http://127.0.0.1:5000` in your browser.
6. Add an endpoint and press **Check now**.

On Android, you can upload the files to GitHub using the browser. To run the Python app from a phone, you will need a Python-capable environment; GitHub stores the code but does not run the Flask server by itself.

## JSON endpoints
- `GET /api/health` — service health.
- `GET /api/metrics` — latest results and summary metrics for all monitored endpoints.
- `GET /api/history/1?limit=20` — recent check history for endpoint ID 1. The limit is capped at 100.

## Important limitations
- Checks are manual, not automatic/background checks.
- This starter version does not include Grafana integration. The dashboard is built into Flask.
- Only check APIs you own or have permission to test. Each request has an 8-second timeout.
- The SQLite database (`monitor.db`) is created automatically when the app starts and should generally not be uploaded to GitHub.

## Suggested next improvements
1. Add a scheduled background checker.
2. Add charts for response-time history.
3. Add authentication before hosting publicly.
4. Add Prometheus metrics and a Grafana dashboard.
5. Add deployment configuration for a hosting provider.
