import subprocess
from copy import deepcopy

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


@app.route("/", methods=["GET", "POST"])
def index():
    context = {
        "supported_sites": SUPPORTED_SITES,
        "book_data": None,
        "errors": [],
        "message": None,
        "chapter_count": 0,
    }

    if request.method == "POST":
        if subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode != 0:
            context["errors"].append("ffmpeg is not available. Install ffmpeg and try again.")
            return render_template("index.html", **context)

        url = request.form.get("url", "").strip()
        scraper = get_scraper(url)

        if not scraper:
            context["errors"].append("Unsupported URL. Use one of the supported audiobook sites.")
            return render_template("index.html", **context)

        try:
            scraped_data = scraper.fetch_book_data(url)
            if not scraped_data or not scraped_data.get("chapters"):
                context["errors"].append("Failed to scrape chapters for that URL.")
                return render_template("index.html", **context)

            book_data = deepcopy(scraped_data)
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
                    context["book_data"] = scraped_data
                    context["chapter_count"] = len(scraped_data["chapters"])
                    return render_template("index.html", **context)
                book_data["chapters"] = [book_data["chapters"][index] for index in selected_indices]

            _prepare_cover_data(book_data)
            download_and_tag_audiobook(book_data)

            context["message"] = (
                f"Download started and completed for '{book_data['title']}' "
                f"({len(book_data['chapters'])} chapters). Files were saved to the Audiobooks folder."
            )
            context["book_data"] = scraped_data
            context["chapter_count"] = len(scraped_data["chapters"])
            return render_template("index.html", **context)
        except Exception as exc:
            context["errors"].append(f"An error occurred: {exc}")

    return render_template("index.html", **context)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
