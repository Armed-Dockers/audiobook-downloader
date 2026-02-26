import subprocess

import requests
from flask import Flask, render_template, request

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
        # Cover art is optional.
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
                download_and_tag_audiobook(book_data)

                context["message"] = (
                    f"Downloaded '{book_data['title']}' ({len(book_data['chapters'])} chapters). "
                    "Files were saved to the Audiobooks folder."
                )
            except Exception as exc:
                context["errors"].append(f"An error occurred: {exc}")

            preview, _ = _scrape_preview(url)
            context["preview"] = preview
            return render_template("index.html", **context)

    return render_template("index.html", **context)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
