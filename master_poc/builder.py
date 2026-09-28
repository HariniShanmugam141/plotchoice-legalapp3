import os
import re

def extract_functions(filepath, route_names):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    out = ""
    for route in route_names:
        pattern = r'@app\.route\("' + route + r'".*?(?=@app\.route|if __name__ ==)'
        match = re.search(pattern, content, re.DOTALL)
        if match:
            out += match.group(0) + "\n"
    return out

ec_funcs = extract_functions("../ec_automation_poc/app.py", ["/start-ec-search", "/submit-captcha", "/download/<sid>"])
ec_funcs = ec_funcs.replace('"/start-ec-search"', '"/start-ec"')
ec_funcs = ec_funcs.replace('"/submit-captcha"', '"/submit-ec-captcha"')
ec_funcs = ec_funcs.replace('def submit_captcha(', 'def submit_ec_captcha(')

patta_funcs = extract_functions("../view_patta_poc/app.py", ["/start-patta-search", "/submit-otp"])
patta_funcs = patta_funcs.replace('"/start-patta-search"', '"/start-patta"')
patta_funcs = patta_funcs.replace('"/submit-otp"', '"/submit-patta-otp"')
patta_funcs = patta_funcs.replace('def submit_otp(', 'def submit_patta_otp(')

court_funcs = extract_functions("../court_case_poc/app.py", ["/start-court-search", "/submit-captcha", "/view-case", "/download/<search_id>"])
court_funcs = court_funcs.replace('"/start-court-search"', '"/start-court"')
court_funcs = court_funcs.replace('"/submit-captcha"', '"/submit-court-captcha"')
court_funcs = court_funcs.replace('def submit_captcha(', 'def submit_court_captcha(')
court_funcs = court_funcs.replace('"/download/<search_id>"', '"/download-court/<search_id>"')
court_funcs = court_funcs.replace('def download_pdf(', 'def download_court_pdf(')

with open("app.py", "r", encoding="utf-8") as f:
    master_text = f.read().split("# --- EC ---\n")[0] # keep the clean base

with open("app.py", "w", encoding='utf-8') as f:
    f.write(master_text)
    f.write("\n# --- EC ---\n")
    f.write(ec_funcs)
    f.write("\n# --- PATTA ---\n")
    f.write(patta_funcs)
    f.write("\n# --- COURT ---\n")
    f.write(court_funcs)
    f.write("\nif __name__ == '__main__':\n    if not os.path.exists('downloads'): os.makedirs('downloads')\n    app.run(debug=True, port=5005, threaded=False)\n")
