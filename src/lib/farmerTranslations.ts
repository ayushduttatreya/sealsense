export type FarmerLanguage = 'en' | 'hi';

export interface FarmerStrings {
  appName: string;
  appSubtitle: string;
  switchTechDashboard: string;
  switchToFarmer: string;
  
  // Navigation
  navHome: string;
  navStorage: string;
  navAlerts: string;
  navHelp: string;

  // Header & Status
  namaste: string;
  greetingMorning: string;
  greetingAfternoon: string;
  greetingEvening: string;
  monitoringActive: string;
  monitoringStale: string;
  monitoringOffline: string;
  monitoringPaused: string;
  lastUpdated: string;
  secondsAgo: string;
  minutesAgo: string;
  hoursAgo: string;

  // Overall Health
  grainSafeTitle: string;
  grainSafeDesc: string;
  grainAttentionTitle: string;
  grainAttentionDesc: string;
  grainCriticalTitle: string;
  grainCriticalDesc: string;
  grainOfflineTitle: string;
  grainOfflineDesc: string;

  // Sensor Cards
  temperature: string;
  tempNormalDesc: string;
  tempWarmDesc: string;
  tempColdDesc: string;

  airHumidity: string;
  airHumidityNote: string;
  humidityGoodDesc: string;
  humidityHighDesc: string;

  airFreshness: string;
  co2NormalDesc: string;
  co2ElevatedDesc: string;
  co2CriticalDesc: string;

  soundActivity: string;
  soundNormalDesc: string;
  soundElevatedDesc: string;
  soundDisclaimer: string;

  // Buttons & Actions
  listenAudio: string;
  stopAudio: string;
  markInspected: string;
  viewDetails: string;
  refreshData: string;
  inspectStorage: string;
  inspectionChecklist: string;

  // Demo Alert Bar
  demoAlertPrompt: string;
  triggerDemoBtn: string;
  resetDemoBtn: string;
  demoActiveBadge: string;
  demoBannerText: string;

  // Storage Screen
  myStorageTitle: string;
  selectStorageArea: string;
  silo1Wheat: string;
  silo2Barley: string;
  silo3Corn: string;
  sensorHealth: string;
  hardwareStatus: string;
  realHardware: string;
  simulatedDemo: string;
  historicalTrend24h: string;
  temperatureTrend: string;
  humidityTrend: string;
  co2Trend: string;
  noHistoryInWindow: string;

  // Alerts Screen
  alertsTitle: string;
  activeAlertsCount: string;
  noActiveAlerts: string;
  allClearMessage: string;
  simulatedAlertTitle: string;
  simulatedAlertDesc: string;
  alertExplanationHeader: string;
  alertStepsHeader: string;
  alertStep1: string;
  alertStep2: string;
  alertStep3: string;
  alertStep4: string;
  inspectedSuccess: string;
  inspectorNameLabel: string;
  inspectionNotesPlaceholder: string;
  submitInspection: string;
  cancel: string;

  // Help & Education
  helpTitle: string;
  educationSection: string;
  faq1Q: string;
  faq1A: string;
  faq2Q: string;
  faq2A: string;
  faq3Q: string;
  faq3A: string;
  troubleshootingSection: string;
  deviceOfflineHelp: string;
  deviceStaleHelp: string;
  contactSupport: string;
  supportPhone: string;
}

export const translations: Record<FarmerLanguage, FarmerStrings> = {
  en: {
    appName: 'SealSense Krishi',
    appSubtitle: 'Smart Grain Storage Assistant',
    switchTechDashboard: 'Technical Console',
    switchToFarmer: 'Farmer View',

    // Navigation
    navHome: 'Home',
    navStorage: 'My Storage',
    navAlerts: 'Alerts',
    navHelp: 'Help & Guide',

    // Header & Status
    namaste: 'Namaste, Kisan Mitra',
    greetingMorning: 'Good Morning',
    greetingAfternoon: 'Good Afternoon',
    greetingEvening: 'Good Evening',
    monitoringActive: 'Active & Protecting',
    monitoringStale: 'Slow Signal (Checking)',
    monitoringOffline: 'Sensor Node Disconnected',
    monitoringPaused: 'Monitoring Paused',
    lastUpdated: 'Updated',
    secondsAgo: 'sec ago',
    minutesAgo: 'min ago',
    hoursAgo: 'hrs ago',

    // Overall Health
    grainSafeTitle: 'Grain Storage is Safe & Normal',
    grainSafeDesc: 'All temperature, air, and acoustic sensors are within healthy ranges. No spoilage or abnormal sound detected.',
    grainAttentionTitle: 'Attention Recommended in Storage',
    grainAttentionDesc: 'One or more storage measurements differ from recent normal levels. A routine physical inspection is advised.',
    grainCriticalTitle: 'Important Storage Warning',
    grainCriticalDesc: 'Elevated CO₂ and high moisture in storage air. Immediate aeration and visual grain inspection required.',
    grainOfflineTitle: 'Sensor Link Offline',
    grainOfflineDesc: 'The wireless sensor node has not reported recently. Please check USB power connection on the sensor unit.',

    // Sensor Cards
    temperature: 'Storage Temperature',
    tempNormalDesc: 'Cool & stable — ideal for grain storage',
    tempWarmDesc: 'Slightly warm — keep aeration fan ready',
    tempColdDesc: 'Cold — safe against insect breeding',

    airHumidity: 'Air Relative Humidity',
    airHumidityNote: 'Air moisture — NOT grain moisture content',
    humidityGoodDesc: 'Dry air circulation — grain is resting safe',
    humidityHighDesc: 'High air dampness — check silo roof and seal',

    airFreshness: 'Air Freshness (CO₂)',
    co2NormalDesc: 'Fresh air — grain is dormant and breathing normally',
    co2ElevatedDesc: 'CO₂ rising — grain or biological activity present',
    co2CriticalDesc: 'High CO₂ buildup — ventilate immediately',

    soundActivity: 'Acoustic Sound Monitoring',
    soundNormalDesc: 'Quiet & calm — continuous listening active',
    soundElevatedDesc: 'Unusual noise registered — manual check advised',
    soundDisclaimer: 'Sound activity is an acoustic indicator, NOT confirmed insect proof.',

    // Buttons & Actions
    listenAudio: 'Listen to Advisory',
    stopAudio: 'Stop Audio',
    markInspected: 'Mark as Inspected',
    viewDetails: 'View Details & Action',
    refreshData: 'Refresh',
    inspectStorage: 'Inspect Grain',
    inspectionChecklist: 'Safe Storage Checklist',

    // Demo Alert Bar
    demoAlertPrompt: 'Judges Demo Mode:',
    triggerDemoBtn: 'Try Sample Alert',
    resetDemoBtn: 'Clear Demo Alert',
    demoActiveBadge: 'SIMULATED SAMPLE',
    demoBannerText: 'You are viewing a demonstration alert. Actual hardware data is completely protected.',

    // Storage Screen
    myStorageTitle: 'My Grain Silos & Storage',
    selectStorageArea: 'Select Storage Area',
    silo1Wheat: 'Silo 1 — Primary Wheat Storage',
    silo2Barley: 'Silo 2 — Barley Storage',
    silo3Corn: 'Silo 3 — Corn Storage',
    sensorHealth: 'Sensor Equipment Status',
    hardwareStatus: 'Physical Hardware',
    realHardware: 'REAL HARDWARE (ESP32 via USB Serial)',
    simulatedDemo: 'SIMULATED DEMO NODE',
    historicalTrend24h: 'Simple 24-Hour Trend',
    temperatureTrend: 'Temperature Trend',
    humidityTrend: 'Air Humidity Trend',
    co2Trend: 'CO₂ Air Freshness Trend',
    noHistoryInWindow: 'No telemetry packets in this time window. Node is currently silent.',

    // Alerts Screen
    alertsTitle: 'Storage Advisories & Alerts',
    activeAlertsCount: 'Active Advisories',
    noActiveAlerts: 'No Active Warnings',
    allClearMessage: 'All storage areas are calm. You will receive an immediate notification if conditions shift.',
    simulatedAlertTitle: 'Unusual Sound Activity Heard in Storage Area',
    simulatedAlertDesc: 'The continuous listening sensor registered a sound pattern differing from background storage noise.',
    alertExplanationHeader: 'What happened?',
    alertStepsHeader: 'Recommended Inspection Steps for the Farmer:',
    alertStep1: 'Step 1: Check grain temperature with a spear thermometer at top apex.',
    alertStep2: 'Step 2: Look for moisture condensation on inner roof walls or hatch.',
    alertStep3: 'Step 3: Sieve a 1 kg sample from top and discharge gate into a white tray.',
    alertStep4: 'Step 4: Check if silo ventilation fan needs to run for 2 hours during dry afternoon.',
    inspectedSuccess: 'Storage area marked as inspected and safe.',
    inspectorNameLabel: 'Inspector / Farmer Name',
    inspectionNotesPlaceholder: 'e.g. Checked Silo 1 top hatch. Grain dry and cool. No insects found.',
    submitInspection: 'Confirm Inspection Done',
    cancel: 'Cancel',

    // Help & Education
    helpTitle: 'Farmer Advisory & Sensor Guide',
    educationSection: 'Understanding Your Storage Sensors (Simple Guide)',
    faq1Q: 'Why does CO₂ rise if grain begins to spoil?',
    faq1A: 'Grain is alive! When grain gets damp or insects enter, they breathe faster and produce Carbon Dioxide (CO₂). By measuring CO₂ rise early, SealSense alerts you days before grain turns sour or visible mold develops.',
    faq2Q: 'Is Air Humidity the same as Grain Moisture?',
    faq2A: 'No! The sensor measures humidity of the AIR inside the silo headspace. Grain moisture is measured with a grain probe. High air humidity means the grain could absorb moisture from the air if not ventilated.',
    faq3Q: 'How does Acoustic Sound sensing work?',
    faq3A: 'Insects make tiny scraping sounds when they move or feed inside grain kernels. SealSense uses a sensitive acoustic microphone to listen. A sound alert means you should take a sample and inspect, NOT spray pesticides blindly.',
    troubleshootingSection: 'Sensor Troubleshooting',
    deviceOfflineHelp: 'If "Sensor Node Disconnected" shows: Check that the ESP32 USB cable is securely plugged into the power adapter or computer. Ensure power switch is on.',
    deviceStaleHelp: 'If "Slow Signal" shows: The node sends readings every few seconds. If delayed by more than 1 minute, the system marks data as stale until fresh data arrives.',
    contactSupport: 'Agricultural Help & Storage Support',
    supportPhone: 'National Toll-Free Storage Advisory: 1800-180-1551 (Kisan Call Centre)',
  },

  hi: {
    appName: 'सीलसेंस कृषि',
    appSubtitle: 'स्मार्ट अनाज भंडारण सहायक',
    switchTechDashboard: 'तकनीकी कंसोल',
    switchToFarmer: 'किसान दृश्य',

    // Navigation
    navHome: 'मुख्य पृष्ठ',
    navStorage: 'मेरा भंडारण',
    navAlerts: 'चेतावनियाँ',
    navHelp: 'सहायता व मार्गदर्शिका',

    // Header & Status
    namaste: 'नमस्ते, किसान भाई',
    greetingMorning: 'शुभ प्रभात',
    greetingAfternoon: 'शुभ दोपहर',
    greetingEvening: 'शुभ संध्या',
    monitoringActive: 'निगरानी सक्रिय व सुरक्षित',
    monitoringStale: 'धीमा सिग्नल (जाँच जारी)',
    monitoringOffline: 'सेंसर डिस्कनेक्ट है',
    monitoringPaused: 'निगरानी रुकी हुई है',
    lastUpdated: 'अपडेट',
    secondsAgo: 'सेकंड पहले',
    minutesAgo: 'मिनट पहले',
    hoursAgo: 'घंटे पहले',

    // Overall Health
    grainSafeTitle: 'अनाज भंडारण पूरी तरह सुरक्षित है',
    grainSafeDesc: 'तापमान, हवा और ध्वनि के सभी सेंसर सामान्य सीमा में हैं। अनाज में किसी खराबी या असामान्य हलचल का कोई संकेत नहीं है।',
    grainAttentionTitle: 'भंडारण में ध्यान देने की आवश्यकता है',
    grainAttentionDesc: 'कुछ सेंसरों में हाल के सामान्य स्तर से बदलाव देखा गया है। कृपया गोदाम या साइलो का भौतिक निरीक्षण करें।',
    grainCriticalTitle: 'महत्वपूर्ण चेतावनी: तुरंत जाँच करें',
    grainCriticalDesc: 'हवा में CO₂ और नमी में असामान्य वृद्धि देखी गई है। तुरंत वेंटिलेशन चालू करें और अनाज की जाँच करें।',
    grainOfflineTitle: 'सेंसर संपर्क टूटा हुआ है',
    grainOfflineDesc: 'सेंसर डिवाइस से पिछले कुछ समय से डेटा प्राप्त नहीं हुआ है। कृपया यूएसबी पावर केबल की जाँच करें।',

    // Sensor Cards
    temperature: 'भंडारण तापमान',
    tempNormalDesc: 'ठंडा व स्थिर — अनाज भंडारण के लिए सर्वोत्तम',
    tempWarmDesc: 'हल्का गर्म — पंखा चलाने की तैयारी रखें',
    tempColdDesc: 'ठंडा — कीटों की वृद्धि रोकने में सुरक्षित',

    airHumidity: 'हवा की नमी (आर्द्रता)',
    airHumidityNote: 'हवा की नमी — यह अनाज की नमी (दाने की नमी) नहीं है',
    humidityGoodDesc: 'शुष्क हवा — अनाज सुरक्षित है',
    humidityHighDesc: 'हवा में नमी अधिक है — साइलो की छत व सील जाँचें',

    airFreshness: 'हवा की ताजगी (CO₂)',
    co2NormalDesc: 'ताजी हवा — अनाज सामान्य रूप से सांस ले रहा है',
    co2ElevatedDesc: 'CO₂ बढ़ रही है — अनाज या जैविक गतिविधि के संकेत',
    co2CriticalDesc: 'CO₂ बहुत अधिक — तुरंत हवा निकासी करें',

    soundActivity: 'ध्वनि निगरानी (माइक्रोफोन)',
    soundNormalDesc: 'शांत व सामान्य — सतत निगरानी चालू है',
    soundElevatedDesc: 'असामान्य आवाज सुनी गई — जाँच की सलाह',
    soundDisclaimer: 'ध्वनि केवल एक संकेत है, यह कीटों की पुष्टि नहीं है।',

    // Buttons & Actions
    listenAudio: 'सलाह सुनें (आवाज़)',
    stopAudio: 'आवाज़ रोकें',
    markInspected: 'निरीक्षण पूरा हुआ',
    viewDetails: 'विवरण व आवश्यक कदम देखें',
    refreshData: 'ताज़ा करें',
    inspectStorage: 'अनाज की जाँच करें',
    inspectionChecklist: 'सुरक्षित भंडारण चेकलिस्ट',

    // Demo Alert Bar
    demoAlertPrompt: 'जजों के लिए डेमो मोड:',
    triggerDemoBtn: 'नमूना चेतावनी देखें',
    resetDemoBtn: 'डेमो रीसेट करें',
    demoActiveBadge: 'नमूना प्रदर्शन',
    demoBannerText: 'आप एक नमूना चेतावनी देख रहे हैं। असली हार्डवेयर डेटा पूरी तरह सुरक्षित है।',

    // Storage Screen
    myStorageTitle: 'मेरे अनाज साइलो व गोदाम',
    selectStorageArea: 'भंडारण क्षेत्र चुनें',
    silo1Wheat: 'साइलो 1 — मुख्य गेहूं भंडारण',
    silo2Barley: 'साइलो 2 — जौ भंडारण',
    silo3Corn: 'साइलो 3 — मक्का भंडारण',
    sensorHealth: 'सेंसर उपकरण की स्थिति',
    hardwareStatus: 'भौतिक हार्डवेयर',
    realHardware: 'असली हार्डवेयर (ESP32 यूएसबी सीरियल)',
    simulatedDemo: 'सिम्युलेटेड डेमो नोड',
    historicalTrend24h: 'सरल 24 घंटे का रुझान',
    temperatureTrend: 'तापमान का रुझान',
    humidityTrend: 'हवा की नमी का रुझान',
    co2Trend: 'हवा की ताजगी (CO₂) का रुझान',
    noHistoryInWindow: 'इस समय सीमा में कोई डेटा नहीं है। नोड अभी बंद है।',

    // Alerts Screen
    alertsTitle: 'भंडारण चेतावनियाँ व सलाह',
    activeAlertsCount: 'सक्रिय चेतावनियाँ',
    noActiveAlerts: 'कोई सक्रिय चेतावनी नहीं',
    allClearMessage: 'सभी भंडारण क्षेत्र शांत व सुरक्षित हैं। स्थिति बदलने पर तुरंत सूचना मिलेगी।',
    simulatedAlertTitle: 'अनाज साइलो में असामान्य आवाज सुनी गई',
    simulatedAlertDesc: 'सेंसर ने पृष्ठभूमि शोर से अलग ध्वनि पैटर्न दर्ज किया है।',
    alertExplanationHeader: 'क्या हुआ?',
    alertStepsHeader: 'किसान भाई के लिए अनुशंसित जाँच कदम:',
    alertStep1: 'कदम 1: थर्मामीटर से अनाज की ऊपरी परत का तापमान जाँचें।',
    alertStep2: 'कदम 2: साइलो की भीतरी छत या ढक्कन पर पानी की बूंदें देखें।',
    alertStep3: 'कदम 3: 1 किलो दाने का नमूना लेकर सफेद ट्रे में छानकर कीट देखें।',
    alertStep4: 'कदम 4: दोपहर की सूखी धूप में 2 घंटे के लिए साइलो का पंखा चलाएं।',
    inspectedSuccess: 'भंडारण क्षेत्र का निरीक्षण पूरा और सुरक्षित दर्ज किया गया।',
    inspectorNameLabel: 'निरीक्षक / किसान का नाम',
    inspectionNotesPlaceholder: 'जैसे: साइलो 1 का ढक्कन खोलकर देखा। अनाज सूखा व ठंडा है। कोई कीट नहीं मिला।',
    submitInspection: 'निरीक्षण पूरा दर्ज करें',
    cancel: 'रद्द करें',

    // Help & Education
    helpTitle: 'किसान सलाह व सेंसर गाइड',
    educationSection: 'सेंसर को समझें (सरल गाइड)',
    faq1Q: 'अनाज खराब होने पर CO₂ क्यों बढ़ती है?',
    faq1A: 'अनाज सजीव है! जब अनाज में सीलन आती है या कीड़े लगते हैं, तो वे तेजी से सांस लेते हैं और कार्बन डाइऑक्साइड (CO₂) छोड़ते हैं। SealSense इसे पहले ही पहचानकर फफूंद लगने से कई दिन पहले सचेत कर देता है।',
    faq2Q: 'क्या हवा की नमी और दाने की नमी एक ही है?',
    faq2A: 'नहीं! यह सेंसर साइलो के अंदर की हवा की नमी नापता है। दाने की नमी अलग मीटर से नापी जाती है। यदि हवा में नमी ज्यादा हो तो अनाज हवा से नमी सोख सकता है।',
    faq3Q: 'ध्वनि सेंसर (माइक्रोफोन) कैसे मदद करता है?',
    faq3A: 'कीड़े जब दाने के अंदर चलते या खाते हैं, तो बहुत धीमी आवाज करते हैं। SealSense का माइक्रोफोन उसे सुनता है। आवाज का मतलब है कि जाकर दाना देखें, बिना सोचे कीटनाशक न डालें।',
    troubleshootingSection: 'सेंसर की समस्या समाधान',
    deviceOfflineHelp: 'यदि "सेंसर डिस्कनेक्ट" दिखे: जाँचें कि ESP32 की यूएसबी केबल चार्जर या कंप्यूटर में सही लगी है और बिजली चालू है।',
    deviceStaleHelp: 'यदि "धीमा सिग्नल" दिखे: नोड हर कुछ सेकंड में डेटा भेजता है। 1 मिनट से अधिक देरी होने पर सिस्टम ताज़ा डेटा आने तक प्रतीक्षा करता है।',
    contactSupport: 'कृषि व भंडारण सहायता केंद्र',
    supportPhone: 'राष्ट्रीय किसान कॉल सेंटर (टोल-फ्री): 1800-180-1551',
  },
};
