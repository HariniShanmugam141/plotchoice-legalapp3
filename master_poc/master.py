import os
import sys
import importlib.util
from flask import Flask, render_template
from werkzeug.middleware.dispatcher import DispatcherMiddleware

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

ec_module = load_module("ec_module", os.path.abspath("../ec_automation_poc/app.py"))
patta_module = load_module("patta_module", os.path.abspath("../view_patta_poc/app.py"))
court_module = load_module("court_module", os.path.abspath("../court_case_poc/app.py"))

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

application = DispatcherMiddleware(app, {
    '/ec': ec_module.app,
    '/patta': patta_module.app,
    '/court': court_module.app
})

if __name__ == '__main__':
    from werkzeug.serving import run_simple
    os.makedirs('downloads', exist_ok=True)
    
    print("Preloading EC/Patta/TSLR portal (TNREGINET)...")
    try:
        ec_module.get_global_page()
    except Exception as e:
        print("Failed to preload EC:", e)
        
    print("Preloading Court Case portal (eCourts)...")
    try:
        # Share the Playwright instance to prevent "Playwright Sync API inside asyncio loop" error
        # which occurs when sync_playwright().start() is called multiple times on the same thread.
        if ec_module._GLOBAL_PW is not None:
            court_module._GLOBAL_PW = ec_module._GLOBAL_PW
            court_module._GLOBAL_BROWSER = ec_module._GLOBAL_BROWSER
        court_module.get_global_page()
    except Exception as e:
        print("Failed to preload Court:", e)
        
    print("Preloading complete! Starting Master Server on port 5005...")
    run_simple('0.0.0.0', 5005, application,
               use_reloader=False,   
               use_debugger=True,
               threaded=False)
