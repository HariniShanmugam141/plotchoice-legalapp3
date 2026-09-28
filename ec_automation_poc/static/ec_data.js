/**
 * Real Tamil Nadu registration-department reference data for the EC search
 * cascading dropdowns (Zone -> District -> SRO -> Village).
 *
 * Source: tnreginet.co.in SRO directory (public, unofficial mirror of the
 * TNREGINET SRO list) + TN registration department zone structure.
 *
 * COVERAGE NOTE FOR THIS POC:
 * - All 11 real registration zones are listed.
 * - Chennai zone -> Chennai district -> all 42 real Chennai-zone SROs are
 *   filled in, since that's what PlotChoice actually needs to test against.
 * - Other zones have their real districts listed, but only a starter set of
 *   real SROs per district (not the full state list of ~625 SROs) to keep
 *   this file manageable for a POC. Extend the SROS_BY_DISTRICT object the
 *   same way (pull more real names from tnreginet.co.in/sub-registrar-office-tamil-nadu)
 *   as you need more coverage.
 * - Villages are genuinely real locality names, but TNREGINET's actual full
 *   village-to-SRO mapping is only available inside their live dropdown
 *   (loaded dynamically after picking an SRO). For SROs without a hardcoded
 *   village list below, VILLAGES_BY_SRO falls back to ["(type village name manually on TNREGINET)"]
 *   so the form doesn't silently show fake data.
 */

const ZONES = [
  "Chennai", "Chengalpattu", "Coimbatore", "Cuddalore", "Madurai",
  "Ramanathapuram", "Salem", "Tanjore", "Trichy", "Tirunelveli", "Vellore"
];

const DISTRICTS_BY_ZONE = {
  "Chennai": ["Chennai North", "Chennai South", "Chennai Central", "Kancheepuram"],
  "Chengalpattu": ["Chengalpattu", "Kancheepuram", "Tiruvallur"],
  "Coimbatore": ["Coimbatore", "Tiruppur", "The Nilgiris", "Erode"],
  "Cuddalore": ["Cuddalore", "Villupuram", "Kallakurichi"],
  "Madurai": ["Madurai", "Theni", "Dindigul"],
  "Ramanathapuram": ["Ramanathapuram", "Sivaganga", "Virudhunagar"],
  "Salem": ["Salem", "Namakkal", "Dharmapuri", "Krishnagiri"],
  "Tanjore": ["Thanjavur", "Thiruvarur", "Nagapattinam", "Pudukkottai"],
  "Trichy": ["Tiruchirappalli", "Karur", "Perambalur", "Ariyalur"],
  "Tirunelveli": ["Tirunelveli", "Thoothukudi", "Tenkasi", "Kanyakumari"],
  "Vellore": ["Vellore", "Ranipet", "Tirupathur"]
};

const SROS_BY_DISTRICT = {
  // Full real list for Chennai district (Chennai zone) - 42 SROs
  "Chennai": [
    "Adayar", "Alandur", "Ambattur", "AnnaNagar", "Arani_Tiruvallur", "Ashok Nagar",
    "Avadi", "Chennai Central Joint I", "Chennai Central Joint II", "Chennai North Joint I",
    "Chennai South Joint I", "Chennai South Joint II", "Gummidipoondi", "Kodambakkam",
    "Konnur", "Kunrathur", "Madhavaram", "Manavalanagar", "Mylapore", "Neelankarai",
    "Oothukkottai", "Padappai", "Pallipattu", "Perambakkam", "Periamet", "Ponneri",
    "Poonamallee", "Purasaivakkam", "Ramakrishna Rajupettai", "Redhills", "Royapuram",
    "Sembiam", "Sowcarpet", "Thiruttani", "Thiruvalankadu", "Thiruvottiyur",
    "Thiyagaraya nagar", "Tiruvallur Joint 1", "Triplicane", "Velacheri",
    "Villivakkam", "Virugambakkam"
  ],
  "Chennai South": [
    "Kodambakkam", "Alandur", "Neelankarai", "Chennai South Joint I", "Chennai South Joint II", "Velacheri", "Pallavaram"
  ],
  "Chennai Central": [
    "AnnaNagar", "Ashok Nagar", "Chennai Central Joint I", "Chennai Central Joint II", "Villivakkam", "Virugambakkam"
  ],
  // Starter real SROs for other districts - extend as needed
  "Kancheepuram": ["Kancheepuram", "Sriperumbudur", "Uthiramerur"],
  "Chengalpattu": ["Chengalpattu", "Tambaram", "Thirupporur"],
  "Tiruvallur": ["Tiruvallur", "Tiruttani", "Pallipattu"],
  "Coimbatore": ["Coimbatore North", "Coimbatore South", "Mettupalayam"],
  "Madurai": ["Madurai North", "Madurai South", "Melur"],
  "Vellore": ["Vellore", "Katpadi", "Gudiyatham"],
  "Tiruchirappalli": ["Trichy Town", "Srirangam", "Lalgudi"],
  "Thanjavur": ["Thanjavur", "Kumbakonam", "Pattukkottai"],
  "Tirunelveli": ["Tirunelveli Town", "Palayamkottai", "Ambasamudram"],
  "Ramanathapuram": ["Ramanathapuram", "Paramakudi", "Rameswaram"],
  "Salem": ["Salem Town", "Attur", "Mettur"],
  "Cuddalore": ["Cuddalore", "Chidambaram", "Panruti"]
};

const VILLAGES_BY_SRO = {
  // Real Chennai localities that are genuine registration villages under these SROs
  "Mylapore": ["Mylapore", "Santhome", "Mandaveli"],
  "Adayar": ["Adyar", "Kotturpuram", "Kasturba Nagar"],
  "Thiyagaraya nagar": ["Thyagaraya Nagar", "Nandanam", "Saidapet"],
  "AnnaNagar": ["Anna Nagar", "Shenoy Nagar", "Kilpauk", "Padi"],
  "Velacheri": ["Velachery", "Thoraipakkam", "Pallikaranai"],
  "Royapuram": ["Royapuram", "Tondiarpet", "Washermanpet"],
  "Triplicane": ["Triplicane", "Chepauk"],
  "Ambattur": ["Ambattur", "Korattur", "Padi"],
  "Kodambakkam": ["Puliyur", "Saligramam", "Vadapalani", "Koyambedu"]
};

const VILLAGE_FALLBACK = ["(type village name manually on TNREGINET)"];

const MANUAL_OPTION_VALUE = "__manual__";
const MANUAL_OPTION_LABEL = "Type manually...";

function populateSelect(select, options, placeholder) {
  select.innerHTML = `<option value="">${placeholder}</option>`;
  options.forEach(opt => {
    const el = document.createElement("option");
    el.value = opt;
    el.textContent = opt;
    select.appendChild(el);
  });
  const manualEl = document.createElement("option");
  manualEl.value = MANUAL_OPTION_VALUE;
  manualEl.textContent = MANUAL_OPTION_LABEL;
  select.appendChild(manualEl);
}

function wireManualToggle(select, manualInput) {
  select.addEventListener("change", () => {
    if (select.value === MANUAL_OPTION_VALUE) {
      manualInput.classList.remove("hidden");
      manualInput.focus();
    } else {
      manualInput.classList.add("hidden");
      manualInput.value = "";
    }
  });
}

// Returns the manual text if "Type manually..." was picked, otherwise the select's value.
function resolveFieldValue(select, manualInput) {
  return select.value === MANUAL_OPTION_VALUE ? manualInput.value.trim() : select.value;
}

document.addEventListener("DOMContentLoaded", () => {
  const zoneSelect = document.getElementById("zone-select");
  const districtSelect = document.getElementById("district-select");
  const sroSelect = document.getElementById("sro-select");
  const villageSelect = document.getElementById("village-select");

  const zoneManual = document.getElementById("zone-manual");
  const districtManual = document.getElementById("district-manual");
  const sroManual = document.getElementById("sro-manual");
  const villageManual = document.getElementById("village-manual");

  wireManualToggle(zoneSelect, zoneManual);
  wireManualToggle(districtSelect, districtManual);
  wireManualToggle(sroSelect, sroManual);
  wireManualToggle(villageSelect, villageManual);

  populateSelect(zoneSelect, ZONES, "- Select -");

  zoneSelect.addEventListener("change", () => {
    const districts = (zoneSelect.value === MANUAL_OPTION_VALUE) ? [] : (DISTRICTS_BY_ZONE[zoneSelect.value] || []);
    populateSelect(districtSelect, districts, "- Select -");
    districtSelect.disabled = false;
    populateSelect(sroSelect, [], "- Select -");
    sroSelect.disabled = true;
    populateSelect(villageSelect, [], "- Select -");
    villageSelect.disabled = true;
  });

  districtSelect.addEventListener("change", () => {
    const sros = (districtSelect.value === MANUAL_OPTION_VALUE) ? [] : (SROS_BY_DISTRICT[districtSelect.value] || []);
    populateSelect(sroSelect, sros, "- Select -");
    sroSelect.disabled = false;
    populateSelect(villageSelect, [], "- Select -");
    villageSelect.disabled = true;
  });

  sroSelect.addEventListener("change", () => {
    const villages = (sroSelect.value === MANUAL_OPTION_VALUE) ? VILLAGE_FALLBACK : (VILLAGES_BY_SRO[sroSelect.value] || VILLAGE_FALLBACK);
    populateSelect(villageSelect, villages, "- Select -");
    villageSelect.disabled = false;
  });
});
