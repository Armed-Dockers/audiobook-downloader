import subprocess
import threading
import time
import uuid

import requests
from flask import Flask, jsonify, redirect, render_template, request, url_for

from main import download_and_tag_audiobook, get_scraper
from utils import parse_chapter_ranges, sanitize_book_title

app = Flask(__name__)

SUPPORTED_SITES = [
    "tokybook.com",
    "zaudiobooks.com",
    "fulllengthaudiobooks.net",
    "hdaudiobooks.net",
    "bigaudiobooks.net",
    "goldenaudiobook.net",
]

jobs = {}
jobs_lock = threading.Lock()


def _check_ffmpeg():
    return subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode == 0


def _prepare_cover_data(book_data):
    if not book_data.get("cover_url"):
        return

    try:
        artwork_response = requests.get(book_data["cover_url"], timeout=20)
        artwork_response.raise_for_status()
        content_type = artwork_response.headers.get("Content-Type", "")

        if content_type.startswith("image/"):
            book_data["artwork_data"] = artwork_response.content
            book_data["mime_type"] = (
                "image/jpeg"
                if content_type == "image/jpeg"
                or book_data["cover_url"].lower().endswith((".jpg", ".jpeg"))
                else "image/png"
            )
    except requests.exceptions.RequestException:
        pass


def _base_context():
    return {
        "supported_sites": SUPPORTED_SITES,
        "errors": [],
        "message": None,
        "preview": None,
    }


def _scrape_preview(url):
    scraper = get_scraper(url)
    if not scraper:
        return None, "Unsupported URL. Use one of the supported audiobook sites."

    scraped_data = scraper.fetch_book_data(url)
    if not scraped_data or not scraped_data.get("chapters"):
        return None, "Failed to scrape chapters for that URL."

    return {
        "url": url,
        "title": scraped_data.get("title") or "Unknown_Book",
        "author": scraped_data.get("author") or "",
        "narrator": scraped_data.get("narrator") or "",
        "year": scraped_data.get("year") or "",
        "cover_url": scraped_data.get("cover_url") or "",
        "chapter_count": len(scraped_data["chapters"]),
        "chapter_samples": [chapter.get("title", "Unknown") for chapter in scraped_data["chapters"][:10]],
    }, None


def _update_job(job_id, **updates):
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id].update(updates)


def _active_jobs_snapshot():
    with jobs_lock:
        active = []
        for job_id, job in jobs.items():
            if job.get("status") not in ("queued", "running"):
                continue
            total = job.get("total", 0) or 0
            current = job.get("current", 0) or 0
            percent = int((current / total) * 100) if total > 0 else 0
            active.append(
                {
                    "job_id": job_id,
                    "book_title": job.get("book_title", "Unknown_Book"),
                    "status": job.get("status", "queued"),
                    "message": job.get("message", "Queued"),
                    "current": current,
                    "total": total,
                    "percent": percent,
                    "started_at": job.get("started_at", 0),
                }
            )

    active.sort(key=lambda item: item["started_at"], reverse=True)
    return active


def _start_download_job(book_data):
    job_id = str(uuid.uuid4())
    with jobs_lock:
        jobs[job_id] = {
            "status": "queued",
            "message": "Queued",
            "current": 0,
            "total": len(book_data.get("chapters", [])),
            "book_title": book_data.get("title", "Unknown_Book"),
            "started_at": time.time(),
        }

    def run_download():
        def callback(current, total, message, status):
            _update_job(
                job_id,
                status=status,
                message=message,
                current=current,
                total=total,
            )

        try:
            _update_job(job_id, status="running", message="Starting download")
            download_and_tag_audiobook(book_data, progress_callback=callback)
            _update_job(job_id, status="completed", message="Download completed")
        except Exception as exc:
            _update_job(job_id, status="error", message=f"Download failed: {exc}")

    thread = threading.Thread(target=run_download, daemon=True)
    thread.start()
    return job_id


@app.route("/", methods=["GET", "POST"])
def index():
    context = _base_context()

    if request.method == "POST":
        action = request.form.get("action", "scrape")

        if not _check_ffmpeg():
            context["errors"].append("ffmpeg is not available. Install ffmpeg and try again.")
            return render_template("index.html", **context)

        if action == "scrape":
            url = request.form.get("url", "").strip()
            preview, error = _scrape_preview(url)
            if error:
                context["errors"].append(error)
            else:
                context["preview"] = preview
            return render_template("index.html", **context)

        if action == "download":
            url = request.form.get("url", "").strip()
            scraper = get_scraper(url)
            if not scraper:
                context["errors"].append("Unsupported URL. Use one of the supported audiobook sites.")
                return render_template("index.html", **context)

            try:
                book_data = scraper.fetch_book_data(url)
                if not book_data or not book_data.get("chapters"):
                    context["errors"].append("Failed to scrape chapters for that URL.")
                    return render_template("index.html", **context)

                book_data["title"] = sanitize_book_title(
                    request.form.get("title", "").strip() or book_data.get("title") or "Unknown_Book"
                )
                book_data["author"] = request.form.get("author", "").strip() or book_data.get("author")
                book_data["narrator"] = request.form.get("narrator", "").strip() or book_data.get("narrator")
                book_data["year"] = request.form.get("year", "").strip() or book_data.get("year")
                book_data["cover_url"] = request.form.get("cover_url", "").strip() or book_data.get("cover_url")

                chapter_selection = request.form.get("chapters", "").strip()
                if chapter_selection:
                    selected_indices = parse_chapter_ranges(chapter_selection, len(book_data["chapters"]))
                    if not selected_indices:
                        context["errors"].append("No valid chapter ranges were selected.")
                        context["preview"] = {
                            "url": url,
                            "title": request.form.get("title", "").strip(),
                            "author": request.form.get("author", "").strip(),
                            "narrator": request.form.get("narrator", "").strip(),
                            "year": request.form.get("year", "").strip(),
                            "cover_url": request.form.get("cover_url", "").strip(),
                            "chapter_count": len(book_data["chapters"]),
                            "chapter_samples": [
                                chapter.get("title", "Unknown") for chapter in book_data["chapters"][:10]
                            ],
                        }
                        return render_template("index.html", **context)
                    book_data["chapters"] = [book_data["chapters"][index] for index in selected_indices]

                _prepare_cover_data(book_data)
                job_id = _start_download_job(book_data)
                return redirect(url_for("download_status_page", job_id=job_id))
            except Exception as exc:
                context["errors"].append(f"An error occurred: {exc}")
                preview, _ = _scrape_preview(url)
                context["preview"] = preview
                return render_template("index.html", **context)

    return render_template("index.html", **context)


@app.route("/download/<job_id>")
def download_status_page(job_id):
    with jobs_lock:
        job = jobs.get(job_id)

    if not job:
        return redirect(url_for("index"))

    return render_template("download_status.html", job_id=job_id, book_title=job.get("book_title", "Unknown_Book"))


@app.route("/download-status/<job_id>")
def download_status(job_id):
    with jobs_lock:
        job = jobs.get(job_id)

    if not job:
        return jsonify({"error": "Job not found"}), 404

    return jsonify(job)


@app.route("/active-downloads")
def active_downloads():
    active_jobs = _active_jobs_snapshot()
    return jsonify({"count": len(active_jobs), "jobs": active_jobs})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
