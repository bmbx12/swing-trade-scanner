"""Flask web app for Swing Trade Scanner."""
import os
import io
import csv
import json
from datetime import datetime
from flask import Flask, render_template, jsonify, request, Response
from dotenv import load_dotenv
from fmp_client import FMPClient
from scanner import Scanner

load_dotenv(override=True)


def create_app(testing=False):
    app = Flask(__name__)
    app.config["TESTING"] = testing

    # Store latest scan results in memory for CSV download
    app.latest_scan = None

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/scan", methods=["POST"])
    def run_scan():
        api_key = os.getenv("FMP_API_KEY")
        if not api_key or api_key == "your_api_key_here":
            return jsonify({
                "error": "FMP API key not configured. Add your key to the .env file."
            }), 400

        try:
            config = {
                "market_cap_min": 1_000_000_000,
                "volume_min": 500_000,
                "ath_min": 10.0,
                "ath_max": 60.0,
                "top_n": 15,
            }
            if request.is_json and request.json:
                config.update({
                    k: v for k, v in request.json.items() if k in config
                })

            client = FMPClient(api_key=api_key)
            scanner = Scanner(client=client, config=config)
            results = scanner.run_scan()

            app.latest_scan = results
            _save_report(results)

            return jsonify(results)

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/csv")
    def download_csv():
        if not app.latest_scan:
            return jsonify({"error": "No scan data available. Run a scan first."}), 400

        stocks = app.latest_scan.get("stocks", [])
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Rank", "Ticker", "Name", "Sector", "Sector Performance %",
            "Current Price", "52-Week High", "All-Time High",
            "% Below ATH", "Target Price", "Potential Upside %",
            "Conviction Score",
        ])
        for stock in stocks:
            writer.writerow([
                stock.get("rank", ""),
                stock.get("symbol", ""),
                stock.get("name", ""),
                stock.get("sector", ""),
                stock.get("sector_performance", ""),
                stock.get("price", ""),
                stock.get("yearHigh", ""),
                stock.get("ath", ""),
                stock.get("pct_below_ath", ""),
                stock.get("target_price", ""),
                stock.get("upside_pct", ""),
                stock.get("score", ""),
            ])

        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={
                "Content-Disposition":
                    f"attachment; filename=swing_scan_{datetime.now().strftime('%Y%m%d')}.csv"
            },
        )

    return app


def _save_report(results: dict):
    """Save scan results as JSON to output directory."""
    os.makedirs("output", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = f"output/scan_{timestamp}.json"
    with open(filepath, "w") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    app = create_app()
    print("\n  Swing Trade Scanner running at http://localhost:5000\n")
    app.run(debug=True, port=5000)
