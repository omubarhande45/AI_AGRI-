/* AgriSmartAI Internationalization (i18n) Engine
   Supports English (en), Hindi (hi), and Marathi (mr)
*/
(function () {
  "use strict";

  var TRANSLATIONS = {
    en: {
      "Dashboard": "Dashboard",
      "Disease Detection & XAI": "Disease Detection & XAI",
      "Digital Twin & Sensors": "Digital Twin & Sensors",
      "AI Yield & DSS": "AI Yield & DSS",
      "Market Intelligence & Mandi": "Market Intelligence & Mandi",
      "Reports": "Reports",
      "FIELD OPERATIONS": "FIELD OPERATIONS",
      "Crop Monitoring": "Crop Monitoring",
      "AI Predictions Lab": "AI Predictions Lab",
      "Weather Station": "Weather Station",
      "Profile & Settings": "Profile & Settings",
      "Log out": "Log out",
      "Scan New Leaf": "Scan New Leaf",
      "Digital Twin": "Digital Twin",
      "Mandi Rates": "Mandi Rates",
      "ACTIVE FARMER PLOT": "ACTIVE FARMER PLOT",
      "CROP HEALTH INDEX": "CROP HEALTH INDEX",
      "HYPERLOCAL WEATHER": "HYPERLOCAL WEATHER",
      "PREDICTED HARVEST YIELD": "PREDICTED HARVEST YIELD",
      "SOIL TELEMETRY (NODE #5)": "SOIL TELEMETRY (NODE #5)",
      "Optimal range": "Optimal range",
      "Grade": "Grade",
      "Humidity": "Humidity",
      "Wind": "Wind",
      "Rain 7d": "Rain 7d",
      "Est. market value": "Est. market value",
      "Model conf.": "Model conf.",
      "Status": "Status",
      "pH": "pH",
      "Farmer login": "Farmer login",
      "Username": "Username",
      "Password": "Password",
      "Sign in →": "Sign in →",
      "Register a farmer account": "Register a farmer account",
      "Every decision on your farm, backed by AI.": "Every decision on your farm, backed by AI.",
      "Edge AI": "Edge AI",
      "Market Intelligence": "Market Intelligence",
      "DSS": "DSS",
      "WEATHER AI · SYNCED": "WEATHER AI · SYNCED",
      "MANDI API ONLINE": "MANDI API ONLINE",
      "Execute In-Silico Forecast": "Execute In-Silico Forecast",
      "Run Scenario →": "Run Scenario →",
      "Review CNN saliency map →": "Review CNN saliency map →",
      "Language": "Language"
    },
    hi: {
      "Dashboard": "डैशबोर्ड",
      "Disease Detection & XAI": "रोग पहचान और XAI",
      "Digital Twin & Sensors": "डिजिटल ट्विन और सेंसर",
      "AI Yield & DSS": "AI उपज और DSS",
      "Market Intelligence & Mandi": "बाजार भाव और मंडी",
      "Reports": "रिपोर्ट्स",
      "FIELD OPERATIONS": "खेत परिचालन",
      "Crop Monitoring": "फसल निगरानी",
      "AI Predictions Lab": "AI पूर्वानुमान लैब",
      "Weather Station": "मौसम केंद्र",
      "Profile & Settings": "प्रोफाइल और सेटिंग्स",
      "Log out": "लॉग आउट",
      "Scan New Leaf": "पत्ती स्कैन करें",
      "Digital Twin": "डिजिटल ट्विन",
      "Mandi Rates": "मंडी भाव",
      "ACTIVE FARMER PLOT": "सक्रिय किसान खेत",
      "CROP HEALTH INDEX": "फसल स्वास्थ्य सूचकांक",
      "HYPERLOCAL WEATHER": "स्थानिक मौसम",
      "PREDICTED HARVEST YIELD": "अनुमानित फसल उपज",
      "SOIL TELEMETRY (NODE #5)": "मृदा टेलीमेट्री (नोड #5)",
      "Optimal range": "अनुकूल सीमा",
      "Grade": "श्रेणी",
      "Humidity": "आर्द्रता",
      "Wind": "हवा",
      "Rain 7d": "वर्षा (7 दिन)",
      "Est. market value": "अनुमानित बाजार मूल्य",
      "Model conf.": "मॉडल सटीकता",
      "Status": "स्थिति",
      "pH": "पीएच (pH)",
      "Farmer login": "किसान लॉगिन",
      "Username": "उपयोगकर्ता नाम",
      "Password": "पासवर्ड",
      "Sign in →": "साइन इन करें →",
      "Register a farmer account": "नया किसान खाता बनाएं",
      "Every decision on your farm, backed by AI.": "आपके खेत का हर निर्णय, AI द्वारा समर्थित।",
      "Edge AI": "एज AI",
      "Market Intelligence": "बाजार बुद्धिमत्ता",
      "DSS": "निर्णय सहायता प्रणाली (DSS)",
      "WEATHER AI · SYNCED": "मौसम AI · सिंक किया गया",
      "MANDI API ONLINE": "मंडी API ऑनलाइन",
      "Execute In-Silico Forecast": "इन-सिलिको पूर्वानुमान चलाएं",
      "Run Scenario →": "परिदृश्य चलाएं →",
      "Review CNN saliency map →": "CNN मैप देखें →",
      "Language": "भाषा"
    },
    mr: {
      "Dashboard": "डॅशबोर्ड",
      "Disease Detection & XAI": "रोग निदान आणि XAI",
      "Digital Twin & Sensors": "डिजिटल ट्विन आणि सेन्सर्स",
      "AI Yield & DSS": "AI पीक उत्पादन व निर्णय प्रणाली",
      "Market Intelligence & Mandi": "बाजार भाव व मंडी",
      "Reports": "अहवाल (Reports)",
      "FIELD OPERATIONS": "शेतातील कामकाज",
      "Crop Monitoring": "पीक पाहणी व देखरेख",
      "AI Predictions Lab": "AI अंदाज प्रयोगशाळा",
      "Weather Station": "हवामान केंद्र",
      "Profile & Settings": "प्रोफाइल आणि सेटिंग्ज",
      "Log out": "लॉग आउट करा",
      "Scan New Leaf": "नवीन पान स्कॅन करा",
      "Digital Twin": "डिजिटल ट्विन",
      "Mandi Rates": "मंडी दर",
      "ACTIVE FARMER PLOT": "सक्रिय शेतकरी गट",
      "CROP HEALTH INDEX": "पीक आरोग्य निर्देशांक",
      "HYPERLOCAL WEATHER": "स्थानिक हवामान",
      "PREDICTED HARVEST YIELD": "अंदाजित पीक उत्पादन",
      "SOIL TELEMETRY (NODE #5)": "मातीचे गुणधर्म (नोड #5)",
      "Optimal range": "योग्य प्रमाण",
      "Grade": "दर्जा (Grade)",
      "Humidity": "हवेतील आद्रता",
      "Wind": "वारा",
      "Rain 7d": "पाऊस (7 दिवस)",
      "Est. market value": "अंदाजित बाजार मूल्य",
      "Model conf.": "मॉडेल अचूकता",
      "Status": "स्थिती",
      "pH": "सामू (pH)",
      "Farmer login": "शेतकरी लॉगिन",
      "Username": "वापरकर्ता नाव",
      "Password": "पासवर्ड",
      "Sign in →": "साइन इन करा →",
      "Register a farmer account": "नवीन शेतकरी नोंदणी करा",
      "Every decision on your farm, backed by AI.": "तुमच्या शेतातील प्रत्येक निर्णय, AI च्या साथीने.",
      "Edge AI": "एज AI",
      "Market Intelligence": "बाजार माहिती",
      "DSS": "निर्णय सहाय्य प्रणाली (DSS)",
      "WEATHER AI · SYNCED": "हवामान AI · अपडेटेड",
      "MANDI API ONLINE": "मंडी API चालू",
      "Execute In-Silico Forecast": "सिम्युलेशन अंदाज चालवा",
      "Run Scenario →": "सिम्युलेशन सुरू करा →",
      "Review CNN saliency map →": "CNN मॅप पाहा →",
      "Language": "भाषा"
    }
  };

  function getSavedLanguage() {
    return localStorage.getItem("agri_lang") || "en";
  }

  function setLanguage(lang) {
    if (!TRANSLATIONS[lang]) lang = "en";
    localStorage.setItem("agri_lang", lang);
    document.cookie = "agri_lang=" + lang + "; path=/; max-age=31536000";

    var dict = TRANSLATIONS[lang];

    // Translate all elements with data-i18n
    var nodes = document.querySelectorAll("[data-i18n]");
    nodes.forEach(function (el) {
      var key = el.getAttribute("data-i18n");
      if (dict[key]) {
        el.textContent = dict[key];
      }
    });

    // Auto-translate navigation text and common headings
    var navLinks = document.querySelectorAll(".nav a, .nav .section, .lbl, .brand-sub, .topbar .status-chip");
    navLinks.forEach(function (el) {
      var text = el.textContent.trim();
      // Look up text or cleaned text
      for (var enKey in TRANSLATIONS.en) {
        if (text === enKey || text === TRANSLATIONS.hi[enKey] || text === TRANSLATIONS.mr[enKey]) {
          if (dict[enKey]) {
            // Retain SVG icons if present
            var svg = el.querySelector("svg");
            var dot = el.querySelector(".dot");
            if (svg || dot) {
              el.childNodes.forEach(function(child) {
                if (child.nodeType === Node.TEXT_NODE && child.textContent.trim()) {
                  child.textContent = " " + dict[enKey];
                }
              });
            } else {
              el.textContent = dict[enKey];
            }
          }
          break;
        }
      }
    });

    // Sync select element
    var selectors = document.querySelectorAll(".lang-select");
    selectors.forEach(function (s) { s.value = lang; });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var currentLang = getSavedLanguage();

    var selectors = document.querySelectorAll(".lang-select");
    selectors.forEach(function (select) {
      select.value = currentLang;
      select.addEventListener("change", function (e) {
        setLanguage(e.target.value);
      });
    });

    if (currentLang !== "en") {
      setLanguage(currentLang);
    }
  });

  window.AgriI18n = {
    setLanguage: setLanguage,
    getSavedLanguage: getSavedLanguage
  };
})();
