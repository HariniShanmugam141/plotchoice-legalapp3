# Court Case Search POC

## Purpose

Search available official court records related to a property owner or
party, using one of three modes:

- **Party Name**
- **CNR Number**
- **Court Details**

This is a due-diligence aid, not a legal opinion. The application never
states that a property "has no legal cases." It only ever reports:

> "No matching cases were found using the selected search criteria."

and always shows:

> "Search results are based on the selected official source and search
> criteria. A name match does not necessarily mean the case belongs to
> the same property owner. Independent legal verification is recommended."

## Architecture

Follows the same simple pattern as `ec_automation_poc` / `cersai_poc`:

```
User
  ↓
Local Flask Application (single form, no React, no microservices)
  ↓
Playwright (visible browser)
  ↓
Official eCourts Services portal
  ↓
Select Search Mode (Party Name / CNR / Court Details)
  ↓
Enter search details
  ↓
Manual CAPTCHA (human-in-the-loop, never solved by the app)
  ↓
Search
  ↓
Case results parsed only from verified selectors
  ↓
Displayed to the user with match-confidence + legal disclaimer
```

## Official source

Primary provider: **eCourts Services**

- Portal: https://services.ecourts.gov.in/ecourtindia_v6/
- Case Status search: https://services.ecourts.gov.in/ecourtindia_v6/casestatus/

Configured in `app.py` as:

```python
COURT_PROVIDERS = {
    "ECOURTS": {
        "name": "eCourts Services",
        "base_url": "https://services.ecourts.gov.in/ecourtindia_v6/"
    },
    "REVENUE_COURT": {
        "name": "Revenue Court",
        "base_url": None
    }
}
```

### Revenue Court

Revenue Court record-keeping is state-specific; there is no single
official nationwide portal or workflow. Selecting "Revenue Court" in the
UI will always return:

```json
{"status": "MANUAL_CONFIGURATION_REQUIRED"}
```

until a specific state portal and workflow are added and implemented
explicitly. **No Revenue Court URL is fabricated anywhere in this code.**

## Current state of this POC

This POC **opens the real eCourts portal with Playwright and takes a
screenshot**, but it does **not** yet click through Party Name / CNR /
Court Details tabs, fill dropdowns, or parse a results table — because
none of those selectors have been captured yet from a live Playwright
Codegen recording against the current eCourts DOM (which, like TNREGINET,
can be entirely in a regional language and use non-obvious internal
value codes).

Every relevant selector lives in one place, all set to `None`:

```python
ECOURTS_SELECTORS = {
    "case_status_menu": None,
    "party_name_tab": None,
    "cnr_search_tab": None,
    "court_search_tab": None,
    "state_select": None,
    "district_select": None,
    "court_complex_select": None,
    "establishment_select": None,
    "party_name_input": None,
    "registration_year_input": None,
    "pending_option": None,
    "disposed_option": None,
    "both_option": None,
    "cnr_input": None,
    "case_type_select": None,
    "case_number_input": None,
    "captcha_image": None,
    "captcha_input": None,
    "search_button": None,
    "result_table": None,
    "result_container": None,
    "no_result_message": None,
    "case_link": None,
}
```

Until these are filled in, `/start-court-search` will:

1. Successfully launch Playwright.
2. Open the real eCourts portal.
3. Save a real screenshot to `screenshots/court_initial_<search_id>.png`.
4. Keep the browser session alive.
5. Return `"status": "MANUAL_CONFIGURATION_REQUIRED"` explaining exactly
   which selectors are still needed for the requested search type,
   instead of pretending to search or fabricating results.

This mirrors the honesty requirement of the reference `ec_automation_poc`
(which also documents that it only has real value codes for one
Zone/District/SRO/Village combination captured via Codegen).

## Wiring up a real search mode

1. Run:

   ```
   playwright codegen https://services.ecourts.gov.in/ecourtindia_v6/
   ```

2. Manually click through to **Case Status**.

3. Inspect and record selectors for:
   - Party Name Search
   - CNR Search
   - Court Details Search

4. Copy the exact selector / role / label text Codegen prints for each
   entry in `ECOURTS_SELECTORS`.

5. Replace the matching `None` values in `app.py`.

6. Implement the corresponding step-by-step navigation in
   `start_court_search()` / `submit_captcha()` using
   `page.get_by_role(...)` / `page.get_by_label(...)`, the same way
   `ec_automation_poc` does it with its `_pick_date()` helper.

7. Fill in `parse_case_results()` to read the verified result table
   structure — never guess column meaning.

**Never guess selectors. Never guess hidden APIs. Never invent a
Revenue Court URL.**

## CAPTCHA policy

- The app **never** solves, OCRs, or bypasses CAPTCHA.
- When a CAPTCHA is detected (once `captcha_image` selector is
  configured), it is screenshotted and shown to the user in the browser
  UI for manual entry.
- The Playwright browser session is kept alive server-side
  (in-memory, keyed by `search_id`) until the user submits the CAPTCHA.
- CAPTCHA values are **never logged**.

## Match classification

Because a name match does not prove identity, every case result is
classified rather than asserted:

- `EXACT_NAME_MATCH`
- `PARTIAL_NAME_MATCH`
- `POSSIBLE_MATCH`

Each with a `confidence` of `LOW` / `MEDIUM` / `HIGH`, alongside the
disclaimer:

> "A matching name does not necessarily confirm that the case belongs to
> the same individual associated with the property."

## Folder structure

```
court_case_poc/
│
├── static/
│   ├── style.css
│   └── script.js
│
├── templates/
│   └── index.html
│
├── screenshots/     # portal / CAPTCHA / result screenshots per search_id
├── results/         # <search_id>_request.json / <search_id>_result.json
├── downloads/        # reserved for any future downloadable artifacts
├── app.py
├── requirements.txt
├── .env.example
└── README.md
```

## Installation

```bash
cd court_case_poc
pip install -r requirements.txt
playwright install chromium
```

## Running

```bash
python app.py
```

Then open:

```
http://127.0.0.1:5000
```

## API summary

| Method | Route                  | Purpose                                              |
|--------|-------------------------|-------------------------------------------------------|
| GET    | `/`                     | Serves the search form                                |
| POST   | `/start-court-search`   | Launches Playwright, opens eCourts, returns status    |
| POST   | `/submit-captcha`       | Submits CAPTCHA on the same open session              |
| GET    | `/download/<search_id>` | Downloads the saved result JSON for a search          |

### `/start-court-search` request body

```json
{
    "search_source": "ECOURTS",
    "search_type": "PARTY_NAME",
    "party_name": "Rajesh Kumar",
    "state": "Tamil Nadu",
    "district": "Chennai",
    "court_complex": "",
    "registration_year": "2024",
    "case_status": "BOTH"
}
```

### Normalized "cases found" response shape

```json
{
    "search_id": "...",
    "provider": "eCourts Services",
    "status": "CASES_FOUND",
    "search_criteria": { "...": "..." },
    "cases": [
        {
            "cnr_number": "...",
            "case_number": "...",
            "case_type": "...",
            "court_name": "...",
            "party_names": "...",
            "filing_date": "...",
            "next_hearing_date": "...",
            "case_status": "...",
            "match": { "match_type": "POSSIBLE_MATCH", "confidence": "LOW" }
        }
    ],
    "summary": "Matching case records were found using the selected search criteria.",
    "disclaimer": "Name-based matches may refer to different individuals. Independent legal verification is recommended."
}
```

### Normalized "no cases found" response shape

```json
{
    "search_id": "...",
    "provider": "eCourts Services",
    "status": "NO_CASE_FOUND",
    "cases": [],
    "summary": "No matching cases were found using the selected search criteria.",
    "disclaimer": "This result does not guarantee the absence of all litigation. Results depend on the selected source and search criteria."
}
```

## Guarantees this POC keeps

1. Never fabricates court cases.
2. Never bypasses or solves CAPTCHA.
3. Never makes a legal conclusion ("no cases" is never phrased as "clear
   title" or similar).
4. Never invents a Revenue Court URL or workflow.
5. Never guesses eCourts selectors — every automated step is backed by a
   selector explicitly verified via Playwright Codegen, or the app
   reports `MANUAL_CONFIGURATION_REQUIRED` instead.
