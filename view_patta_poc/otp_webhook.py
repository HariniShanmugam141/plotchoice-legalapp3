"""
OTP Webhook Receiver
---------------------
Runs alongside the Flask app. A spare Android phone (with the company SIM)
runs MacroDroid (free tier) with one macro:

    Trigger: SMS Received
    Action:  HTTP Request (POST)
             URL: http://<your-server-ip>:5000/otp-webhook
             Body (JSON): {"sender": "%sms_sender%", "message": "%sms_text%"}

When an OTP SMS arrives on the phone, MacroDroid POSTs it here automatically.
This extracts the OTP digits and stores them keyed by phone number, so the
Playwright automation can poll for it instead of a human typing it in.

SECURITY NOTE FOR A REAL DEPLOYMENT (fine to skip for a POC on your own LAN):
Add a shared-secret header check here before trusting the payload, since
this endpoint is otherwise open to anyone who can reach your server's IP.
"""

import re
import time
import threading

from flask import request, jsonify

# In-memory store: { phone_number: {"otp": "123456", "received_at": <timestamp>} }
OTP_STORE = {}
OTP_LOCK = threading.Lock()
OTP_MAX_AGE_SECONDS = 5 * 60  # discard OTPs older than this if never claimed


def register_otp_routes(app):
    """Call this once from app.py: register_otp_routes(app)"""

    @app.route("/otp-webhook", methods=["POST"])
    def otp_webhook():
        data = request.get_json(force=True)
        sender = data.get("sender", "unknown")
        message = data.get("message", "")

        otp = _extract_otp(message)
        if not otp:
            print(f"[otp-webhook] no OTP pattern found in message from {sender}: {message!r}")
            return jsonify({"status": "ignored", "reason": "no OTP pattern matched"}), 200

        # Keyed by sender for now since we don't know the recipient number from
        # the SMS itself - if you're only ever verifying one number at a time,
        # this is fine. For multiple concurrent numbers, have MacroDroid also
        # forward "%sms_to%" (the receiving number) and key on that instead.
        with OTP_LOCK:
            OTP_STORE[sender] = {"otp": otp, "received_at": time.time()}

        print(f"[otp-webhook] stored OTP '{otp}' from {sender}")
        return jsonify({"status": "stored"}), 200


def _extract_otp(message: str) -> str | None:
    """
    Pulls a 4-8 digit OTP out of a typical OTP SMS body.
    Government/bank OTP texts almost always look like:
      "123456 is your OTP for Chitta verification. Valid for 10 minutes."
    Adjust this regex if your actual SMS format doesn't match.
    """
    match = re.search(r"\b(\d{4,8})\b", message)
    return match.group(1) if match else None


def wait_for_otp(sender_filter=None, timeout=90, poll_interval=0.2):
    """
    Call this from the Playwright flow after clicking 'Get OTP'.
    Blocks (polling) until an OTP shows up in OTP_STORE, or times out.

    sender_filter: if you know the exact sender ID the government portal's
    SMS comes from (e.g. "TN-ESERV" or similar), pass it here to avoid
    picking up an unrelated SMS. Leave None to accept the most recent OTP
    from any sender (fine for a single-purpose test phone).
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        with OTP_LOCK:
            candidates = [
                (sender, info) for sender, info in OTP_STORE.items()
                if (sender_filter is None or sender_filter in sender)
                and time.time() - info["received_at"] < OTP_MAX_AGE_SECONDS
            ]
        if candidates:
            # Most recently received matching OTP
            sender, info = max(candidates, key=lambda c: c[1]["received_at"])
            with OTP_LOCK:
                del OTP_STORE[sender]  # consume it - don't reuse a stale OTP
            return info["otp"]
        time.sleep(poll_interval)
    return None
