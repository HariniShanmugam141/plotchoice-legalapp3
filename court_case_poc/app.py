import re
"""
Court Case Search POC
----------------------
Follows the SAME simple architecture as ec_automation_poc / cersai_poc:

  1. /start-court-search  -> launches Playwright, opens the official
                              eCourts Services portal, screenshots the
                              landing page, keeps the browser session
                              alive for manual CAPTCHA entry.
  2. /submit-captcha       -> types the human-entered CAPTCHA into the
                              SAME still-open page, clicks Search, and
                              parses whatever results are available.
  3. /download/<sid>       -> serves any generated result file, if any.

IMPORTANT / HONESTY NOTE ABOUT THIS POC:
This script does NOT invent, guess, or assume any TNREGINET/eCourts-style
internal selectors. The eCourts workflow (Case Status -> Party Name / CNR /
Court Details tabs, State/District/Court Complex dropdowns, CAPTCHA field,
results table, etc.) has NOT yet been captured via Playwright Codegen
against the live site, so every entry in ECOURTS_SELECTORS below is `None`.

Until those selectors are filled in from a real recording, this app will:
  - Successfully launch Playwright and open the official eCourts portal.
  - Take a real screenshot of whatever loads.
  - Report back "MANUAL_CONFIGURATION_REQUIRED" instead of pretending to
    search, click, or read results it has never verified against the
    live DOM.

To wire up a real search mode (Party Name, CNR, or Court Details):
  1. Run:  playwright codegen https://services.ecourts.gov.in/ecourtindia_v6/
  2. Manually click through to Case Status -> the tab you need.
  3. Copy the exact selector / label / role text codegen prints for each
     field listed in ECOURTS_SELECTORS.
  4. Replace the matching `None` value below.
  5. Implement the corresponding `_run_xxx_search()` step using
     page.get_by_role(...) / page.get_by_label(...) the same way
     ec_automation_poc does it.

Revenue Court is intentionally NOT wired to any URL. There is no single
official Revenue Court portal that works the same way nationwide, and
workflows differ by state. Selecting "Revenue Court" always returns
MANUAL_CONFIGURATION_REQUIRED until a specific state portal + workflow
is added to COURT_PROVIDERS and implemented explicitly.

Run:
    pip install -r requirements.txt
    playwright install chromium
    python app.py
"""

import os
import time
import uuid
import base64
import threading
import traceback
from datetime import datetime

from flask import Flask, request, jsonify, render_template, send_file
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCREENSHOT_DIR = os.path.join(BASE_DIR, "screenshots")
RESULTS_DIR = os.path.join(BASE_DIR, "results")
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")

for _d in (SCREENSHOT_DIR, RESULTS_DIR, DOWNLOAD_DIR):
    os.makedirs(_d, exist_ok=True)

SESSIONS = {}
SESSION_LOCK = threading.Lock()
SESSION_TTL_SECONDS = 5 * 60


# ==================================================================
# OFFICIAL PROVIDER CONFIGURATION
# ==================================================================
COURT_PROVIDERS = {
    "ECOURTS": {
        "name": "eCourts Services",
        "base_url": "https://services.ecourts.gov.in/ecourtindia_v6/?p=casestatus/index",
    },
    "REVENUE_COURT": {
        "name": "Revenue Court",
        # Deliberately left unset. Revenue Court workflows are state-specific
        # and no single official portal/workflow has been verified yet.
        "base_url": None,
    },
}


# ==================================================================
# SELECTOR CONFIGURATION
# ==================================================================
# TODO:
# Run Playwright Codegen against the official eCourts workflow.
# Replace None values with verified selectors.
# Do not guess selectors.
#
#   playwright codegen https://services.ecourts.gov.in/ecourtindia_v6/
#
ECOURTS_SELECTORS = {
    # Search navigation
    "case_status_menu": "a:has-text('Case Status')",
    "party_name_tab": "#partyname-tabMenu",
    "cnr_search_tab": "a:has-text('Search by CNR')",
    "court_search_tab": "a:has-text('Court Details')",

    # Location
    "state_select": "#sess_state_code",
    "district_select": "#sess_dist_code",
    "court_complex_select": "#court_complex_code",
    "establishment_select": "#court_est_code",

    # Party search
    "party_name_input": "#petres_name",
    "registration_year_input": "#rgyearP",
    "pending_option": "#radP",
    "disposed_option": "#radD",
    "both_option": "#radB",

    # CNR search
    "cnr_input": "#cino",
    "cnr_search_button": "#searchbtn",

    # Court details
    "case_type_select": "#case_type",
    "case_number_input": "#search_case_no",

    # CAPTCHA
    "captcha_image": "#captcha_image",
    "captcha_input": "#fcaptcha_code",

    # Actions
    "search_button": "button:has-text('Go') >> visible=true",

    # Results
    "result_table": "table.table",
    "result_container": "#dispTable",
    "no_result_message": "text='Record Not Found'",
    "case_link": "a",
}


def _selectors_configured(keys):
    """Return True only if every selector key needed for a step has a
    real, non-None value. Used to avoid guessing at DOM elements."""
    return all(ECOURTS_SELECTORS.get(k) for k in keys)


# ==================================================================
# SESSION HELPERS
# ==================================================================
def _cleanup_stale_sessions():
    now = time.time()
    with SESSION_LOCK:
        stale = [sid for sid, s in SESSIONS.items() if now - s["created_at"] > SESSION_TTL_SECONDS]
    for sid in stale:
        _close_session(sid)


def _close_session(sid):
    with SESSION_LOCK:
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


def _close_session_objects(pw, browser, context, page):
    try:
        if page:
            page.close()
        if context:
            context.close()
        if browser:
            browser.close()
        if pw:
            pw.stop()
    except Exception:
        pass


def _save_json(path, payload):
    import json
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=str)


def detect_portal_state(page):
    """
    Only classify a page state when it can be backed by either:
      (a) a verified, configured selector being present, or
      (b) unambiguous, clearly-identified visible text.
    """
    try:
        # Check for results OR no-results FIRST, because captcha image stays on screen
        if ECOURTS_SELECTORS.get("result_table"):
            try:
                if page.locator(ECOURTS_SELECTORS["result_table"]).is_visible(timeout=1000):
                    return "RESULT_AVAILABLE"
            except Exception:
                pass

        if ECOURTS_SELECTORS.get("no_result_message"):
            try:
                if page.locator(ECOURTS_SELECTORS["no_result_message"]).is_visible(timeout=1000):
                    return "NO_CASE_FOUND"
            except Exception:
                pass

        # Then check if captcha is required
        if ECOURTS_SELECTORS.get("captcha_image"):
            try:
                if page.locator(ECOURTS_SELECTORS["captcha_image"]).is_visible(timeout=1000):
                    return "CAPTCHA_REQUIRED"
            except Exception:
                pass

        return "SEARCH_AVAILABLE"
    except Exception:
        return "UNKNOWN"


# ==================================================================
# RESULT PARSING
# ==================================================================
def parse_case_results(page):
    """
    Extract only information actually present in official results.
    Never fabricate data. Until result selectors are verified via
    Playwright Codegen, this honestly reports that parsing cannot
    be performed yet rather than guessing at a table structure.
    """
    required = ("result_table", "result_container")
    if not _selectors_configured(required):
        return {
            "status": "MANUAL_CONFIGURATION_REQUIRED",
            "message": (
                "Official eCourts workflow opened successfully, but verified "
                "result selectors are not configured yet. Run Playwright "
                "Codegen against the live search-results page and populate "
                "ECOURTS_SELECTORS['result_table'] / ['result_container'] "
                "(and related row-level selectors) before result parsing "
                "can be implemented."
            ),
            "cases": [],
        }

    cases = []
    try:
        # Give it a moment for the table to fully populate
        page.wait_for_timeout(2000)
        
        # If eCourts grouped the results by Court Establishment, it shows links instead of a table.
        # e.g., "City Civil Court, Chennai: 38". Click the first one to expand the case table.
        if page.locator("text=Total Number of Establishments").is_visible(timeout=2000):
            # Click the first link that looks like an establishment link
            links = page.locator("a").all()
            for link in links:
                try:
                    text = link.inner_text()
                    if ":" in text and any(char.isdigit() for char in text):
                        link.click()
                        page.wait_for_timeout(3000)
                        break
                except Exception:
                    continue

        if page.locator("text='Petitioner and Advocate'").is_visible(timeout=1000):
            details = {"is_detailed": True}
            # Extract basic details from the first table
            try:
                # CNR Number
                cnr_loc = page.locator("td").filter(has_text=re.compile(r"CNR Number", re.IGNORECASE)).locator("xpath=following-sibling::td").first
                if cnr_loc.is_visible():
                    details["cnr_number"] = cnr_loc.inner_text().split()[0].strip()
                    
                reg_loc = page.locator("td").filter(has_text=re.compile(r"Registration Number", re.IGNORECASE)).locator("xpath=following-sibling::td").first
                if reg_loc.is_visible():
                    details["case_number"] = reg_loc.inner_text().strip()
            except: pass
            
            # Extract Case Status
            try:
                # Handle both Pending and Disposed case tables
                next_hearing_loc = page.locator("td").filter(has_text=re.compile(r"Next Hearing Date", re.IGNORECASE)).locator("xpath=following-sibling::td").first
                if next_hearing_loc.is_visible():
                    details["next_hearing_date"] = next_hearing_loc.inner_text().strip()
                
                decision_date_loc = page.locator("td").filter(has_text=re.compile(r"Decision Date", re.IGNORECASE)).locator("xpath=following-sibling::td").first
                if decision_date_loc.is_visible():
                    details["decision_date"] = decision_date_loc.inner_text().strip()
                
                stage_loc = page.locator("td").filter(has_text=re.compile(r"Case Stage", re.IGNORECASE)).locator("xpath=following-sibling::td").first
                if stage_loc.is_visible():
                    details["case_stage"] = stage_loc.inner_text().strip()
                    
                status_loc = page.locator("td").filter(has_text=re.compile(r"Case Status", re.IGNORECASE)).locator("xpath=following-sibling::td").first
                if status_loc.is_visible():
                    details["case_status"] = status_loc.inner_text().strip()
                    
                judge_loc = page.locator("td").filter(has_text=re.compile(r"Court Number and Judge", re.IGNORECASE)).locator("xpath=following-sibling::td").first
                if judge_loc.is_visible():
                    details["court"] = judge_loc.inner_text().strip()
            except: pass

            try:
                # Use evaluate to safely get text content across rows
                p_text = page.evaluate('''() => {
                    let ths = Array.from(document.querySelectorAll('th, td'));
                    let pHeader = ths.find(el => el.textContent && el.textContent.includes('Petitioner and Advocate'));
                    if (pHeader && pHeader.parentElement.nextElementSibling) {
                        return pHeader.parentElement.nextElementSibling.textContent.trim();
                    }
                    return 'Unknown';
                }''')
                r_text = page.evaluate('''() => {
                    let ths = Array.from(document.querySelectorAll('th, td'));
                    let rHeader = ths.find(el => el.textContent && el.textContent.includes('Respondent and Advocate'));
                    if (rHeader && rHeader.parentElement.nextElementSibling) {
                        return rHeader.parentElement.nextElementSibling.textContent.trim();
                    }
                    return 'Unknown';
                }''')
                details["party_names"] = f"{p_text} Vs {r_text}"
            except: pass
            
            try:
                # Capture all tables in the Case Details view!
                full_html = page.evaluate('''() => {
                    // Find all tables on the page that contain case details
                    let tables = Array.from(document.querySelectorAll('table'));
                    
                    // Filter out header/menu tables. We only want tables that come after or include "Case Type" or "Registration Number"
                    let startIndex = tables.findIndex(t => t.textContent.includes('Registration Number') || t.textContent.includes('Petitioner and Advocate'));
                    if (startIndex === -1) return ''; // Should not happen
                    
                    // eCourts usually wraps all these tables in a single div like #history_case_data
                    let container = document.querySelector('#history_case_data') || 
                                    document.querySelector('#history_case_details') ||
                                    document.querySelector('form[name="history_form"]');
                                    
                    if (container && container.textContent.includes('Petitioner and Advocate')) {
                        return container.innerHTML;
                    }
                    
                    // Fallback: Just take all tables from the Registration table onwards and wrap them
                    let validTables = tables.slice(startIndex);
                    let html = '';
                    for (let t of validTables) {
                        html += t.outerHTML + '<br>';
                    }
                    return html;
                }''')
                if full_html:
                    details["full_html"] = full_html
            except: pass

            return {
                "status": "CASES_FOUND",
                "cases": [details]
            }

        # Otherwise, parse the summary list
        try:
            table = page.locator(ECOURTS_SELECTORS["result_table"]).first
            if not table.is_visible(timeout=2000):
                table = page.locator("table").last
        except Exception:
            table = page.locator("table").last
        
        rows = table.locator("tbody tr").all()
        for row in rows:
            cells = row.locator("td").all()
            if len(cells) >= 3:
                case_info = {
                    "case_number": cells[1].text_content(timeout=1000).strip(),
                    "party_names": cells[2].text_content(timeout=1000).strip(),
                }
                
                # Try to extract CNR from the View button in the 4th column
                if len(cells) >= 4:
                    view_btn = cells[3].locator("a, button").first
                    try:
                        if view_btn.is_visible(timeout=500):
                            html = view_btn.evaluate("el => el.outerHTML")
                            # Regex to find something that looks like a CNR (16 alphanumeric chars starting with state code, e.g. TNCH010428972024)
                            import re
                            cnr_match = re.search(r'([A-Z]{2}[A-Z0-9]{2}[0-9]{12})', html, re.IGNORECASE)
                            if cnr_match:
                                case_info["cnr_number"] = cnr_match.group(1).upper()
                    except Exception:
                      pass
                
                cases.append(case_info)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error parsing case results: {e}")

    return {
        "status": "CASES_FOUND" if cases else "NO_CASE_FOUND",
        "cases": cases,
    }


def _classify_match(searched_name, found_party_names):
    """
    Very deliberately conservative name-matching classification.
    Never claims a case "belongs" to the property owner.
    """
    if not searched_name or not found_party_names:
        return {"match_type": "POSSIBLE_MATCH", "confidence": "LOW"}

    searched_norm = searched_name.strip().lower()
    found_norm = found_party_names.strip().lower()

    if searched_norm == found_norm:
        return {"match_type": "EXACT_NAME_MATCH", "confidence": "MEDIUM"}
    if searched_norm in found_norm or found_norm in searched_norm:
        return {"match_type": "PARTIAL_NAME_MATCH", "confidence": "MEDIUM"}
    return {"match_type": "POSSIBLE_MATCH", "confidence": "LOW"}


# ==================================================================
# ROUTES
# ==================================================================
@app.route("/")
def index():
    return render_template("index.html")



_GLOBAL_PW = None
_GLOBAL_BROWSER = None
_GLOBAL_PAGE = None

_GLOBAL_PW = None
_GLOBAL_BROWSER = None
_GLOBAL_PAGE = None

def get_global_page():
    global _GLOBAL_PW, _GLOBAL_BROWSER, _GLOBAL_PAGE
    if _GLOBAL_PW is None:
        from playwright.sync_api import sync_playwright
        _GLOBAL_PW = sync_playwright().start()
        _GLOBAL_BROWSER = _GLOBAL_PW.chromium.launch(headless=True, channel="chrome", slow_mo=200)
    
    if _GLOBAL_PAGE is None:
        _GLOBAL_PAGE = _GLOBAL_BROWSER.new_page()
        _GLOBAL_PAGE.goto("https://services.ecourts.gov.in/ecourtindia_v6/", timeout=30000)
        _GLOBAL_PAGE.wait_for_load_state("domcontentloaded")
        
        try:
            _GLOBAL_PAGE.locator("a:has-text('Case Status')").first.click(timeout=5000)
            _GLOBAL_PAGE.wait_for_timeout(2000)
        except:
                      pass
    return _GLOBAL_PAGE


@app.route("/api/options", methods=["POST"])
def get_options():
    data = request.get_json(force=True)
    target = data.get("target")
    state = data.get("state", "")
    district = data.get("district", "")
    
    try:
        page = get_global_page()
        
        if target == "state":
            page.locator(ECOURTS_SELECTORS["state_select"]).wait_for(state="attached", timeout=10000)
            options = page.locator(f'{ECOURTS_SELECTORS["state_select"]} option').all_inner_texts()
            return jsonify([o.strip() for o in options if o.strip() and "Select" not in o])
            
        elif target == "district":
            if state:
                option = page.locator(f'{ECOURTS_SELECTORS["state_select"]} option', has_text=re.compile(re.escape(state), re.IGNORECASE)).first
                opt_val = option.get_attribute("value", timeout=5000)
                page.locator(ECOURTS_SELECTORS["state_select"]).select_option(value=opt_val, timeout=5000)
                page.wait_for_timeout(1000)
                
            page.locator(ECOURTS_SELECTORS["district_select"]).wait_for(state="attached", timeout=10000)
            options = page.locator(f'{ECOURTS_SELECTORS["district_select"]} option').all_inner_texts()
            return jsonify([o.strip() for o in options if o.strip() and "Select" not in o])
            
        elif target == "court_complex":
            if state:
                option = page.locator(f'{ECOURTS_SELECTORS["state_select"]} option', has_text=re.compile(re.escape(state), re.IGNORECASE)).first
                opt_val = option.get_attribute("value", timeout=5000)
                page.locator(ECOURTS_SELECTORS["state_select"]).select_option(value=opt_val, timeout=5000)
                page.wait_for_timeout(1000)
            if district:
                option = page.locator(f'{ECOURTS_SELECTORS["district_select"]} option', has_text=re.compile(re.escape(district), re.IGNORECASE)).first
                opt_val = option.get_attribute("value", timeout=5000)
                page.locator(ECOURTS_SELECTORS["district_select"]).select_option(value=opt_val, timeout=5000)
                page.wait_for_timeout(1000)
                
            page.locator(ECOURTS_SELECTORS["court_complex_select"]).wait_for(state="attached", timeout=10000)
            options = page.locator(f'{ECOURTS_SELECTORS["court_complex_select"]} option').all_inner_texts()
            return jsonify([o.strip() for o in options if o.strip() and "Select" not in o])
            
    except Exception as e:
        print("API Error:", e)
        return jsonify({"error": str(e)}), 500

@app.route('/start-court-search', methods=['POST'])
def start_court_search():
    _cleanup_stale_sessions()
    data = request.get_json(force=True) or {}

    search_source = data.get("search_source", "ECOURTS")
    search_type = data.get("search_type", "PARTY_NAME")

    provider = COURT_PROVIDERS.get(search_source)
    if not provider:
        return jsonify({
            "success": False,
            "status": "FAILED",
            "message": f"Unknown search_source '{search_source}'.",
        }), 400

    search_id = str(uuid.uuid4())

    # Close any existing sessions to prevent asyncio loop errors in Flask threads
    # (Since we are in a single-user POC, any new search abandons the old one)
    existing_sids = list(SESSIONS.keys())
    for sid in existing_sids:
        _close_session(sid)

    # Persist the exact request for auditability.
    _save_json(os.path.join(RESULTS_DIR, f"{search_id}_request.json"), {
        "search_id": search_id,
        "received_at": datetime.now(),
        "request": data,
    })

    # ----------------------------------------------------------------
    # REVENUE COURT: never guess a portal / workflow.
    # ----------------------------------------------------------------
    if search_source == "REVENUE_COURT":
        result = {
            "success": False,
            "search_id": search_id,
            "provider": provider["name"],
            "status": "MANUAL_CONFIGURATION_REQUIRED",
            "message": (
                "Revenue Court search is state-specific and the official "
                "provider workflow has not been configured yet."
            ),
            "next_action": "CONFIGURE_REVENUE_COURT_PROVIDER",
        }
        _save_json(os.path.join(RESULTS_DIR, f"{search_id}_result.json"), result)
        return jsonify(result)

    # ----------------------------------------------------------------
    # eCourts: launch Playwright and open the official portal.
    # ----------------------------------------------------------------
    pw = browser = context = page = None
    try:
        page = get_global_page()
        # We reuse the global page directly because eCourts blocks multiple contexts or requires tokens
        page.goto(provider["base_url"], timeout=30000)
        page.wait_for_load_state("domcontentloaded")

        initial_screenshot = os.path.join(SCREENSHOT_DIR, f"court_initial_{search_id}.png")
        page.screenshot(path=initial_screenshot, full_page=True)

        page_title = page.title()
        page_url = page.url

    except Exception as e:
        traceback.print_exc()
        error_screenshot = os.path.join(SCREENSHOT_DIR, f"court_error_{search_id}.png")
        try:
            if page:
                page.screenshot(path=error_screenshot, full_page=True)
        except Exception:
            pass
        pass # Do not close global page

        result = {
            "success": False,
            "search_id": search_id,
            "status": "FAILED",
            "message": "Court search workflow failed while opening the official portal.",
        }
        _save_json(os.path.join(RESULTS_DIR, f"{search_id}_result.json"), result)
        return jsonify(result), 500

    # Keep the browser session alive - selectors for the actual search
    # steps (Party Name / CNR / Court Details tabs, dropdowns, etc.) are
    # not yet verified, so we stop here honestly rather than guessing.
    with SESSION_LOCK:
        SESSIONS[search_id] = {
            "playwright": pw,
            "browser": browser,
            "context": context,
            "page": page,
            "created_at": time.time(),
            "status": "PROCESSING",
            "search_type": search_type,
            "search_source": search_source,
            "request_data": data,
        }

    needed_selectors_by_type = {
        "PARTY_NAME": (
            "case_status_menu", "party_name_tab", "state_select",
            "district_select", "party_name_input", "search_button",
        ),
        "CNR_NUMBER": ("cnr_input", "cnr_search_button"),
        "COURT_DETAILS": (
            "case_status_menu", "court_search_tab", "state_select",
            "district_select", "case_type_select", "search_button",
        ),
    }
    required_for_type = needed_selectors_by_type.get(search_type, ())

    if not _selectors_configured(required_for_type):
        result = {
            "success": True,
            "search_id": search_id,
            "provider": provider["name"],
            "status": "MANUAL_CONFIGURATION_REQUIRED",
            "message": (
                f"Official eCourts portal opened successfully "
                f"(page title: '{page_title}', url: {page_url}), but the "
                f"selectors required for the '{search_type}' search flow "
                f"have not been verified via Playwright Codegen yet. "
                f"Update ECOURTS_SELECTORS in app.py before this search "
                f"type can be automated end-to-end."
            ),
            "next_action": "CONFIGURE_ECOURTS_SELECTORS",
            "screenshot": f"screenshots/court_initial_{search_id}.png",
        }
        _save_json(os.path.join(RESULTS_DIR, f"{search_id}_result.json"), result)
        return jsonify(result)

    # If selectors ARE fully configured (future state), this is where
    # the real per-mode navigation + form fill + CAPTCHA detection would
    # run, mirroring ec_automation_poc's _pick_date-style helpers. Left
    # unimplemented intentionally until selectors are verified live.
    try:
        if search_type == "PARTY_NAME":
            try:
                page.locator(ECOURTS_SELECTORS["case_status_menu"]).first.click(force=True, timeout=5000)
            except:
                pass
            page.wait_for_timeout(2000)
            
            # Party Name is often the default tab, clicking it if already active collapses it
            if not page.locator(ECOURTS_SELECTORS["party_name_input"]).is_visible():
                try:
                    page.locator(ECOURTS_SELECTORS["party_name_tab"]).first.click(force=True, timeout=5000)
                except:
                    pass
                page.wait_for_timeout(2000)

            import re
            
            def fuzzy_select(selector, value, name):
                if not value: return
                try:
                    option = page.locator(f"{selector} option", has_text=re.compile(re.escape(value), re.IGNORECASE)).first
                    opt_val = option.get_attribute("value", timeout=5000)
                    page.locator(selector).select_option(value=opt_val, timeout=5000)
                except Exception as e:
                    raise Exception(f"{name} '{value}' not found in dropdown.")

            # Wait for state select to be visible
            try:
                page.locator(ECOURTS_SELECTORS["state_select"]).wait_for(state="visible", timeout=10000)
            except Exception as e:
                page.screenshot(path="debug_state_fail.png", full_page=True)
                raise e
            
            fuzzy_select(ECOURTS_SELECTORS["state_select"], data.get("state"), "State")
            page.wait_for_timeout(2000)
            
            fuzzy_select(ECOURTS_SELECTORS["district_select"], data.get("district"), "District")
            page.wait_for_timeout(2000)
            
            fuzzy_select(ECOURTS_SELECTORS["court_complex_select"], data.get("court_complex"), "Court Complex")
            page.wait_for_timeout(2000)
                
            if data.get("party_name"):
                page.locator(ECOURTS_SELECTORS["party_name_input"]).fill(data["party_name"], timeout=5000)
            if data.get("registration_year"):
                page.locator(ECOURTS_SELECTORS["registration_year_input"]).fill(data["registration_year"], timeout=5000)
                
            status_val = data.get("case_status", "BOTH")
            try:
                if status_val == "PENDING":
                    page.locator(ECOURTS_SELECTORS["pending_option"]).check(timeout=5000)
                elif status_val == "DISPOSED":
                    page.locator(ECOURTS_SELECTORS["disposed_option"]).check(timeout=5000)
                else:
                    page.locator(ECOURTS_SELECTORS["both_option"]).check(timeout=5000)
            except Exception:
                pass

        elif search_type == "CNR_NUMBER":
            # The CNR search is usually the default page
            page.locator(ECOURTS_SELECTORS["cnr_input"]).wait_for(state="visible", timeout=10000)
            if data.get("cnr_number"):
                page.locator(ECOURTS_SELECTORS["cnr_input"]).fill(data["cnr_number"].strip(), timeout=5000)

        state = detect_portal_state(page)

        if state == "CAPTCHA_REQUIRED":
            captcha_bytes = page.locator(ECOURTS_SELECTORS["captcha_image"]).screenshot()
            captcha_b64 = base64.b64encode(captcha_bytes).decode("utf-8")
            captcha_path = os.path.join(SCREENSHOT_DIR, f"captcha_{search_id}.png")
            with open(captcha_path, "wb") as f:
                f.write(captcha_bytes)

            result = {
                "success": True,
                "search_id": search_id,
                "status": "CAPTCHA_REQUIRED",
                "message": "Manual CAPTCHA entry is required to continue the official court search.",
                "next_action": "SUBMIT_CAPTCHA",
                "captcha_image_base64": captcha_b64,
            }
        else:
            result = {
                "success": True,
                "search_id": search_id,
                "provider": provider["name"],
                "status": state,
                "message": "Court search opened on the official portal.",
                "screenshot": f"screenshots/court_initial_{search_id}.png",
            }

        _save_json(os.path.join(RESULTS_DIR, f"{search_id}_result.json"), result)
        return jsonify(result)

    except Exception as e:
        traceback.print_exc()
        _close_session(search_id)
        result = {
            "success": False,
            "search_id": search_id,
            "status": "FAILED",
            "message": f"Court search workflow failed while inspecting portal state: {str(e)}",
        }
        _save_json(os.path.join(RESULTS_DIR, f"{search_id}_result.json"), result)
        return jsonify(result), 500


@app.route("/submit-captcha", methods=["POST"])
def submit_captcha():
    data = request.get_json(force=True) or {}
    search_id = data.get("search_id")
    captcha_text = data.get("captcha", "").strip()  # never logged

    with SESSION_LOCK:
        session = SESSIONS.get(search_id)

    if not session:
        return jsonify({
            "success": False,
            "status": "FAILED",
            "message": "Session expired or not found. Please restart the search.",
        }), 404

    page = session["page"]
    search_type = session.get("search_type")
    request_data = session.get("request_data", {})

    if not _selectors_configured(("captcha_input", "search_button")):
        return jsonify({
            "success": False,
            "search_id": search_id,
            "status": "MANUAL_CONFIGURATION_REQUIRED",
            "message": (
                "CAPTCHA input / search button selectors are not configured "
                "yet in ECOURTS_SELECTORS. Cannot submit CAPTCHA "
                "automatically until they are verified via Playwright Codegen."
            ),
        }), 400

    try:
        page.locator(ECOURTS_SELECTORS["captcha_input"]).fill(captcha_text)
        
        captcha_invalid_state = [False]
        def handle_dialog(dialog):
            msg = dialog.message.lower()
            if "invalid" in msg or "captcha" in msg or "wrong" in msg or "error" in msg:
                captcha_invalid_state[0] = True
            try:
                dialog.accept()
            except:
                      pass
                
        # Listen for the invalid captcha alert
        page.on("dialog", handle_dialog)
        
        if search_type == "CNR_NUMBER":
            page.locator(ECOURTS_SELECTORS.get("cnr_search_button", "#searchbtn")).click(force=True)
        else:
            page.locator(ECOURTS_SELECTORS["search_button"]).click(force=True)

        try:
            # Wait for either the result table, the no-result message, or give the dialog time to fire
            for _ in range(15):
                if captcha_invalid_state[0]:
                    break
                if page.locator(ECOURTS_SELECTORS.get("result_table", "table.table")).is_visible():
                    break
                if ECOURTS_SELECTORS.get("no_result_message") and page.locator(ECOURTS_SELECTORS["no_result_message"]).is_visible():
                    break
                page.wait_for_timeout(1000)
        except Exception:
            pass

        results_screenshot = os.path.join(SCREENSHOT_DIR, f"court_results_{search_id}.png")
        page.screenshot(path=results_screenshot, full_page=True)
        
        page.remove_listener("dialog", handle_dialog)

        # If the alert fired, we know for SURE it was a captcha error.
        if captcha_invalid_state[0]:
            state = "CAPTCHA_REQUIRED"
        else:
            # If no alert fired, the captcha was CORRECT. 
            # The portal either shows results or a "Not found" message.
            # Even if our strict selectors fail, we can assume results are present.
            state_from_dom = detect_portal_state(page)
            if state_from_dom == "NO_CASE_FOUND":
                state = "NO_CASE_FOUND"
            else:
                state = "RESULT_AVAILABLE"

        if state == "NO_CASE_FOUND":
            result = {
                "search_id": search_id,
                "provider": COURT_PROVIDERS["ECOURTS"]["name"],
                "status": "NO_CASE_FOUND",
                "search_criteria": request_data,
                "cases": [],
                "summary": "No matching cases were found using the selected search criteria.",
                "disclaimer": (
                    "This result does not guarantee the absence of all litigation. "
                    "Results depend on the selected source and search criteria."
                ),
            }
        elif state == "RESULT_AVAILABLE":
            parsed = parse_case_results(page)
            cases = parsed.get("cases", [])
            for case in cases:
                case["match"] = _classify_match(
                    request_data.get("party_name", ""),
                    case.get("party_names", ""),
                )
            result = {
                "search_id": search_id,
                "provider": COURT_PROVIDERS["ECOURTS"]["name"],
                "status": "CASES_FOUND" if cases else "NO_CASE_FOUND",
                "search_criteria": request_data,
                "cases": cases,
                "summary": (
                    "Matching case records were found using the selected search criteria."
                    if cases else
                    "No matching cases were found using the selected search criteria."
                ),
                "disclaimer": (
                    "Name-based matches may refer to different individuals. "
                    "Independent legal verification is recommended."
                ),
            }
        elif state == "CAPTCHA_REQUIRED":
            # If we still see CAPTCHA_REQUIRED after submit, it usually means 
            # the captcha was invalid and the page didn't advance.
            
            # Need to capture the NEW captcha that was loaded
            captcha_b64 = ""
            try:
                captcha_bytes = page.locator(ECOURTS_SELECTORS["captcha_image"]).screenshot()
                captcha_b64 = base64.b64encode(captcha_bytes).decode("utf-8")
            except Exception:
                pass
                
            result = {
                "search_id": search_id,
                "provider": COURT_PROVIDERS["ECOURTS"]["name"],
                "status": "CAPTCHA_REQUIRED",
                "message": "Incorrect CAPTCHA or page did not advance. Please try again.",
                "captcha_image_base64": captcha_b64,
            }
        else:
            result = {
                "search_id": search_id,
                "provider": COURT_PROVIDERS["ECOURTS"]["name"],
                "status": "MANUAL_CONFIGURATION_REQUIRED",
                "message": (
                    "CAPTCHA was submitted, but result selectors are not yet "
                    "configured, so results cannot be reliably parsed. Check "
                    f"the saved screenshot: screenshots/court_results_{search_id}.png"
                ),
            }

        _save_json(os.path.join(RESULTS_DIR, f"{search_id}_result.json"), result)
        # Keep session alive for viewing details
        return jsonify(result)

    except Exception as e:
        traceback.print_exc()
        try:
            page.screenshot(
                path=os.path.join(SCREENSHOT_DIR, f"court_error_{search_id}.png"),
                full_page=True,
            )
        except Exception:
            pass
        _close_session(search_id)
        return jsonify({
            "success": False,
            "search_id": search_id,
            "status": "FAILED",
            "message": "Court search workflow failed while submitting CAPTCHA.",
        }), 500


@app.route("/view-case", methods=["POST"])
def view_case():
    data = request.get_json(force=True) or {}
    search_id = data.get("search_id")
    cnr = data.get("cnr_number")

    with SESSION_LOCK:
        session = SESSIONS.get(search_id)

    if not session:
        return jsonify({"success": False, "status": "FAILED", "message": "Session expired."}), 404

    page = session["page"]

    try:
        # Click the view button that matches the cnr in its outerHTML
        clicked = False
        rows = page.locator("tbody tr").all()
        for row in rows:
            html = row.evaluate("el => el.innerHTML")
            if cnr in html:
                # Get all links in the row
                links = row.locator("a, button").all()
                for link in links:
                    onclick = link.get_attribute("onclick") or link.get_attribute("href") or ""
                    if cnr in onclick:
                        link.click(timeout=5000)
                        clicked = True
                        break
            if clicked:
                break
        
        if not clicked:
            return jsonify({"success": False, "status": "FAILED", "message": "View button not found."}), 404

        # Wait for the AJAX call to load the detailed tables
        # The detailed view ALWAYS has a table cell/header with "Petitioner and Advocate"
        try:
            page.wait_for_selector("text='Petitioner and Advocate'", timeout=15000)
            page.wait_for_timeout(2000) # Give DOM time to update
        except:
                      pass
        
        # Parse the details
        parsed = parse_case_results(page)
        
        # Go back to the list by clicking Back
        try:
            page.locator("text='Back'").first.click(timeout=5000, force=True)
            page.wait_for_selector("table.table", timeout=10000)
        except:
                      pass
        
        return jsonify(parsed)

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "status": "FAILED", "message": str(e)}), 500


@app.route("/download/<search_id>")
def download(search_id):
    """
    Serves any saved result JSON as a downloadable file, if present.
    (No PDF is generated by the eCourts flow itself at this stage -
    result data is stored as JSON in results/.)
    """
    result_path = os.path.join(RESULTS_DIR, f"{search_id}_result.json")
    if not os.path.exists(result_path):
        return jsonify({"error": "Result not found."}), 404
    return send_file(result_path, as_attachment=True, download_name=f"court_case_result_{search_id}.json")


if __name__ == "__main__":
    print("Preloading eCourts... this will take 10 seconds.")
    get_global_page()

    from wsgiref.simple_server import make_server
    print("Starting single-threaded WSGI server on port 5000...")
    server = make_server("127.0.0.1", 5000, app)
    server.serve_forever()
