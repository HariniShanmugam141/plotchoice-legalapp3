import os
import re

def clean_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    out = []
    skip = False
    for line in lines:
        if line.startswith("app = Flask"): continue
        if line.startswith("if __name__ =="): 
            skip = True
            
        # Stop skipping if we hit a new route
        if skip and line.startswith("@app.route") and not "/extract-deed" in line and not "('/')" in line and not '("/")' in line:
            skip = False
            
        # Start skipping
        if "/extract-deed" in line: skip = True
        if "def index(" in line: skip = True
        if "def _cleanup" in line: skip = True
        if line.startswith("@app.route") and ("('/')" in line or '("/")' in line): skip = True
            
        # THIS IS WHERE IT BELONGS
        if skip: continue
        
        # Remove imports and globals
        if line.startswith("from flask import"): continue
        if line.startswith("import"): continue
        if line.startswith("from playwright"): continue
        if "from PIL import Image" in line: continue
        if line.startswith("SESSIONS ="): continue
        if line.startswith("SESSION_LOCK ="): continue
            
        out.append(line)
    return "".join(out)

with open("app.py", "r", encoding='utf-8') as f:
    master = f.read()
master = master.split("# --- EC ---")[0]

ec = clean_file("../ec_automation_poc/app.py")
patta = clean_file("../view_patta_poc/app.py")
court = clean_file("../court_case_poc/app.py")

with open("app.py", "w", encoding='utf-8') as f:
    f.write(master)
    f.write("\n# --- EC ---\n")
    f.write(ec)
    f.write("\n# --- PATTA ---\n")
    f.write(patta)
    f.write("\n# --- COURT ---\n")
    f.write(court)
    f.write("\n@app.route('/')\ndef index():\n    return render_template('index.html')\n")
    f.write("\nif __name__ == '__main__':\n    app.run(debug=True, port=5005, threaded=False)\n")
