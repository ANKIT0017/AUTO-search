from flask import Flask, render_template, jsonify, request
import pandas as pd
import subprocess
import os
import glob
import math
import json
import psutil
import base64
import requests
import csv

app = Flask(__name__)


def get_latest_csv():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    csv_file = os.path.join(base_dir, "jobs_main.csv")
    if os.path.exists(csv_file):
        return csv_file
    return None


def clean_nan(obj):
    if isinstance(obj, float) and math.isnan(obj):
        return None
    if isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_nan(x) for x in obj]
    return obj


SETTINGS_FILE = "scraper_settings.json"

DEFAULT_SETTINGS = {
    "hours": 1,
    "sleep_time": 10,
    "scrape_from": ["linkedin", "indeed", "skillsire"],
    "search_term": "machine learning engineer",
    "results_fetch_count": 300,
    "country_to_search": "India",
    "file_name_prefix": "",
    "roles_of_interest": [
        "DevOps",
        "Data Engineer",
        "computer Vision Engineer",
        "NLP Engineer",
        "AI Researcher",
        "AI Scientist",
        "AI Specialist",
        "AI Developer",
        "Data Scientist",
        "Machine Learning Engineer",
        "AI Engineer",
        "Cloud Engineer",
        "Data Analyst",
        "Data Architect",
        "Big Data Engineer",
        "Data Visualization",
    ],
}


def push_settings_to_github():
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
    REPO = "ANKIT0017/AUTO-search"  # Updated to your actual repo
    BRANCH = "main"
    FILE_PATH = "scraper_settings.json"
    with open(FILE_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    content_b64 = base64.b64encode(content.encode()).decode()
    # Get the current file SHA
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        sha = r.json()["sha"]
    else:
        sha = None
    data = {
        "message": "Update scraper_settings.json from app",
        "content": content_b64,
        "branch": BRANCH,
    }
    if sha:
        data["sha"] = sha
    r = requests.put(url, headers=headers, json=data)
    return r.status_code in (200, 201)


BLOCKED_COMPANIES_FILE = "blocked_companies.json"


def load_blocked_companies():
    if os.path.exists(BLOCKED_COMPANIES_FILE):
        with open(BLOCKED_COMPANIES_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_blocked_companies(companies):
    with open(BLOCKED_COMPANIES_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(companies)), f, ensure_ascii=False, indent=2)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/jobs")
def get_jobs():
    csv_file = get_latest_csv()
    if not csv_file or not os.path.exists(csv_file):
        print("No CSV file found.", flush=True)
        return jsonify({"jobs": []})
    df = pd.read_csv(csv_file, comment="#")
    df.columns = [col.strip() for col in df.columns]
    expected_cols = [
        "job_url",
        "title",
        "company",
        "location",
        "scrape_date",
        "scrape_time",
    ]
    if list(df.columns) != expected_cols:
        print("CSV header mismatch! Columns found:", df.columns, flush=True)
        return jsonify({"jobs": []})
    df = df[df["job_url"].astype(str).str.startswith("http")]
    jobs = df.to_dict(orient="records")
    jobs = clean_nan(jobs)  # Clean NaN values for valid JSON
    return jsonify({"jobs": jobs})


@app.route("/api/scrape", methods=["POST"])
def trigger_scrape():
    print("SCRAPE ENDPOINT CALLED")
    try:
        # Start the scraper in the background (non-blocking)
        subprocess.Popen(["python", "JobScraperUltimate.py", "--csv", "jobs_main.csv"])
        return jsonify({"success": True, "message": "Scraping started in background."})
    except Exception as e:
        print("Exception:", str(e))
        return jsonify({"success": False, "message": str(e), "new_jobs": []})


@app.route("/api/stop_scrape", methods=["POST"])
def stop_scrape():
    with open("STOP_SCRAPE", "w") as f:
        f.write("stop")
    return jsonify({"success": True, "message": "Scraping will be stopped."})


@app.route("/api/stop_scraper/<int:pid>", methods=["POST"])
def stop_scraper_pid(pid):
    try:
        import psutil

        p = psutil.Process(pid)
        p.terminate()
        p.wait(timeout=5)
        return jsonify({"success": True, "message": f"Scraper process {pid} stopped."})
    except Exception as e:
        return jsonify(
            {"success": False, "message": f"Failed to stop process {pid}: {str(e)}"}
        )


@app.route("/api/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        settings = request.get_json()
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        push_settings_to_github()  # Always push updated settings to GitHub
        return jsonify({"success": True})
    else:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                settings = json.load(f)
        else:
            settings = DEFAULT_SETTINGS
        return jsonify(settings)


@app.route("/api/threads")
def get_threads():
    threads = []
    # Read the current search_term from settings
    search_term = ""
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            try:
                settings = json.load(f)
                search_term = settings.get("search_term", "")
            except Exception as e:
                print("Error reading settings:", e)
    for proc in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
        try:
            cmdline_str = " ".join(str(arg) for arg in (proc.info["cmdline"] or []))
            if (
                proc.info["name"]
                and "python" in proc.info["name"].lower()
                and "JobScraperUltimate" in cmdline_str
            ):
                threads.append(
                    {
                        "pid": proc.info["pid"],
                        "cmdline": cmdline_str,
                        "search_term": search_term,
                        "start_time": proc.info["create_time"],
                    }
                )
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            print(f"Process error: {e}")
            continue
    return jsonify({"threads": threads})


@app.route("/api/delete_job", methods=["POST"])
def delete_job():
    data = request.get_json()
    job_url = data.get("job_url")
    if not job_url:
        return jsonify({"success": False, "message": "Missing job_url"}), 400
    csv_file = get_latest_csv()
    if not csv_file or not os.path.exists(csv_file):
        return jsonify({"success": False, "message": "CSV file not found"}), 404
    df = pd.read_csv(csv_file, comment="#")
    before_count = len(df)
    df = df[df["job_url"] != job_url]
    after_count = len(df)
    df.to_csv(csv_file, index=False, quoting=csv.QUOTE_NONNUMERIC, escapechar="\\")
    return jsonify(
        {"success": True, "message": f"Deleted {before_count - after_count} job(s)."}
    )


@app.route("/api/block_company", methods=["POST"])
def block_company():
    data = request.get_json()
    company = data.get("company")
    if not company:
        return jsonify({"success": False, "message": "Missing company name"}), 400
    companies = load_blocked_companies()
    companies.add(company.strip())
    save_blocked_companies(companies)
    return jsonify({"success": True, "message": f"Blocked company: {company}"})


@app.route("/api/blocked_companies", methods=["GET"])
def get_blocked_companies():
    companies = sorted(list(load_blocked_companies()))
    return jsonify({"blocked_companies": companies})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
