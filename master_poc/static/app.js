// ─────────────────────────────────────────────────────────────────────────────
// DOM REFS
// ─────────────────────────────────────────────────────────────────────────────
const step1Section        = document.getElementById("step1-section");
const step2Section        = document.getElementById("step2-section");
const actionSection       = document.getElementById("action-section");
const resultsSection      = document.getElementById("results-section");

const nextToFieldsBtn     = document.getElementById("nextToFieldsBtn");
const backToStep1Btn      = document.getElementById("backToStep1Btn");
const detailsForm         = document.getElementById("details-form");

const liveStatus          = document.getElementById("live-status");
const currentTaskName     = document.getElementById("current-task-name");
const interactionBlock    = document.getElementById("interaction-block");
const interactionMsg      = document.getElementById("interaction-msg");
const captchaImg          = document.getElementById("captcha-img");
const interactionInput    = document.getElementById("interaction-input");
const interactionInput2   = document.getElementById("interaction-input-2");
const input2Container     = document.getElementById("input-2-container");
const label1              = document.getElementById("label-input-1");
const label2              = document.getElementById("label-input-2");
const downloadsList       = document.getElementById("downloads-list");

// Upload / Manual toggle refs
const btnModeUpload = document.getElementById("btnModeUpload");
const btnModeManual = document.getElementById("btnModeManual");
const uploadPanel   = document.getElementById("upload-panel");
const manualPanel   = document.getElementById("manual-panel");
const extractBtn    = document.getElementById("extractBtn");
const extractStatus = document.getElementById("extractStatus");

// ─────────────────────────────────────────────────────────────────────────────
// FIELD VISIBILITY MAP
// Which field groups each service needs shown in Step 2
// ─────────────────────────────────────────────────────────────────────────────
const SERVICE_FIELDS = {
    ec:    ["district", "zone", "sro", "village", "survey", "subdiv"],
    patta: ["district", "taluk", "village", "survey", "subdiv", "mobile"],
    tslr:  ["district", "taluk", "village", "ward", "block", "survey", "subdiv", "mobile"],
    court: ["party", "cnr"],
};

let selectedServices = [];
let collectedData    = {};

// Wizard State
let wizardQueue = [];
let isPipelineRunning = false;

// ─────────────────────────────────────────────────────────────────────────────
// WIZARD HELPERS
// ─────────────────────────────────────────────────────────────────────────────
function showFieldsForService(service) {
    document.querySelectorAll(".field-group").forEach(el => el.classList.add("hidden"));
    if (SERVICE_FIELDS[service]) {
        SERVICE_FIELDS[service].forEach(f => {
            const el = document.getElementById("grp-" + f);
            if (el) el.classList.remove("hidden");
        });
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// EXTRACT BUTTON — calls /patta/extract-deed and pre-fills visible fields
// ─────────────────────────────────────────────────────────────────────────────
// (PDF extraction now happens automatically in the form submit handler when in upload mode)

// ─────────────────────────────────────────────────────────────────────────────
// CASCADING DROPDOWN HELPERS
// ─────────────────────────────────────────────────────────────────────────────

function activeService() {
    if (selectedServices.includes("tslr"))  return "tslr";
    if (selectedServices.includes("patta")) return "patta";
    return null;   // EC only → leave as text inputs
}

/** Read value from either <input> or <select> by id */
function getVal(id) {
    const el = document.getElementById(id);
    return el ? el.value.trim() : "";
}

async function loadOptions(selectId, loaderId, body) {
    const sel    = document.getElementById(selectId);
    const loader = document.getElementById(loaderId);
    if (!sel || sel.tagName !== "SELECT") return;

    sel.disabled = true;
    sel.innerHTML = `<option value="">Loading…</option>`;
    if (loader) loader.classList.remove("hidden");

    try {
        const res  = await fetch("/patta/fetch-options", {
            method:  "POST",
            headers: { "Content-Type": "application/json" },
            body:    JSON.stringify(body),
        });
        const data = await res.json();
        if (data.error || !data.options || !data.options.length) {
            // Fallback: replace select with a free-text input
            sel.outerHTML = `<input type="text" id="${selectId}" placeholder="Type value manually">`;
            return;
        }
        sel.innerHTML = `<option value="">— Select —</option>` +
            data.options.map(o => `<option value="${o.label}">${o.label}</option>`).join("");
        sel.disabled = false;
    } catch (_) {
        sel.outerHTML = `<input type="text" id="${selectId}" placeholder="Type value manually">`;
    } finally {
        if (loader) loader.classList.add("hidden");
    }
}

function resetSelect(id, placeholder) {
    const el = document.getElementById(id);
    if (el && el.tagName === "SELECT") {
        el.innerHTML = `<option value="">${placeholder}</option>`;
        el.disabled  = true;
    }
}

let _cascadeInitialized = false;

async function initDistrictDropdown() {
    const svc = activeService();
    if (!svc) return;   // EC only — keep text inputs

    // Load districts (cached after first call)
    await loadOptions("f-district", "load-district", { service: svc, level: "district" });

    if (_cascadeInitialized) return;   // listeners already attached
    _cascadeInitialized = true;

    const distSel = document.getElementById("f-district");
    if (!distSel || distSel.tagName !== "SELECT") return;

    // ── District → load Taluks ──────────────────────────────────────────────
    distSel.addEventListener("change", async () => {
        const district = distSel.value;
        resetSelect("f-taluk",   "— Select District first —");
        resetSelect("f-village", "— Select Taluk first —");
        resetSelect("f-ward",    "— Select Village first —");
        resetSelect("f-block",   "— Select Ward first —");
        if (!district) return;
        await loadOptions("f-taluk", "load-taluk", { service: svc, level: "taluk", district });
    });

    // ── Taluk → load Villages ───────────────────────────────────────────────
    document.getElementById("f-taluk").addEventListener("change", async function() {
        // re-read distSel in case it was replaced with an input
        const district = getVal("f-district");
        const taluk    = this.value;
        resetSelect("f-village", "— Select Taluk first —");
        resetSelect("f-ward",    "— Select Village first —");
        resetSelect("f-block",   "— Select Ward first —");
        if (!taluk) return;
        await loadOptions("f-village", "load-village", { service: svc, level: "village", district, taluk });
    });
}

// ─────────────────────────────────────────────────────────────────────────────
// EC-SPECIFIC CASCADE  Zone → District(EC) → SRO
// ─────────────────────────────────────────────────────────────────────────────
async function loadOptionsFromEc(selectId, loaderId, body, retries=2) {
    const sel    = document.getElementById(selectId);
    const loader = document.getElementById(loaderId);
    if (!sel || sel.tagName !== "SELECT") return;
    sel.disabled = true;
    sel.innerHTML = `<option value="">Loading…</option>`;
    if (loader) loader.classList.remove("hidden");

    let success = false;
    let errMessage = "";

    for (let i = 0; i <= retries; i++) {
        try {
            const res  = await fetch("/ec/fetch-options", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            
            if (data.error || !data.options || !data.options.length) {
                errMessage = data.error || "No options returned";
                console.warn(`EC cascade error on ${body.level} (attempt ${i+1}):`, errMessage);
                if (i < retries) {
                    await new Promise(r => setTimeout(r, 1500));
                    continue;
                }
                break; // give up
            }
            
            sel.innerHTML = `<option value="">— Select —</option>` +
                data.options.map(o => `<option value="${o.label}">${o.label}</option>`).join("");
            sel.disabled = false;
            success = true;
            break;
        } catch (err) {
            errMessage = "Network error";
            console.warn(`EC cascade network error on ${body.level} (attempt ${i+1}):`, err);
            if (i < retries) {
                await new Promise(r => setTimeout(r, 1500));
                continue;
            }
        }
    }

    if (!success) {
        sel.outerHTML = `<input type="text" id="${selectId}" placeholder="Error: ${errMessage} (type manually)">`;
    }
    if (loader) loader.classList.add("hidden");
}

let _ecCascadeInitialized = false;

// Pre-warm EC zone cache silently in the background on page load
// so when the user opens the form, zones appear instantly
(function prewarmEcZones() {
    fetch("/ec/fetch-options", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ level: "zone" }),
    }).catch(() => {}); // silent — just warming the backend cache
})();

async function initEcDropdowns() {
    if (!selectedServices.includes("ec")) return;
    // Load Zones from EC portal (should be near-instant if pre-warm finished)
    await loadOptionsFromEc("f-zone", "load-zone", { level: "zone" });
    if (_ecCascadeInitialized) return;
    _ecCascadeInitialized = true;

    const zoneSel = document.getElementById("f-zone");
    if (!zoneSel || zoneSel.tagName !== "SELECT") return;

    // Zone → load EC Districts; reset downstream
    zoneSel.addEventListener("change", async () => {
        const zone = zoneSel.value;
        resetSelect("f-district", "— Select Zone first —");
        resetSelect("f-sro",      "— Select District first —");
        resetSelect("f-village",  "— Select SRO first —");
        if (!zone) return;
        await loadOptionsFromEc("f-district", "load-district", { level: "district", zone });
    });

    // District change → load SROs; reset downstream
    document.getElementById("f-district").addEventListener("change", async function () {
        const zone     = getVal("f-zone");
        const district = this.value;
        resetSelect("f-sro",     "— Select District first —");
        resetSelect("f-village", "— Select SRO first —");
        if (!district || !zone) return;
        await loadOptionsFromEc("f-sro", "load-sro", { level: "sro", zone, district });
    });

    // SRO change → load Villages
    document.getElementById("f-sro").addEventListener("change", async function () {
        const zone     = getVal("f-zone");
        const district = getVal("f-district");
        const sro      = this.value;
        resetSelect("f-village", "— Select SRO first —");
        if (!sro || !district || !zone) return;
        await loadOptionsFromEc("f-village", "load-village", { level: "village", zone, district, sro });
    });
}

// ─────────────────────────────────────────────────────────────────────────────
// STEP 1 → STEP 2: show only the relevant fields
// ─────────────────────────────────────────────────────────────────────────────
nextToFieldsBtn.addEventListener("click", () => {
    const checkboxes = document.querySelectorAll('input[name="services"]:checked');
    selectedServices = Array.from(checkboxes).map(c => c.value);

    if (selectedServices.length === 0) {
        alert("Please select at least one service.");
        return;
    }

    step1Section.classList.add("hidden");
    step2Section.classList.remove("hidden");
    
    // Default to Upload mode on entering Step 2
    setMode("upload");
});

function setMode(mode) {
    const btnModeUpload = document.getElementById("btnModeUpload");
    const btnModeManual = document.getElementById("btnModeManual");
    const uploadPanel   = document.getElementById("upload-panel");
    const wizardPanel   = document.getElementById("wizard-panel");
    
    if (mode === "upload") {
        btnModeUpload.classList.add("active");
        btnModeManual.classList.remove("active");
        uploadPanel.classList.remove("hidden");
        wizardPanel.classList.add("hidden");
    } else {
        btnModeManual.classList.add("active");
        btnModeUpload.classList.remove("active");
        uploadPanel.classList.add("hidden");
        wizardPanel.classList.remove("hidden");
        
        // Start the wizard loop
        runAutomationPipeline();
    }
}

document.getElementById("btnModeUpload").addEventListener("click", () => setMode("upload"));
document.getElementById("btnModeManual").addEventListener("click", () => setMode("manual"));

document.getElementById("processUploadBtn").addEventListener("click", async () => {
    const fileInput = document.getElementById("deedFile");
    if (!fileInput.files[0]) {
        alert("⚠ Please choose a PDF file first.");
        return;
    }
    
    step2Section.classList.add("hidden");
    actionSection.classList.remove("hidden");
    resultsSection.classList.remove("hidden");
    downloadsList.innerHTML = "";
    
    currentTaskName.textContent = "Extracting PDF…";
    liveStatus.textContent = "Reading sale deed — extracting property details…";

    try {
        const fd = new FormData();
        fd.append("file", fileInput.files[0]);
        const res = await fetch("/patta/extract-deed", { method: "POST", body: fd });
        const data = await res.json();
        
        if (data.error) {
            alert("Extraction failed: " + data.error);
            step2Section.classList.remove("hidden");
            actionSection.classList.add("hidden");
            return;
        }

        collectedData = {
            district:     data.district     || "",
            zone:         data.zone         || data.district || "",
            taluk:        data.taluk        || "",
            sro:          data.sro          || "",
            village:      data.village      || "",
            ward:         data.ward         || "",
            block:        data.block        || "",
            survey_no:    data.survey_no    || "",
            sub_division: data.sub_division || "",
            party_name:   data.party_name   || "",
            cnr_number:   "",
            mobile_no:    "",
        };
    } catch (err) {
        alert("Network error: " + err);
        step2Section.classList.remove("hidden");
        actionSection.classList.add("hidden");
        return;
    }
    
    // Upload Mode processing -> blind loop (no wizard forms)
    let hasError = false;
    for (const service of selectedServices) {
        const success = await processService(service);
        if (!success) { hasError = true; break; }
    }
    
    if (!hasError) actionSection.classList.add("hidden");
});

// ─────────────────────────────────────────────────────────────────────────────
// WIZARD PIPELINE
// ─────────────────────────────────────────────────────────────────────────────
async function runAutomationPipeline() {
    if (isPipelineRunning) return;
    isPipelineRunning = true;

    wizardQueue = [...selectedServices];
    let hasError = false;

    for (const service of wizardQueue) {
        // Step 1: Wait for user to verify/fill details for this specific service
        await showWizardFormAndWaitForSubmit(service);

        // Step 2: Hide form, show processing UI
        step2Section.classList.add("hidden");
        actionSection.classList.remove("hidden");
        resultsSection.classList.remove("hidden");
        downloadsList.innerHTML = "";
        
        // Step 3: Run the backend automation for this service
        const success = await processService(service);
        if (!success) { hasError = true; break; }
    }

    if (!hasError) {
        actionSection.classList.add("hidden");
        alert("All requested services have been processed successfully!");
    }
    isPipelineRunning = false;
}

function showWizardFormAndWaitForSubmit(service) {
    return new Promise((resolve) => {
        // Show step 2 form, hide processing UI
        actionSection.classList.add("hidden");
        step2Section.classList.remove("hidden");
        
        const titleMap = { ec: "EC", patta: "Patta", tslr: "Urban TSLR", court: "Court Case", fir: "FIR" };
        document.getElementById("wizard-title").textContent = `Verify Details for ${titleMap[service] || service}`;
        
        // Show only the fields needed for THIS service
        showFieldsForService(service);
        
        // Initialize appropriate dropdown cascade
        if (service === "ec") {
            _ecCascadeInitialized = false; // allow re-attaching listeners if form was reset
            initEcDropdowns();
        } else if (service === "patta" || service === "tslr") {
            _cascadeInitialized = false;
            initDistrictDropdown();
        }
        
        // Pre-fill text inputs if we already have data (from PDF extraction or previous step)
        const textFields = ["ward", "block", "survey", "subdiv", "party", "cnr", "mobile"];
        textFields.forEach(f => {
            const el = document.getElementById(`f-${f}`);
            const mapKey = (f === "survey") ? "survey_no" : (f === "subdiv") ? "sub_division" : (f === "party") ? "party_name" : (f === "cnr") ? "cnr_number" : (f === "mobile") ? "mobile_no" : f;
            if (el && collectedData[mapKey]) {
                el.value = collectedData[mapKey];
            }
        });

        // Define what happens when they click "Process this Service"
        detailsForm.onsubmit = (e) => {
            e.preventDefault();

            // Read the form into collectedData.
            // We ONLY overwrite collectedData if the user actually typed/selected something (val != "").
            // This preserves extracted PDF data even if a dropdown shows "— Select —".
            const fields = [
                { id: "f-district", key: "district" },
                { id: "f-zone",     key: "zone" },
                { id: "f-taluk",    key: "taluk" },
                { id: "f-sro",      key: "sro" },
                { id: "f-village",  key: "village" },
                { id: "f-ward",     key: "ward" },
                { id: "f-block",    key: "block" },
                { id: "f-survey",   key: "survey_no" },
                { id: "f-subdiv",   key: "sub_division" },
                { id: "f-party",    key: "party_name" },
                { id: "f-cnr",      key: "cnr_number" },
                { id: "f-mobile",   key: "mobile_no" },
            ];

            fields.forEach(f => {
                const val = getVal(f.id);
                if (val) collectedData[f.key] = val;
            });

            // Basic validation
            const hasProperty = collectedData.district || collectedData.village || collectedData.party_name || collectedData.cnr_number;
            if (!hasProperty) {
                alert("Please select at least District or Village from the dropdowns (or fill in Party Name).");
                return; // Don't resolve, let user fix it
            }

            // Remove the handler so it doesn't fire twice
            detailsForm.onsubmit = null;
            resolve();
        };
    });
}

// ─────────────────────────────────────────────────────────────────────────────
// INTERACTION HELPER — shows a prompt and waits for the user to click Submit
// ─────────────────────────────────────────────────────────────────────────────
function askUser(message, placeholder, imageB64 = null, inputType = "text", showSecond = false, placeholder2 = "") {
    return new Promise((resolve) => {
        interactionMsg.textContent = message;

        interactionInput.type = inputType;
        interactionInput.placeholder = placeholder;
        interactionInput.value = "";

        if (showSecond) {
            interactionInput2.type = inputType;
            interactionInput2.placeholder = placeholder2;
            interactionInput2.value = "";
            input2Container.classList.remove("hidden");
            label1.classList.remove("hidden");
            label1.style.display = "block";
            label2.style.display = "block";
        } else {
            input2Container.classList.add("hidden");
            label1.classList.add("hidden");
        }

        if (imageB64) {
            captchaImg.src = "data:image/png;base64," + imageB64;
            captchaImg.classList.remove("hidden");
        } else {
            captchaImg.classList.add("hidden");
        }

        interactionBlock.classList.remove("hidden");
        interactionInput.focus();

        // Clone to remove old listeners
        const oldBtn = document.getElementById("submitInteractionBtn");
        const newBtn = oldBtn.cloneNode(true);
        newBtn.disabled = false;
        oldBtn.parentNode.replaceChild(newBtn, oldBtn);

        newBtn.addEventListener("click", () => {
            const val1 = interactionInput.value.trim();
            if (!val1) return;

            let val2 = null;
            if (showSecond) {
                val2 = interactionInput2.value.trim();
                if (!val2) return;
            }

            newBtn.disabled = true;
            interactionBlock.classList.add("hidden");
            interactionInput.type = "text";
            interactionInput2.type = "text";

            if (showSecond) resolve({ val1, val2 });
            else resolve(val1);
        });
    });
}

// ─────────────────────────────────────────────────────────────────────────────
// PROCESS ONE SERVICE
// ─────────────────────────────────────────────────────────────────────────────
async function processService(service) {
    let taskName      = "";
    let startEndpoint = "";
    let areaType      = null;

    if (service === "ec")    { taskName = "EC";          startEndpoint = "/ec/start-ec-search"; }
    if (service === "patta") { taskName = "Patta";        startEndpoint = "/patta/start-patta-search"; areaType = "Rural"; }
    if (service === "tslr")  { taskName = "Urban TSLR";  startEndpoint = "/patta/start-patta-search"; areaType = "Urban"; }
    if (service === "court") { taskName = "Court Case";  startEndpoint = "/court/start-court-search"; }

    currentTaskName.textContent = taskName;
    liveStatus.textContent = `Processing ${taskName}...`;

    try {
        // Build the payload from the shared collected data
        const payload = { ...collectedData };
        if (areaType) payload.area_type = areaType;

        // ── Ask for mobile number if not already collected (upload mode) ─────
        if ((service === "patta" || service === "tslr") && !payload.mobile_no) {
            liveStatus.textContent = "Action Required: Mobile Number";
            payload.mobile_no = await askUser(
                "Enter the 10-digit mobile number to receive OTP:",
                "10-digit mobile number"
            );
            collectedData.mobile_no = payload.mobile_no; // cache for next service
        }

        // ── EC: ask for date range before starting ──────────────────────────
        if (service === "ec") {
            liveStatus.textContent = "Action Required: Date Range";
            const dates = await askUser(
                "Select the EC Search Start and End Date:",
                "", null, "date", true, ""
            );
            payload.ec_start_date = dates.val1;
            payload.ec_end_date   = dates.val2;
        }


        // ── STEP: START AUTOMATION ──────────────────────────────────────────
        liveStatus.textContent = `Starting ${taskName} automation...`;
        const startRes  = await fetch(startEndpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const data = await startRes.json();

        if (data.error) {
            liveStatus.textContent = `Error: ${data.error}`;
            liveStatus.style.color = "red";
            return false;
        }

        const sessionId = data.session_id;
        let submitEndpoint = "";
        let submitPayload  = { session_id: sessionId };

        // ── STEP: HANDLE INTERACTION (captcha or OTP) ───────────────────────
        if (data.captcha_image_base64) {
            liveStatus.textContent = "Action Required: Enter Captcha";
            const captchaVal = await askUser(
                "Please enter the Captcha shown:",
                "Enter Captcha",
                data.captcha_image_base64
            );
            if (service === "ec")    { submitEndpoint = "/ec/submit-captcha";    submitPayload.captcha_text = captchaVal; }
            if (service === "court") { submitEndpoint = "/court/submit-captcha"; submitPayload.captcha_text = captchaVal; }

        } else if (data.status === "otp_required" || data.status === "otp_sent") {
            liveStatus.textContent = "Action Required: Enter OTP";
            const otpVal = await askUser(
                `An OTP was sent to ${collectedData.mobile_no}. Enter it below:`,
                "Enter 6-digit OTP"
            );
            submitEndpoint = "/patta/submit-otp";
            submitPayload.otp       = otpVal;
            submitPayload.area_type = areaType;

        } else {
            // Automation completed without needing interaction (rare but possible)
            liveStatus.textContent = `${taskName} completed.`;
            await new Promise(r => setTimeout(r, 1500));
            return true;
        }

        // ── STEP: SUBMIT INTERACTION ────────────────────────────────────────
        liveStatus.textContent = "Submitting...";
        const submitRes  = await fetch(submitEndpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(submitPayload),
        });
        const submitData = await submitRes.json();

        if (submitData.error) {
            liveStatus.textContent = `Error: ${submitData.error}`;
            liveStatus.style.color = "red";
            return false;
        }

        // ── STEP: SAVE DOWNLOAD LINK ────────────────────────────────────────
        const addDownload = (href, label, isData = false, filename = "") => {
            const a = document.createElement("a");
            a.className    = "download-btn";
            a.target       = "_blank";
            a.href         = href;
            a.textContent  = label;
            if (isData) a.download = filename;
            downloadsList.appendChild(a);
        };

        if (submitData.download_url) {
            let url = submitData.download_url;
            if (url.startsWith("/download")) {
                if (service === "ec")    url = "/ec"    + url;
                if (service === "court") url = "/court" + url;
                if (service === "patta" || service === "tslr") url = "/patta" + url;
            }
            addDownload(url, `Download ${taskName} PDF`);
        } else if (submitData.sketch_download_url) {
            addDownload("/patta" + submitData.sketch_download_url, "Download TSLR Sketch PDF");
        } else if (submitData.image_b64) {
            addDownload(
                "data:image/png;base64," + submitData.image_b64,
                `Download ${taskName} Image`,
                true,
                `${service}_result.png`
            );
        }

        liveStatus.textContent = `${taskName} completed successfully!`;
        liveStatus.style.color = "#1a5c38";
        await new Promise(r => setTimeout(r, 2000));
        liveStatus.style.color = "";
        return true;

    } catch (err) {
        liveStatus.textContent = "Fatal Error: " + err;
        liveStatus.style.color = "red";
        return false;
    }
}
