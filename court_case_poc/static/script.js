const searchTypeSelect = document.getElementById("searchType");
const partyNameSection = document.getElementById("partyNameSection");
const cnrSection = document.getElementById("cnrSection");


const form = document.getElementById("courtSearchForm");
const submitBtn = document.getElementById("submitBtn");
const statusBox = document.getElementById("statusBox");
const resultBox = document.getElementById("resultBox");

const captchaPanel = document.getElementById("captchaPanel");
const captchaImage = document.getElementById("captchaImage");
const captchaInput = document.getElementById("captchaInput");
const submitCaptchaBtn = document.getElementById("submitCaptchaBtn");

let currentSearchId = null;

// ==========================================
// Dependent Dropdown Logic (State -> District -> Court Complex)
// ==========================================

// Pre-filling with the exact states from the official eCourts portal
const statesList = [
    "Kerala", "Ladakh", "Lakshadweep", "Madhya Pradesh", "Maharashtra", 
    "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Puducherry", 
    "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu"
];

const districtData = {
    "Tamil Nadu": [
        { label: "Ariyalur", value: "Ariyalur" },
        { label: "Chengalpattu", value: "Chengalpattu" },
        { label: "Chennai", value: "Chennai" },
        { label: "Coimbatore", value: "Coimbatore" },
        { label: "Cuddalore", value: "Cuddalore" },
        { label: "Dharmapuri", value: "Dharmapuri" },
        { label: "Dindigul", value: "Dindigul" },
        { label: "Erode", value: "Erode" },
        { label: "Kallakurichi", value: "Kallakurichi" },
        { label: "Kancheepuram", value: "Kancheepuram" },
        { label: "Kanniyakumari", value: "Kanniyakumari" },
        { label: "Karur", value: "Karur" },
        { label: "Krishnagiri", value: "Krishnagiri" },
        { label: "Madurai", value: "Madurai" }
    ]
};

const courtData = {
    "Chennai": [
        { label: "Singaravelar Maaligai Complex", value: "Singaravelar" },
        { label: "C M M Court, Egmore", value: "C M M Court, Egmore" },
        { label: "M M Courts, George Town", value: "George Town" },
        { label: "M M Courts, Saidapet", value: "Saidapet" },
        { label: "City Civil Court Complex, Chennai", value: "City Civil Court Complex" },
        { label: "Court of Small Causes, Chennai", value: "Small Causes" },
        { label: "Bomb Blast Court, Poonamallee", value: "Bomb Blast" },
        { label: "M M Courts, Egmore at Allikulam", value: "Allikulam" }
    ]
};

// Initialize the State dropdown on load
const stateSelect = document.getElementById("pn_state");
statesList.forEach(s => {
    stateSelect.insertAdjacentHTML('beforeend', `<option value="${s}">${s}</option>`);
});

// Helper to manually trigger change events
function triggerChange(element) {
    const event = new Event('change', { bubbles: true });
    element.dispatchEvent(event);
}

// ==========================================
// File Upload & Extraction Logic
// ==========================================
const extractBtn = document.getElementById("extractBtn");
const deedFileInput = document.getElementById("deed_file");
const extractStatus = document.getElementById("extractStatus");
const courtSearchForm = document.getElementById("courtSearchForm");

extractBtn.addEventListener("click", async () => {
    const file = deedFileInput.files[0];
    if (!file) {
        extractStatus.textContent = "Please select a file first.";
        extractStatus.style.color = "red";
        return;
    }
    
    extractBtn.disabled = true;
    extractBtn.textContent = "Extracting details...";
    extractStatus.textContent = "";
    
    const formData = new FormData();
    formData.append("file", file);
    
    try {
        const response = await fetch("/extract-deed", { method: "POST", body: formData });
        const data = await response.json();
        
        if (data.error) {
            extractStatus.textContent = data.error;
            extractStatus.style.color = "red";
            extractBtn.disabled = false;
            extractBtn.textContent = "Process Document";
            return;
        }
        
        // Populate and trigger cascading dropdowns
        document.getElementById("party_name").value = data.party_name || "";
        
        stateSelect.value = data.state || "Tamil Nadu";
        triggerChange(stateSelect);
        
        const districtSelect = document.getElementById("pn_district");
        districtSelect.value = data.district || "Chennai";
        triggerChange(districtSelect);
        
        // Auto-select court complex
        const courtSelect = document.getElementById("pn_court_complex");
        // Preselect a default if the district is Chennai
        if ((data.district || "Chennai") === "Chennai") {
            // Find "City Civil" value in options
            for (let i = 0; i < courtSelect.options.length; i++) {
                if (courtSelect.options[i].value === "City Civil Court Complex") {
                    courtSelect.selectedIndex = i;
                    break;
                }
            }
        }
        
        // Hide upload, show form
        document.getElementById("uploadSection").style.display = "none";
        courtSearchForm.style.display = "block";
        
    } catch (e) {
        extractStatus.textContent = "Extraction failed due to network error.";
        extractStatus.style.color = "red";
        extractBtn.disabled = false;
        extractBtn.textContent = "Process Document";
    }
});
// ==========================================

document.getElementById("pn_state").addEventListener("change", function() {
    const state = this.value;
    const districtSelect = document.getElementById("pn_district");
    const courtSelect = document.getElementById("pn_court_complex");
    
    districtSelect.innerHTML = '<option value="">Select District</option>';
    courtSelect.innerHTML = '<option value="">Select Court Complex</option>';
    
    if (state && districtData[state]) {
        districtSelect.disabled = false;
        districtData[state].forEach(d => {
            districtSelect.insertAdjacentHTML('beforeend', `<option value="${d.value}">${d.label}</option>`);
        });
    } else {
        districtSelect.disabled = true;
        courtSelect.disabled = true;
    }
});

document.getElementById("pn_district").addEventListener("change", function() {
    const district = this.value;
    const courtSelect = document.getElementById("pn_court_complex");
    
    courtSelect.innerHTML = '<option value="">Select Court Complex</option>';
    
    // Use the label of the selected district to look up courts, because 'this.value' might be shorter now!
    // Actually wait, for district we used the full name as the value in our dictionary. Let's just use this.value
    if (district && courtData[district]) {
        courtSelect.disabled = false;
        courtData[district].forEach(c => {
            courtSelect.insertAdjacentHTML('beforeend', `<option value="${c.value}">${c.label}</option>`);
        });
    } else {
        courtSelect.disabled = true;
    }
});
// ==========================================

function showSection(activeId) {
    [partyNameSection, cnrSection].forEach((section) => {
        section.style.display = section.id === activeId ? "block" : "none";
    });
}

searchTypeSelect.addEventListener("change", () => {
    const type = searchTypeSelect.value;
    if (type === "PARTY_NAME") showSection("partyNameSection");
    else if (type === "CNR_NUMBER") showSection("cnrSection");
});

// initial state
showSection("partyNameSection");

function setStatus(label, cssClass, message) {
    statusBox.innerHTML = `
        <span class="status-pill ${cssClass}">${label}</span>
        ${message ? `<div style="margin-top:8px;">${message}</div>` : ""}
    `;
}

async function viewCaseDetails(cnr) {
    if (!currentSearchId) return;
    setStatus("FETCHING DETAILS...", "status-searching");
    try {
        const response = await fetch("/view-case", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ search_id: currentSearchId, cnr_number: cnr }),
        });
        const data = await response.json();
        renderResult(data);
    } catch (err) {
        setStatus("FAILED", "status-failed", "Could not fetch details.");
    }
}

function renderResult(data) {
    resultBox.innerHTML = "";
    
    // Only save summary data, not detailed card data
    if (data.cases && data.cases.length > 1) {
        window.lastSearchData = data;
    }

    if (data.status === "CASES_FOUND" && data.cases && data.cases.length > 0) {
        setStatus("CASES FOUND", "status-found");

        // If it's a detailed view (marked by the backend)
        if (data.cases.length === 1 && data.cases[0].is_detailed) {
            const c = data.cases[0];
            
            // If we captured the full official HTML, render it directly!
            if (c.full_html) {
                resultBox.innerHTML = `
                    <button onclick="renderResult(window.lastSearchData)" style="margin-bottom: 15px; padding: 8px 15px; background: #2c3e50; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px;">&larr; Back to Results</button>
                    <div class="official-case-details" style="overflow-x: auto; background: white; padding: 15px; border-radius: 5px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                        ${c.full_html}
                    </div>
                `;
            } else {
                resultBox.innerHTML = `
                    <button onclick="renderResult(window.lastSearchData)" style="margin-bottom: 10px; padding: 5px 10px; cursor: pointer;">&larr; Back to Results</button>
                    <div class="case-details-card" style="border: 1px solid #ccc; padding: 15px; background: #fafafa; border-radius: 5px;">
                        <h3>Case Details: ${c.cnr_number || "Unknown"}</h3>
                        <p><strong>Case Number:</strong> ${c.case_number || "-"}</p>
                        <p><strong>Parties:</strong> ${c.party_names || "-"}</p>
                        <p><strong>Court / Judge:</strong> ${c.court || "-"}</p>
                        <p><strong>Status:</strong> ${c.case_status || c.case_stage || "-"}</p>
                        <p><strong>Next Hearing / Decision Date:</strong> ${c.next_hearing_date || c.decision_date || "-"}</p>
                    </div>
                `;
            }
            return;
        }

        let rows = data.cases.map((c, index) => `
            <tr>
                <td>${index + 1}</td>
                <td>${c.case_number || "-"}</td>
                <td>${c.party_names || "-"}</td>
                <td>
                    ${c.cnr_number ? `<button onclick="viewCaseDetails('${c.cnr_number}')" style="padding: 4px 8px; font-size: 12px; cursor: pointer;">View</button>` : "-"}
                </td>
            </tr>
        `).join("");

        resultBox.innerHTML = `
            <div class="warning-box">
                <strong>Potential Litigation Records Found</strong><br>
                One or more matching court records were found based on the selected search criteria.
            </div>
            <table class="case-table">
                <thead>
                    <tr>
                        <th>Sr No</th>
                        <th>Case Type/Case Number/Case Year</th>
                        <th>Petitioner Name versus Respondent Name</th>
                        <th>View</th>
                    </tr>
                </thead>
                <tbody>
                    ${rows}
                </tbody>
            </table>
            <p class="disclaimer">${data.disclaimer || ""}</p>
        `;

    } else if (data.status === "NO_CASE_FOUND") {
        setStatus("NO MATCHING CASES FOUND", "status-none");
        resultBox.innerHTML = `
            <div class="no-result-box">
                <strong>No Matching Cases Found</strong><br>
                No matching cases were found using the selected search criteria.
            </div>
            <p class="disclaimer">
                This search result does not guarantee that no litigation exists. Results depend on:
                search criteria, party name spelling, selected court, available court records, and
                case indexing. Independent legal verification is recommended.
            </p>
        `;

    } else if (data.status === "MANUAL_CONFIGURATION_REQUIRED") {
        setStatus("MANUAL CONFIGURATION REQUIRED", "status-manual");
        resultBox.innerHTML = `
            <div class="manual-box">
                ${data.message || "This search mode is not fully configured yet."}
            </div>
        `;

    } else if (data.status === "FAILED") {
        setStatus("FAILED", "status-failed");
        resultBox.innerHTML = `<div class="manual-box">${data.message || "The search failed."}</div>`;
    } else {
        setStatus(data.status || "UNKNOWN", "status-manual", data.message || "");
    }
}

function collectFormData() {
    const searchSource = document.getElementById("searchSource").value;
    const searchType = document.getElementById("searchType").value;

    const payload = {
        search_source: searchSource,
        search_type: searchType,
    };

    if (searchType === "PARTY_NAME") {
        payload.party_name = document.getElementById("party_name").value;
        payload.state = document.getElementById("pn_state").value;
        payload.district = document.getElementById("pn_district").value;
        payload.court_complex = document.getElementById("pn_court_complex").value;
        payload.registration_year = document.getElementById("registration_year").value;
        payload.case_status = document.getElementById("case_status").value;
    } else if (searchType === "CNR_NUMBER") {
        payload.cnr_number = document.getElementById("cnr_number").value;
    }

    return payload;
}

form.addEventListener("submit", async (e) => {
    e.preventDefault();

    submitBtn.disabled = true;
    submitBtn.textContent = "Searching Court Records...";
    captchaPanel.style.display = "none";
    resultBox.innerHTML = "";
    setStatus("SEARCHING", "status-searching");

    try {
        const response = await fetch("/start-court-search", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(collectFormData()),
        });

        const data = await response.json();
        currentSearchId = data.search_id || null;

        if (data.status === "CAPTCHA_REQUIRED") {
            setStatus("CAPTCHA REQUIRED", "status-captcha", data.message);
            captchaImage.src = `data:image/png;base64,${data.captcha_image_base64}`;
            captchaPanel.style.display = "block";
        } else {
            renderResult(data);
        }
    } catch (err) {
        setStatus("FAILED", "status-failed", "Could not reach the server.");
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "Search Court Records";
    }
});

submitCaptchaBtn.addEventListener("click", async () => {
    if (!currentSearchId) return;

    submitCaptchaBtn.disabled = true;
    submitCaptchaBtn.textContent = "Submitting...";
    setStatus("SEARCHING", "status-searching");

    try {
        const response = await fetch("/submit-captcha", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                search_id: currentSearchId,
                captcha: captchaInput.value,
            }),
        });

        const data = await response.json();
        captchaPanel.style.display = "none";
        renderResult(data);
    } catch (err) {
        setStatus("FAILED", "status-failed", "Could not reach the server.");
    } finally {
        submitCaptchaBtn.disabled = false;
        submitCaptchaBtn.textContent = "Submit CAPTCHA";
        captchaInput.value = "";
    }
});
