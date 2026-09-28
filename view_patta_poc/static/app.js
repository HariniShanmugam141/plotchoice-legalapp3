const form = document.getElementById("patta-form");
const statusEl = document.getElementById("status");
const resultSection = document.getElementById("result-section");
const resultText = document.getElementById("result-text");
const otpSection = document.getElementById("otp-section");
const otpInput = document.getElementById("otp-input");
const otpMsg = document.getElementById("otp-msg");
const submitOtpBtn = document.getElementById("submit-otp-btn");

const processDeedBtn = document.getElementById("processDeedBtn");
const deedFile = document.getElementById("deedFile");
const deedStatus = document.getElementById("deedStatus");
const extractionFields = document.getElementById("extraction-fields");

// Handle Search Type radio toggle
const radios = document.querySelectorAll('input[name="search_type"]');
const surveyGroup = document.getElementById("survey-group");
const pattaGroup = document.getElementById("patta-group");

radios.forEach(radio => {
  radio.addEventListener('change', (e) => {
    if (e.target.value === 'sur') {
      surveyGroup.style.display = 'block';
      pattaGroup.style.display = 'none';
    } else {
      surveyGroup.style.display = 'none';
      pattaGroup.style.display = 'block';
    }
  });
});

// Handle Area Type toggle for Ward/Block fields and Button Text
const areaSelect = document.getElementById("area-select");
const urbanGroup = document.getElementById("urban-group");
const searchBtn = document.getElementById("search-btn");

areaSelect.addEventListener('change', (e) => {
  if (e.target.value === 'Urban') {
    urbanGroup.style.display = 'block';
    searchBtn.textContent = 'Search TSLR';
  } else {
    urbanGroup.style.display = 'none';
    searchBtn.textContent = 'Search Patta';
  }
});

if (processDeedBtn) {
  processDeedBtn.addEventListener("click", async () => {
    if (!deedFile.files.length) {
      alert("Please select a PDF file first.");
      return;
    }

    deedStatus.textContent = "Analyzing document locally... Please wait.";
    deedStatus.style.color = "blue";
    // Hide the manual extraction fields to keep the UI clean during/after extraction
    extractionFields.style.display = "none";

    const formData = new FormData();
    formData.append("file", deedFile.files[0]);

    try {
      const res = await fetch("/extract-deed", {
        method: "POST",
        body: formData,
      });
      const data = await res.json();

      if (data.error) {
        deedStatus.textContent = "Error: " + data.error;
        deedStatus.style.color = "red";
        extractionFields.style.display = "block"; // Show again on error
        return;
      }

      // Populate fields
      if (data.area_type) {
        areaSelect.value = data.area_type;
        // Trigger the change event to update the button text and group visibility
        areaSelect.dispatchEvent(new Event('change'));
      }
      if (data.district) document.getElementById("district-input").value = data.district;
      if (data.taluk) document.getElementById("taluk-input").value = data.taluk;
      if (data.village) document.getElementById("village-input").value = data.village;
      if (data.ward) document.getElementById("ward-input").value = data.ward;
      if (data.block) document.getElementById("block-input").value = data.block;
      
      // Auto-extraction means we definitely have a survey number
      if (data.survey_no) {
        document.getElementById("survey-input").value = data.survey_no;
        document.querySelector('input[name="search_type"][value="sur"]').checked = true;
        surveyGroup.style.display = 'block';
        pattaGroup.style.display = 'none';
      }
      
      if (data.sub_division) document.getElementById("subdiv-input").value = data.sub_division;

      deedStatus.textContent = "Successfully extracted details! The manual fields have been hidden.";
      deedStatus.style.color = "green";
    } catch (err) {
      deedStatus.textContent = "Request failed: " + err;
      deedStatus.style.color = "red";
      extractionFields.style.display = "block";
    }
  });
}

let currentSessionId = null;
let timerInterval = null;

function startOtpTimer() {
  const timerDisplay = document.getElementById("otp-timer");
  const resendBtn = document.getElementById("resend-otp-btn");
  resendBtn.style.display = "none";
  
  let timeLeft = 120; // 2 minutes
  
  clearInterval(timerInterval);
  timerInterval = setInterval(() => {
    timeLeft--;
    let m = Math.floor(timeLeft / 60).toString().padStart(2, '0');
    let s = (timeLeft % 60).toString().padStart(2, '0');
    timerDisplay.textContent = `${m}:${s}`;
    
    if (timeLeft <= 0) {
      clearInterval(timerInterval);
      timerDisplay.textContent = "00:00 (Expired)";
      resendBtn.style.display = "inline-block";
    }
  }, 1000);
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const docNameStart = document.getElementById("area-select").value === "Urban" ? "TSLR" : "Patta"; statusEl.textContent = `Connecting to e-Services (${docNameStart}) and triggering OTP...`;
  resultSection.classList.add("hidden");
  otpSection.style.display = "none";

  const formData = new FormData(form);
  const payload = Object.fromEntries(formData.entries());

  try {
    const res = await fetch("/start-patta-search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (data.error) {
      statusEl.textContent = "Error: " + data.error;
      return;
    }

    if (data.status === "otp_required") {
      currentSessionId = data.session_id;
      statusEl.textContent = "Success! Waiting for you to enter the OTP.";
      otpSection.style.display = "block";
      otpInput.focus();
      startOtpTimer();
    }
  } catch (err) {
    statusEl.textContent = "Request failed: " + err;
  }
});

submitOtpBtn.addEventListener("click", async () => {
  const otpVal = otpInput.value.trim();
  if (!otpVal) {
    otpMsg.textContent = "Please enter the OTP.";
    return;
  }

  otpMsg.textContent = "Verifying OTP...";
  
  try {
    const res = await fetch("/submit-otp", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: currentSessionId, otp: otpVal })
    });
    const data = await res.json();

    if (data.error) {
      otpMsg.textContent = "Error: " + data.error;
      return;
    }

    if (data.status === "success") {
      otpSection.style.display = "none";
      const docName = document.getElementById("area-select").value === 'Urban' ? 'TSLR' : 'Patta';
      statusEl.textContent = `OTP Verified! ${docName} retrieved.`;
      if(data.image_b64) { document.getElementById("result-image").src = "data:image/png;base64," + data.image_b64; document.getElementById("result-image").style.display = "block"; } else { resultText.textContent = data.raw_text; resultText.style.display = "block"; }
      resultSection.classList.remove("hidden");
    }
  } catch (err) {
    otpMsg.textContent = "Request failed: " + err;
  }
});
const resendOtpBtn = document.getElementById('resend-otp-btn');
if (resendOtpBtn) {
  resendOtpBtn.addEventListener('click', async () => {
    if (!currentSessionId) return;
    
    resendOtpBtn.textContent = 'Resending...';
    resendOtpBtn.disabled = true;
    
    try {
      const res = await fetch('/resend-otp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: currentSessionId })
      });
      const data = await res.json();
      if (data.error) {
        alert('Failed to resend: ' + data.error);
        resendOtpBtn.textContent = 'Resend OTP';
        resendOtpBtn.disabled = false;
      } else {
        alert('OTP Resent Successfully!');
        resendOtpBtn.textContent = 'Resend OTP';
        resendOtpBtn.disabled = false;
        startOtpTimer(); // Restart the 2-minute timer
      }
    } catch(err) {
      alert('Error: ' + err);
      resendOtpBtn.textContent = 'Resend OTP';
      resendOtpBtn.disabled = false;
    }
  });
}
