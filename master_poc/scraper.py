from playwright.sync_api import sync_playwright

def scrape():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://tnreginet.gov.in/portal/")
        page.wait_for_timeout(3000)
        
        # Open EC tab
        page.locator("#ec").click()
        page.wait_for_timeout(1000)
        
        # Get zones
        zones = page.locator("#zone").locator("option").all()
        for z in zones:
            if "Vellore" in z.text_content():
                zone_val = z.get_attribute("value")
                page.locator("#zone").select_option(value=zone_val)
                print(f"Zone: {zone_val}")
                break
                
        page.wait_for_timeout(2000)
        districts = page.locator("#district").locator("option").all()
        for d in districts:
            if "Tiruvannamalai" in d.text_content():
                dist_val = d.get_attribute("value")
                page.locator("#district").select_option(value=dist_val)
                print(f"District: {dist_val}")
                break
                
        page.wait_for_timeout(2000)
        sros = page.locator("#sroName").locator("option").all()
        for s in sros:
            if "Vandavasi" in s.text_content():
                sro_val = s.get_attribute("value")
                page.locator("#sroName").select_option(value=sro_val)
                print(f"SRO: {sro_val}")
                break
                
        page.wait_for_timeout(2000)
        villages = page.locator("#village").locator("option").all()
        for v in villages:
            if "Adaiyur" in v.text_content():
                vil_val = v.get_attribute("value")
                print(f"Village: {vil_val}")
                break
                
        browser.close()

scrape()
