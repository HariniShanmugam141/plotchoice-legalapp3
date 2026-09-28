"""
PlotChoice EC Automation POC
-----------------------------
Built from a real Playwright Codegen recording against the live TNREGINET
site (session ran in Tamil - no English toggle was used), so all selectors
below are the actual DOM text/values, not guesses.

Flow:
  1. /start-ec-search   -> opens TNREGINET, navigates to the EC search page,
                            fills the form, clicks "Add", screenshots the
                            captcha, keeps the browser session alive.
  2. /submit-captcha    -> types the human-entered captcha into the SAME
                            still-open page, clicks Search, handles the
                            confirm dialog, and downloads the EC PDF.
  3. /download/<sid>    -> serves the generated EC PDF.

IMPORTANT LIMITATION OF THIS POC:
Zone / District / SRO / Village are picked on TNREGINET by internal numeric
value codes (e.g. Zone "1", District "20003"), not by name. Right now this
script only knows the codes for ONE combination - the exact one recorded via
codegen: Zone=Chennai, District=Chennai, SRO=AnnaNagar, Village=Padi.

To add another combination:
  1. Run:  playwright codegen https://tnreginet.gov.in/portal/
  2. Click through to the EC page and pick the new Zone/District/SRO/Village
  3. Copy the four select_option(...) values codegen prints
  4. Add a new entry to KNOWN_VALUE_CODES below

Run:
    pip install flask playwright
    playwright install chromium
    python app.py
"""

import os
import time
import uuid
import base64
import threading
from datetime import datetime

from flask import Flask, request, jsonify, render_template, send_file
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

app = Flask(__name__)

SESSIONS = {}
SESSION_LOCK = threading.Lock()
SESSION_TTL_SECONDS = 5 * 60

DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

TNREGINET_HOME_URL = "https://tnreginet.gov.in/portal/webHP?requestType=ApplicationRH&actionVal=homePage&screenId=114&UserLocaleID=en"

# Exact Tamil link text for "Free Encumbrance Certificate view/download"
EC_LINK_TEXT = "Search/View EC"

# Exact Tamil field labels/button text from the live DOM (via codegen)
ZONE_LABEL = "Zone *"
DISTRICT_LABEL = "District *"
SRO_LABEL = "Sub Registrar Office *"
START_DATE_TEXTBOX = "EC Start Date *"
END_DATE_TEXTBOX = "EC End Date *"
VILLAGE_LABEL = "Registration Village *"
CAPTCHA_TEXTBOX_LABEL = "Type the code shown"
ADD_BUTTON_TEXT = "Add"
SEARCH_BUTTON_TEXT = "Search"
OK_BUTTON_TEXT = "OK"
DOWNLOAD_LINK_TEXT = "Click here"

import re
def _select_when_ready(select_locator, label_text, timeout=15000):
    escaped = re.escape(label_text.strip())
    option_locator = select_locator.locator("option").filter(
        has_text=re.compile(escaped, re.IGNORECASE)
    )
    option_locator.first.wait_for(state="attached", timeout=timeout)
    exact_text = option_locator.first.inner_text().strip()
    select_locator.select_option(label=exact_text)

_GLOBAL_PW = None
_GLOBAL_BROWSER = None
_GLOBAL_PAGE = None

def get_global_page():
    global _GLOBAL_PW, _GLOBAL_BROWSER, _GLOBAL_PAGE
    if _GLOBAL_PW is None:
        _GLOBAL_PW = sync_playwright().start()
        _GLOBAL_BROWSER = _GLOBAL_PW.chromium.launch(headless=True, channel="chrome", slow_mo=200)
    
    if _GLOBAL_PAGE is None:
        _GLOBAL_PAGE = _GLOBAL_BROWSER.new_page()
        _GLOBAL_PAGE.goto(TNREGINET_HOME_URL, timeout=30000)
        try:
            _GLOBAL_PAGE.locator("#MobileAppModal").get_by_text("×").click(timeout=4000)
        except Exception:
            pass
        _GLOBAL_PAGE.locator("a").filter(has_text=EC_LINK_TEXT).first.click(force=True)
        _GLOBAL_PAGE.wait_for_timeout(500)
    return _GLOBAL_PAGE


@app.route("/api/options", methods=["POST"])
def get_options():
    global _GLOBAL_PAGE
    data = request.get_json(force=True)
    target = data.get("target")
    zone = data.get("zone", "")
    district = data.get("district", "")
    sro = data.get("sro", "")

    try:
        page = get_global_page()
        
        if target == "zone":
            select = page.get_by_label(ZONE_LABEL)
            select.locator("option").nth(1).wait_for(state="attached", timeout=10000)
            options = select.locator("option").all_inner_texts()
            return jsonify([o.strip() for o in options if o.strip() and "- Select -" not in o])

        elif target == "district":
            _select_when_ready(page.get_by_label(ZONE_LABEL), zone)
            select = page.get_by_label(DISTRICT_LABEL)
            select.locator("option").nth(1).wait_for(state="attached", timeout=10000)
            options = select.locator("option").all_inner_texts()
            return jsonify([o.strip() for o in options if o.strip() and "- Select -" not in o])

        elif target == "sro":
            _select_when_ready(page.get_by_label(ZONE_LABEL), zone)
            _select_when_ready(page.get_by_label(DISTRICT_LABEL), district)
            select = page.get_by_label(SRO_LABEL)
            select.locator("option").nth(1).wait_for(state="attached", timeout=10000)
            options = select.locator("option").all_inner_texts()
            return jsonify([o.strip() for o in options if o.strip() and "- Select -" not in o])
            
        elif target == "doc_sro":
            page.locator("label:has-text('Document Number Wise')").first.click(force=True)
            select = page.locator("#cmb_SroName")
            select.locator("option").nth(1).wait_for(state="attached", timeout=10000)
            options = select.locator("option").all_inner_texts()
            return jsonify([o.strip() for o in options if o.strip() and "- Select -" not in o])

        elif target == "doc_year":
            page.locator("label:has-text('Document Number Wise')").first.click(force=True)
            select = page.locator("#cmb_Year")
            select.locator("option").nth(1).wait_for(state="attached", timeout=10000)
            options = select.locator("option").all_inner_texts()
            return jsonify([o.strip() for o in options if o.strip() and "- Select -" not in o])

        elif target == "doc_type":
            page.locator("label:has-text('Document Number Wise')").first.click(force=True)
            select = page.locator("#cmb_doc_type")
            select.locator("option").nth(1).wait_for(state="attached", timeout=10000)
            options = select.locator("option").all_inner_texts()
            return jsonify([o.strip() for o in options if o.strip() and "- Select -" not in o])

        elif target == "village":
            _select_when_ready(page.get_by_label(ZONE_LABEL), zone)
            _select_when_ready(page.get_by_label(DISTRICT_LABEL), district)
            _select_when_ready(page.get_by_label(SRO_LABEL), sro)
            select = page.get_by_label(VILLAGE_LABEL)
            select.locator("option").nth(1).wait_for(state="attached", timeout=10000)
            options = select.locator("option").all_inner_texts()
            return jsonify([o.strip() for o in options if o.strip() and "- Select -" not in o])

        return jsonify([])
    except Exception as e:
        if hasattr(_THREAD_LOCAL, "page"): _GLOBAL_PAGE = None
        return jsonify({"error": str(e)}), 500


def _cleanup_stale_sessions():
    now = time.time()
    with SESSION_LOCK:
        stale = [sid for sid, s in SESSIONS.items() if now - s["created_at"] > SESSION_TTL_SECONDS]
        for sid in stale:
            _close_session(sid)


def _close_session(sid):
    session = SESSIONS.pop(sid, None)
    if not session:
        return
    try:
        session["page"].close()
        session["context"].close()
        session["browser"].close()
        session["playwright"].stop()
    except Exception as e:
        print(f"[cleanup] error closing session {sid}: {e}")


_MONTH_ABBR = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}


def _pick_date(page, textbox_label, target_date):
    """
    Types the date directly into the textbox as DD-Mon-YYYY (the format
    confirmed visible on the live TNREGINET field, e.g. "01-Jul-2026"),
    instead of clicking through the custom calendar widget.

    The earlier calendar-click approach (open picker, select month/year from
    a combobox, click the day link) was unreliable - it silently failed to
    change the displayed month and just clicked whatever day was already
    showing (today's month), producing a wrong date range with zero search
    results. Typing directly avoids that failure mode entirely.
    """
    date_str = f"{target_date.day:02d}-{_MONTH_ABBR[target_date.month]}-{target_date.year}"
    box = page.get_by_role("textbox", name=textbox_label)
    box.click()
    box.fill(date_str)
    page.keyboard.press("Escape")

    actual_value = box.input_value()
    if date_str not in actual_value:
        print(f"[warn] date field '{textbox_label}' shows '{actual_value}' - expected '{date_str}'. "
              f"The typed-fill approach may not be accepted here either - re-check via codegen.")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/start-ec-search", methods=["POST"])
def start_ec_search():
    _cleanup_stale_sessions()
    data = request.get_json(force=True)

    search_mode = data.get("search_mode", "ec")

    if search_mode == "ec":
        zone = data.get("zone", "")
        district = data.get("district", "")
        sro = data.get("sro", "")
        village = data.get("village", "")
        try:
            start_date = datetime.strptime(data["ec_start_date"], "%Y-%m-%d").date()
            end_date = datetime.strptime(data["ec_end_date"], "%Y-%m-%d").date()
        except (KeyError, ValueError) as e:
            return jsonify({"error": f"Invalid date fields: {e}"}), 400
    else:
        doc_sro = data.get("doc_sro", "")
        document_number = data.get("document_number", "")
        document_year = data.get("document_year", "")
        document_type = data.get("document_type", "")

    sid = str(uuid.uuid4())
    try:
        if _GLOBAL_PW is None:
            get_global_page()
            
        pw = _GLOBAL_PW
        browser = _GLOBAL_PW.chromium.launch(headless=True, channel="chrome", slow_mo=300)
        context = browser.new_context()
        page = context.new_page()
    except Exception as e:
        return jsonify({"error": f"Could not launch browser: {e}"}), 500

    try:
        page.goto(TNREGINET_HOME_URL, timeout=30000)

        # Mobile app promo modal - may or may not appear
        try:
            page.locator("#MobileAppModal").get_by_text("×").click(timeout=4000)
        except Exception:
            pass

        page.locator("a").filter(has_text=EC_LINK_TEXT).first.click(force=True)

        if search_mode == "ec":
            _select_when_ready(page.get_by_label(ZONE_LABEL), zone)
            _select_when_ready(page.get_by_label(DISTRICT_LABEL), district)
            _select_when_ready(page.get_by_label(SRO_LABEL), sro)

            _pick_date(page, START_DATE_TEXTBOX, start_date)
            _pick_date(page, END_DATE_TEXTBOX, end_date)

            _select_when_ready(page.get_by_label(VILLAGE_LABEL), village)

            page.locator("#txt_SurveyNo").fill(data.get("survey_no", ""))

            if data.get("sub_division"):
                try:
                    page.locator("#txt_SubDivisionNo").fill(data["sub_division"], timeout=3000)
                except Exception:
                    pass
            page.get_by_role("button", name=ADD_BUTTON_TEXT).click()
        else:
            page.locator("label:has-text('Document Number Wise')").first.click(force=True)
            page.wait_for_timeout(1000)
            _select_when_ready(page.locator("#cmb_SroName"), doc_sro)
            page.locator("#txt_DocNo").fill(document_number)
            _select_when_ready(page.locator("#cmb_Year"), document_year)
            _select_when_ready(page.locator("#cmb_doc_type"), document_type)

        captcha_locator = page.locator("#captcha")
        captcha_locator.wait_for(state="visible", timeout=15000)
        captcha_bytes = captcha_locator.screenshot()
        captcha_b64 = base64.b64encode(captcha_bytes).decode("utf-8")

    except Exception as e:
        _close_session_objects(pw, browser, context, page)
        return jsonify({"error": f"Failed while filling form: {e}"}), 500

    with SESSION_LOCK:
        SESSIONS[sid] = {
            "pw": pw,
            "browser": browser,
            "context": context,
            "page": page,
            "created_at": time.time(),
        }

    return jsonify({"session_id": sid, "captcha_image_base64": captcha_b64})


@app.route("/submit-captcha", methods=["POST"])
def submit_captcha():
    data = request.get_json(force=True)
    sid = data.get("session_id")
    captcha_text = data.get("captcha_text", "").strip()

    with SESSION_LOCK:
        session = SESSIONS.get(sid)

    if not session:
        return jsonify({"error": "Session expired or not found. Please restart the search."}), 404

    page = session["page"]

    try:
        page.get_by_role("textbox", name=CAPTCHA_TEXTBOX_LABEL).fill(captcha_text)
        page.get_by_role("button", name=SEARCH_BUTTON_TEXT).click()

        download_link = page.get_by_role("link", name=DOWNLOAD_LINK_TEXT)
        try:
            download_link.wait_for(state="visible", timeout=20000)
        except PlaywrightTimeoutError:
            print(f"[debug] stuck after search - current URL: {page.url}")
            print(f"[debug] stuck after search - page title: {page.title()}")
            # Save a screenshot of exactly what's on screen right now so we can
            # see what's actually blocking - a dialog, an error message,
            # a page that navigated somewhere unexpected, etc.
            debug_path = os.path.join(os.path.dirname(__file__), "debug_after_search.png")
            try:
                page.screenshot(path=debug_path, full_page=True)
            except Exception:
                pass

            captcha_locator = page.locator("#captcha")
            captcha_locator.wait_for(state="visible", timeout=15000)
            captcha_bytes = captcha_locator.screenshot()
            captcha_b64 = base64.b64encode(captcha_bytes).decode("utf-8")
            return jsonify({
                "status": "retry",
                "message": f"Captcha incorrect or page didn't advance. Try again. (debug screenshot saved: {debug_path})",
                "captcha_image_base64": captcha_b64,
            })

        with page.expect_download() as download_info:
            with page.expect_popup() as popup_info:
                download_link.click()
            popup = popup_info.value
        download = download_info.value

        pdf_path = os.path.join(DOWNLOAD_DIR, f"{sid}.pdf")
        download.save_as(pdf_path)
        popup.close()

        # Final confirm dialog after closing the download popup, if present.
        try:
            page.get_by_role("button", name=OK_BUTTON_TEXT).click(timeout=4000)
        except PlaywrightTimeoutError:
            pass

        _close_session(sid)
        return jsonify({"status": "success", "download_url": f"/download/{sid}"})

    except Exception as e:
        return jsonify({"error": f"Failed while submitting captcha: {e}"}), 500


@app.route("/download/<sid>")
def download(sid):
    pdf_path = os.path.join(DOWNLOAD_DIR, f"{sid}.pdf")
    if not os.path.exists(pdf_path):
        return jsonify({"error": "File not found or already downloaded."}), 404
    return send_file(pdf_path, as_attachment=True, download_name="Encumbrance_Certificate.pdf")


def _close_session_objects(pw, browser, context, page):
    try:
        page.close()
        context.close()
        browser.close()
        # pw.stop()  # Do not stop global playwright
    except Exception:
        pass


if __name__ == "__main__":
    from wsgiref.simple_server import make_server
    print("Preloading EC portal... this will take 10 seconds.")
    get_global_page()

    print("Starting single-threaded WSGI server on port 5000...")
    server = make_server("127.0.0.1", 5000, app)
    server.serve_forever()
















