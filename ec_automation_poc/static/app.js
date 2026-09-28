let currentSessionId = null;

const form = document.getElementById("ec-form");
const statusEl = document.getElementById("status");
const captchaSection = document.getElementById("captcha-section");
const captchaImg = document.getElementById("captcha-img");
const captchaInput = document.getElementById("captcha-input");
const captchaMsg = document.getElementById("captcha-msg");
const resultSection = document.getElementById("result-section");
const downloadLink = document.getElementById("download-link");

// -----------------------------------------------------
// AI AUTO-FILL LOGIC
// -----------------------------------------------------
document.getElementById("processDeedBtn").addEventListener("click", async () => {
  const fileInput = document.getElementById("deedFile");
  const deedStatus = document.getElementById("deedStatus");
  
  if (!fileInput.files.length) {
    deedStatus.textContent = "Please select a PDF file first.";
    deedStatus.style.color = "red";
    return;
  }

  deedStatus.textContent = "Analyzing document locally using pattern matching... Please wait.";
  deedStatus.style.color = "blue";

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);

  try {
    const res = await fetch("/extract-deed", {
      method: "POST",
      body: formData
    });
    
    const data = await res.json();
    if (data.error) {
      deedStatus.textContent = "Error: " + data.error;
      deedStatus.style.color = "red";
      return;
    }

    deedStatus.textContent = "Successfully extracted details!";
    deedStatus.style.color = "green";
    
    console.log("Extracted Data:", data);

    // Auto-fill logic
    // We set the "manual" text boxes for the cascading dropdowns
    // so they trigger the cascading logic if needed, or bypass it entirely
    // since our backend accepts manual typed values natively.
    
    if (data.zone) {
      document.getElementById("zone-select").value = "__manual__";
      document.getElementById("zone-select").dispatchEvent(new Event('change'));
      document.getElementById("zone-manual").value = data.zone;
    }
    
    if (data.district) {
      document.getElementById("district-select").value = "__manual__";
      document.getElementById("district-select").dispatchEvent(new Event('change'));
      document.getElementById("district-manual").value = data.district;
    }
    
    if (data.sro) {
      document.getElementById("sro-select").value = "__manual__";
      document.getElementById("sro-select").dispatchEvent(new Event('change'));
      document.getElementById("sro-manual").value = data.sro;
    }
    
    if (data.village) {
      document.getElementById("village-select").value = "__manual__";
      document.getElementById("village-select").dispatchEvent(new Event('change'));
      document.getElementById("village-manual").value = data.village;
    }

    if (data.survey_no) {
      document.querySelector("input[name='survey_no']").value = data.survey_no;
    }
    
    if (data.sub_division) {
      document.querySelector("input[name='sub_division']").value = data.sub_division;
    }
    
  } catch (err) {
    deedStatus.textContent = "Failed to process: " + err.message;
    deedStatus.style.color = "red";
  }
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  statusEl.textContent = "Opening TNREGINET and filling the form...";
  captchaSection.classList.add("hidden");
  resultSection.classList.add("hidden");

  const formData = new FormData(form);
  const payload = Object.fromEntries(formData.entries());

  // Manual-entry overrides for the four dropdown fields
  payload.zone = resolveFieldValue(document.getElementById("zone-select"), document.getElementById("zone-manual"));
  payload.district = resolveFieldValue(document.getElementById("district-select"), document.getElementById("district-manual"));
  payload.sro = resolveFieldValue(document.getElementById("sro-select"), document.getElementById("sro-manual"));
  payload.village = resolveFieldValue(document.getElementById("village-select"), document.getElementById("village-manual"));

  try {
    const res = await fetch("/start-ec-search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (data.error) {
      statusEl.textContent = "Error: " + data.error;
      return;
    }

    currentSessionId = data.session_id;
    captchaImg.src = "data:image/png;base64," + data.captcha_image_base64;
    statusEl.textContent = "Form filled. Please enter the captcha shown below.";
    captchaSection.classList.remove("hidden");
  } catch (err) {
    statusEl.textContent = "Request failed: " + err;
  }
});

document.getElementById("captcha-submit-btn").addEventListener("click", async () => {
  const captchaText = captchaInput.value.trim();
  if (!captchaText) return;

  captchaMsg.textContent = "Submitting...";

  try {
    const res = await fetch("/submit-captcha", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: currentSessionId, captcha_text: captchaText }),
    });
    const data = await res.json();

    if (data.error) {
      captchaMsg.textContent = "Error: " + data.error;
      return;
    }

    if (data.status === "retry") {
      captchaImg.src = "data:image/png;base64," + data.captcha_image_base64;
      captchaMsg.textContent = data.message;
      captchaInput.value = "";
      return;
    }

    if (data.status === "email_required") {
      captchaSection.classList.add("hidden");
      document.getElementById("emailSection").style.display = "block";
      statusEl.textContent = data.message;
      return;
    }

    if (data.status === "success") {
      captchaSection.classList.add("hidden");
      resultSection.classList.remove("hidden");
      downloadLink.href = data.download_url;
    }
  } catch (err) {
    captchaMsg.textContent = "Request failed: " + err;
  }
});

// New listener for the >200 records email submission
document.getElementById("submitEmailBtn").addEventListener("click", async () => {
  const name = document.getElementById("reqName").value.trim();
  const email = document.getElementById("reqEmail").value.trim();
  
  if (!name || !email) return;

  statusEl.textContent = "Submitting your details to TNREGINET...";
  
  try {
    const res = await fetch("/submit-email", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: currentSessionId, name, email }),
    });
    const data = await res.json();

    if (data.error) {
      statusEl.textContent = "Error: " + data.error;
      return;
    }

    if (data.status === "success") {
      document.getElementById("emailSection").style.display = "none";
      statusEl.textContent = "Success! TNREGINET will process the massive PDF in the background and email it to you shortly.";
    }
  } catch (err) {
    statusEl.textContent = "Request failed: " + err;
  }
});
