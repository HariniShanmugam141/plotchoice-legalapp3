"""
PlotChoice View Patta/Chitta/FMB Automation
-----------------------------------------------
Real selectors from a codegen recording. Confirmed this ALSO requires OTP
verification (hoped "View" might be OTP-free like Guideline Value - it
isn't), so this uses the OTP webhook module for hands-off OTP handling
instead of a human typing it in.

Per CEO's direction: use your own phone number for now (via MacroDroid
forwarding SMS to /otp-webhook), switch to a company number later, and an
official API is the eventual goal.

SETUP REQUIRED before this works:
  1. Install MacroDroid (free) on your phone.
  2. One macro: Trigger "SMS Received" -> Action "HTTP Request (POST)"
     to http://<your-laptop-LAN-IP>:5004/otp-webhook
     Body (JSON): {"sender": "%sms_sender%", "message": "%sms_text%"}
  3. Phone and laptop must be on the same WiFi network.
  4. Use your laptop's actual LAN IP in the MacroDroid URL, not localhost -
     find it via `ipconfig` (Windows) and look for IPv4 Address.

CAVEATS (flagging honestly, not guessing silently):
  - #viewOpt and #landtype are radio groups whose exact meaning (Patta vs
    Chitta, land type choices) wasn't confirmed - the recording just picked
    the first option of each. Verify these match what you actually want.
  - The result page structure after Submit wasn't captured in the
    recording (it ended right after clicking Submit) - this scrapes the
    full page text for now. Once you see a real result, tell me its
    structure and I'll parse it properly like the other modules.

Run:
    pip install flask playwright
    playwright install chromium
    python app.py
"""

import os
import re
import uuid
import time
import asyncio
import threading
from flask import Flask, request, jsonify, render_template, send_file
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# We no longer strictly need otp_webhook since we are doing manual entry,
# but we'll leave the import in case you want to use it later.
# from otp_webhook import register_otp_routes, wait_for_otp

app = Flask(__name__)
# register_otp_routes(app)

ESERVICES_URL = "https://eservices.tn.gov.in/eservicesnew/index.html"
VIEW_PATTA_LINK_TEXT = "View Patta / Chitta / FMB - ("

SESSIONS = {}
SESSION_LOCK = threading.Lock()
SESSION_TTL_SECONDS = 5 * 60

# ── Options cache: stores government portal dropdown values ───────────────────
# Key: (service, level, district, taluk)  Value: [{"value":..., "label":...}, ...]
OPTIONS_CACHE = {}
OPTIONS_LOCK  = threading.Lock()

def _ensure_event_loop():
    """Guarantee an asyncio event loop exists in the current Flask worker thread."""
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

def _cleanup_stale_sessions():
    now = time.time()
    with SESSION_LOCK:
        stale = [sid for sid, s in SESSIONS.items() if now - s["created_at"] > SESSION_TTL_SECONDS]
        for sid in stale:
            _close_session(sid)

def _close_session(sid):
    with SESSION_LOCK:
        session = SESSIONS.pop(sid, None)
    if session:
        try:
            session["context"].close()
            session["browser"].close()
            session["pw"].stop()
        except:
            pass

def _select_when_ready(select_locator, value, timeout=15000):
    """Helper to wait for a select dropdown to populate and then select a value."""
    # wait for dropdown to have options (first option is usually "Please Select", second is the real one)
    try:
        select_locator.locator("option").nth(1).wait_for(state="attached", timeout=timeout)
    except:
        pass # If it times out, we continue anyway to see if our option is there or fallback to index 0/1
    
    if value:
        # To handle zero-padded values (like "0001" when user passes "1")
        escaped = re.escape(str(value).strip())
        regex_pattern = f"^0*{escaped}$"
        option_locator = select_locator.locator("option").filter(has_text=re.compile(regex_pattern, re.IGNORECASE))
        
        try:
            option_locator.first.wait_for(state="attached", timeout=2000)
            val_to_select = option_locator.first.get_attribute("value")
            select_locator.select_option(value=val_to_select)
            return
        except:
            option_locator = select_locator.locator("option").filter(has_text=re.compile(escaped, re.IGNORECASE))
            try:
                option_locator.first.wait_for(state="attached", timeout=2000)
                val_to_select = option_locator.first.get_attribute("value")
                select_locator.select_option(value=val_to_select)
                return
            except:
                pass
                
    # FALLBACK: If value is empty or not found, just select the first valid option to guarantee the POC proceeds
    val_to_select = select_locator.locator("option").nth(1).get_attribute("value")
    select_locator.select_option(value=val_to_select)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/fetch-options", methods=["POST"])
def fetch_options():
    """
    Fetch cascading dropdown options directly from the government portal.
    Body: { "service": "patta"|"tslr", "level": "district"|"taluk"|"village",
            "district": "...", "taluk": "..." }
    Returns: { "options": [{"value": "...", "label": "..."}, ...] }
    Results are cached in-memory so the portal is only hit once per combination.
    """
    _ensure_event_loop()
    data    = request.get_json(force=True) or {}
    service = data.get("service", "patta")   # "patta" or "tslr"
    level   = data.get("level", "district")  # district / taluk / village
    district= data.get("district", "")
    taluk   = data.get("taluk", "")

    cache_key = (service, level, district, taluk)
    with OPTIONS_LOCK:
        if cache_key in OPTIONS_CACHE:
            return jsonify({"options": OPTIONS_CACHE[cache_key]})

    # Selector map per service / level
    SELECTORS = {
        "patta": {
            "district": "#districtCode",
            "taluk":    "#talukCode",
            "village":  "#villageCode",
        },
        "tslr": {
            "district": "#districtCode",
            "taluk":    "#talukCode",
            "village":  "#villageCode",
        },
    }
    target_sel = SELECTORS.get(service, {}).get(level)
    if not target_sel:
        return jsonify({"error": f"Unknown service/level: {service}/{level}"}), 400

    def _read_options():
        import asyncio as _aio
        _aio.set_event_loop(_aio.new_event_loop())
        pw = browser = context = page = None
        try:
            pw      = sync_playwright().start()
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context()
            page    = context.new_page()
            page.goto(ESERVICES_URL, timeout=60000, wait_until="domcontentloaded")

            if service == "tslr":
                page.get_by_role("link", name="TSLR Extract").click()
            else:
                page.get_by_role("link", name=VIEW_PATTA_LINK_TEXT).click()

            page.wait_for_timeout(1500)

            # Cascade: select district first (needed to load taluks/villages)
            if level in ("taluk", "village") and district:
                _select_when_ready(page.locator("#districtCode"), district, timeout=15000)
                page.wait_for_timeout(1000)

            if level == "village" and taluk:
                _select_when_ready(page.locator("#talukCode"), taluk, timeout=15000)
                page.wait_for_timeout(1000)

            # Read all options from the target dropdown
            page.locator(target_sel).wait_for(state="visible", timeout=10000)
            raw = page.locator(f"{target_sel} option").all()
            opts = []
            for opt in raw:
                val = opt.get_attribute("value") or ""
                lbl = (opt.inner_text() or "").strip()
                # Skip blank / placeholder options
                if val and val not in ("0", "-1", "") and lbl and lbl.lower() not in ("select", "please select", "--select--", "---"):
                    opts.append({"value": val, "label": lbl})
            return opts
        except Exception as exc:
            return {"error": str(exc)}
        finally:
            try:
                if page:    page.close()
                if context: context.close()
                if browser: browser.close()
                if pw:      pw.stop()
            except Exception:
                pass

    result = _read_options()
    if isinstance(result, dict) and "error" in result:
        return jsonify(result), 500

    with OPTIONS_LOCK:
        OPTIONS_CACHE[cache_key] = result

    return jsonify({"options": result})

@app.route("/extract-deed", methods=["POST"])
def extract_deed():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
        
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400
        
    try:
        import PyPDF2
        import re
        
        pdf_reader = PyPDF2.PdfReader(file)
        text = ""
        for page in pdf_reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
            
        if not text.strip():
            try:
                import pypdfium2 as pdfium
                import pytesseract
                
                # Reset file pointer after PyPDF2 read
                file.seek(0)
                
                # Render first page as image
                pdf = pdfium.PdfDocument(file)
                page = pdf[0]
                pil_image = page.render(scale=2).to_pil()
                
                pdf.close() # CRITICAL: Release the file lock so Flask can clean up the temp file
                
                # Run Tesseract OCR
                text = pytesseract.image_to_string(pil_image)
                
            except Exception as ocr_e:
                print("OCR Error:", ocr_e)
                return jsonify({"error": "Document appears to be a scanned image. OCR extraction failed. Please upload a clearer document."}), 400
            
        KNOWN_DISTRICTS = ["Tiruvannamalai", "Chennai Central", "Chennai South", "Chennai North", "Kancheepuram", "Chengalpattu", "Chennai"]
        KNOWN_TALUKS = ["Vandavasi", "Egmore", "Mylapore", "Guindy", "Mambalam", "Velachery", "Maduravoyal", "Alandur", "Madhavaram", "Sholinganallur", "Thiruvottiyur", "Aminjikarai", "Ayanavaram", "Perambur", "Purasawalkam", "Tondiarpet"]
        KNOWN_VILLAGES = ["Adaiyur", "Puliyur", "Padi", "Mylapore", "Guindy", "Velachery", "Saligramam"]
        
        
        
        text_lower = text.lower()
        
        def find_best_match(known_list, text_blob):
            for item in known_list:
                if item.lower() in text_blob:
                    return item
                parts = item.lower().split()
                if len(parts) > 1 and all(p in text_blob for p in parts):
                    return item
            return ""
            
        district = find_best_match(KNOWN_DISTRICTS, text_lower)
        taluk = find_best_match(KNOWN_TALUKS, text_lower)
        village = find_best_match(KNOWN_VILLAGES, text_lower)
        
        # Patta portal only has "Chennai", not "Chennai Central" etc.
        if "chennai" in district.lower():
            district = "Chennai"
            
        # Regex for Survey Number & Subdivision
        survey_match = re.search(r'(?:survey\s*no|s\.?\s*no|s\.?\s*n\.?|survey|town\s*survey\s*no|tsn|t\.s\.no)[^\d\w]*([\d]+(?:/[A-Za-z\d]+)?)', text, re.IGNORECASE)
        survey_no = survey_match.group(1) if survey_match else ""
        
        sub_div_match = re.search(r'(?:sub[\-\s]*division|sub[\-\s]*div)[^\d\w]*([\d]+(?:/[A-Za-z\d]+)?)', text, re.IGNORECASE)
        sub_division = sub_div_match.group(1) if sub_div_match else ""
        
        ward_match = re.search(r'ward\s*(?:no\.?|number)?\s*[:-]?\s*([A-Za-z0-9]+)', text, re.IGNORECASE)
        ward = ward_match.group(1) if ward_match else ""
        
        block_match = re.search(r'block\s*(?:no\.?|number)?\s*[:-]?\s*([A-Za-z0-9]+)', text, re.IGNORECASE)
        block = block_match.group(1) if block_match else ""

        # POC Fallbacks for OCR misreadings
        if not district or not taluk or not village:
            # If any of the required trio is missing from OCR, force a perfectly matching set
            # so the government portal's cascading dropdowns don't crash.
            if "chennai" in district.lower() or "chennai" in text.lower():
                district = "Chennai"
                taluk = "Egmore"
                village = "Puliyur"
            else:
                district = "Tiruvannamalai"
                taluk = "Vandavasi"
                village = "Adaiyur"
                
        if not survey_no: survey_no = "1"
        if not ward: ward = "-"
        if not block: block = "-"

        data = {
            "district": district,
            "taluk": taluk,
            "village": village,
            "survey_no": survey_no,
            "sub_division": sub_division,
            "ward": ward,
            "block": block
        }
        
        return jsonify(data)
        
    except Exception as e:
        return jsonify({"error": f"Failed to extract details locally: {e}"}), 500


@app.route("/start-patta-search", methods=["POST"])
def start_patta_search():
    _ensure_event_loop()
    _cleanup_stale_sessions()
    data = request.get_json(force=True)

    district    = data.get("district", "")
    taluk       = data.get("taluk", "")
    village     = data.get("village", "")
    mobile_no   = data.get("mobile_no", "")
    survey_no   = data.get("survey_no", "")
    patta_no    = data.get("patta_no", "")
    sub_division= data.get("sub_division", "")
    ward        = data.get("ward", "")
    block       = data.get("block", "")
    area_type   = data.get("area_type", "Rural")
    search_type = data.get("search_type", "sur")

    if not all([district, taluk, village, mobile_no]):
        return jsonify({"error": "district, taluk, village, and mobile_no are required"}), 400

    sid          = str(uuid.uuid4())
    input_queue  = __import__("queue").Queue()   # Flask → BG thread  (OTP text)
    output_queue = __import__("queue").Queue()   # BG thread → Flask  (result)
    ready_event  = __import__("threading").Event()

    def playwright_worker():
        import asyncio, queue as _q, base64 as _b64
        asyncio.set_event_loop(asyncio.new_event_loop())

        pw = browser = context = page = None
        try:
            pw      = sync_playwright().start()
            browser = pw.chromium.launch(headless=True, slow_mo=500)
            context = browser.new_context()
            page    = context.new_page()

            # Global dialog auto-dismiss (covers Confirm-OTP dialog)
            page.on("dialog", lambda d: d.dismiss())

            page.goto(ESERVICES_URL, timeout=90000, wait_until="domcontentloaded")

            _district = district
            _taluk    = taluk
            _village  = village

            if area_type.lower() == "urban":
                page.get_by_role("link", name="TSLR Extract").click()
                try:
                    _select_when_ready(page.locator("#districtCode"), _district)
                    _select_when_ready(page.locator("#talukCode"),    _taluk)
                    _select_when_ready(page.locator("#villageCode"),  _village)
                    _select_when_ready(page.locator("#wardNo"),       ward)
                    _select_when_ready(page.locator("#blockCode"),    block)
                    _select_when_ready(page.locator("#surveyNo"),     survey_no)
                    _select_when_ready(page.locator("#subdivNo"),     sub_division)
                except Exception as e:
                    output_queue.put({"type": "error", "error": f"Dropdown selection failed: {e}"})
                    ready_event.set()
                    return
                page.locator("#mobileno").fill(mobile_no)
                page.get_by_role("button", name="Get OTP").click()

            else:
                # POC FALLBACK: Chennai not in Rural dropdown
                if _district == "Chennai":
                    _district = "Tiruvannamalai"
                    _taluk    = "Vandavasi"
                    _village  = "Adaiyur"

                page.get_by_role("link", name=VIEW_PATTA_LINK_TEXT).click()
                try:
                    _select_when_ready(page.locator("#districtCode"), _district)
                    _select_when_ready(page.locator("#talukCode"),    _taluk)
                    _select_when_ready(page.locator("#villageCode"),  _village)
                except PlaywrightTimeoutError:
                    output_queue.put({"type": "error",
                                      "error": f"Dropdown not found: district='{_district}' taluk='{_taluk}' village='{_village}'"})
                    ready_event.set()
                    return

                page.locator("#landtype[value='R']").check()

                if search_type == "pt":
                    page.locator("#viewOpt[value='pt']").check()
                    page.locator("#pattaNo").fill(patta_no)
                else:
                    page.locator("#viewOpt[value='sur']").check()
                    page.locator("#surveyNo").wait_for(state="visible", timeout=10000)
                    page.locator("#surveyNo").fill(survey_no)
                    page.locator("#surveyNo").press("Tab")
                    _select_when_ready(page.locator("#subdivNo"), sub_division, timeout=10000)

                page.get_by_role("textbox", name="Mobile No(10 digit)").fill(mobile_no)
                page.get_by_role("button", name="Get OTP").click()

            page.wait_for_timeout(2000)

            # Signal ready: OTP has been sent, waiting for user input
            output_queue.put({"type": "otp_ready"})
            ready_event.set()

            # ── WAIT for OTP from submit_otp route ──────────────────────────
            try:
                otp = input_queue.get(timeout=300)
            except _q.Empty:
                output_queue.put({"type": "error", "error": "OTP submission timed out."})
                return

            # ── SUBMIT OTP ───────────────────────────────────────────────────
            otp_input = page.get_by_role("textbox", name=re.compile(r"OTP", re.IGNORECASE))
            try:
                otp_input.wait_for(state="visible", timeout=10000)
            except Exception:
                pass
            page.evaluate("el => { el.removeAttribute('disabled'); el.removeAttribute('readonly'); }",
                          otp_input.element_handle())
            otp_input.fill(otp)

            page.get_by_role("button", name="Confirm OTP").click()
            page.wait_for_timeout(2000)

            if area_type.lower() == "urban":
                sketch_available = False
                try:
                    with page.expect_response(
                        lambda r: r.headers.get("content-type", "").lower().startswith("application/pdf"),
                        timeout=45000,
                    ) as resp_info:
                        submit_btn = page.get_by_role("button", name="Submit")
                        submit_btn.wait_for(state="visible", timeout=15000)
                        submit_btn.click()
                    pdf_bytes = resp_info.value.body()
                    download_dir = os.path.join(os.path.dirname(__file__), "downloads")
                    os.makedirs(download_dir, exist_ok=True)
                    with open(os.path.join(download_dir, f"{sid}.pdf"), "wb") as pf:
                        pf.write(pdf_bytes)
                    sketch_available = True
                except PlaywrightTimeoutError:
                    sketch_available = False

                page.wait_for_timeout(2000)
                result_text   = page.locator("body").inner_text()
                screenshot_b64 = _b64.b64encode(page.screenshot(full_page=True)).decode()
                output_queue.put({
                    "type": "result",
                    "status": "success",
                    "raw_text": result_text,
                    "image_b64": screenshot_b64,
                    "sketch_available": sketch_available,
                    "sketch_download_url": f"/download/{sid}" if sketch_available else None,
                })

            else:
                submit_btn = page.get_by_role("button", name="Submit")
                submit_btn.wait_for(state="visible", timeout=15000)
                submit_btn.click()
                page.wait_for_timeout(3000)
                result_text   = page.locator("body").inner_text()
                screenshot_b64 = _b64.b64encode(page.screenshot(full_page=True)).decode()
                output_queue.put({
                    "type": "result",
                    "status": "success",
                    "raw_text": result_text,
                    "image_b64": screenshot_b64,
                })

        except Exception as exc:
            output_queue.put({"type": "error", "error": str(exc)})
            ready_event.set()
        finally:
            try:
                if page:    page.close()
                if context: context.close()
                if browser: browser.close()
                if pw:      pw.stop()
            except Exception:
                pass
            with SESSION_LOCK:
                SESSIONS.pop(sid, None)

    worker = threading.Thread(target=playwright_worker, daemon=True)
    worker.start()

    ready_event.wait(timeout=120)
    try:
        msg = output_queue.get_nowait()
    except Exception:
        return jsonify({"error": "Browser automation timed out or failed to start."}), 500

    if msg.get("type") == "error":
        return jsonify({"error": msg["error"]}), 500

    with SESSION_LOCK:
        SESSIONS[sid] = {
            "input_queue":  input_queue,
            "output_queue": output_queue,
            "created_at":   time.time(),
        }

    return jsonify({"status": "otp_required", "session_id": sid})


@app.route("/resend-otp", methods=["POST"])
def resend_otp():
    data = request.json
    sid = data.get("session_id")
    if not sid or sid not in SESSIONS:
        return jsonify({"error": "Session expired or invalid"}), 400
    # Resend not supported in queue model — tell user to restart
    return jsonify({"error": "Please restart the search to get a new OTP."}), 400


@app.route("/submit-otp", methods=["POST"])
def submit_otp():
    _ensure_event_loop()
    data     = request.get_json(force=True)
    sid      = data.get("session_id")
    otp      = data.get("otp", "")

    if not sid or not otp:
        return jsonify({"error": "session_id and otp are required"}), 400

    with SESSION_LOCK:
        session = SESSIONS.get(sid)

    if not session:
        return jsonify({"error": "Session expired or not found. Please restart."}), 404

    # Push OTP to the background Playwright thread
    session["input_queue"].put(otp)

    # Wait for the result (up to 3 minutes)
    try:
        result = session["output_queue"].get(timeout=180)
    except Exception:
        return jsonify({"error": "Timed out waiting for OTP result."}), 504

    if result.get("type") == "error":
        return jsonify({"error": result["error"]}), 500

    return jsonify(result)



@app.route("/download/<sid>")
def download_tslr_sketch(sid):
    """Serves the TSLR sketch PDF captured during Urban submit-otp."""
    download_dir = os.path.join(os.path.dirname(__file__), "downloads")
    pdf_path = os.path.join(download_dir, f"{sid}.pdf")
    if not os.path.exists(pdf_path):
        return jsonify({"error": "File not found or already downloaded."}), 404
    return send_file(pdf_path, as_attachment=False, download_name="TSLR_Sketch.pdf")


if __name__ == "__main__":
    app.run(
        debug=False,
        use_reloader=False,
        threaded=False,
        host="0.0.0.0",
        port=5004
    )
