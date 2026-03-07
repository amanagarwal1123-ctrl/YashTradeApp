import AsyncStorage from '@react-native-async-storage/async-storage';

export type Language = 'en' | 'hi' | 'pa';

const T: Record<string, Record<Language, string>> = {
  // Navigation
  home: { en: 'Home', hi: 'होम', pa: 'ਹੋਮ' },
  feed: { en: 'Feed', hi: 'फीड', pa: 'ਫੀਡ' },
  calculator: { en: 'Calculator', hi: 'कैलकुलेटर', pa: 'ਕੈਲਕੁਲੇਟਰ' },
  profile: { en: 'Profile', hi: 'प्रोफाइल', pa: 'ਪ੍ਰੋਫਾਈਲ' },

  // Home
  welcome_back: { en: 'Welcome back,', hi: 'वापस स्वागत है,', pa: 'ਵਾਪਸ ਸਵਾਗਤ ਹੈ,' },
  silver: { en: 'SILVER', hi: 'चांदी', pa: 'ਚਾਂਦੀ' },
  gold: { en: 'GOLD', hi: 'सोना', pa: 'ਸੋਨਾ' },
  per_gram: { en: 'per gram', hi: 'प्रति ग्राम', pa: 'ਪ੍ਰਤੀ ਗ੍ਰਾਮ' },
  request_call: { en: 'Request Call', hi: 'कॉल अनुरोध', pa: 'ਕਾਲ ਬੇਨਤੀ' },
  video_call: { en: 'Video Call', hi: 'वीडियो कॉल', pa: 'ਵੀਡੀਓ ਕਾਲ' },
  my_rewards: { en: 'My Rewards', hi: 'मेरे रिवॉर्ड्स', pa: 'ਮੇਰੇ ਇਨਾਮ' },
  ai_assistant: { en: 'AI Assistant', hi: 'AI सहायक', pa: 'AI ਸਹਾਇਕ' },
  silver_guide: { en: 'Silver Guide', hi: 'चांदी गाइड', pa: 'ਚਾਂਦੀ ਗਾਈਡ' },
  highlights: { en: 'HIGHLIGHTS', hi: 'हाइलाइट्स', pa: 'ਹਾਈਲਾਈਟਸ' },
  latest_collection: { en: 'LATEST COLLECTION', hi: 'नवीनतम संग्रह', pa: 'ਨਵੀਨਤਮ ਸੰਗ੍ਰਹਿ' },
  see_all: { en: 'See All', hi: 'सभी देखें', pa: 'ਸਭ ਵੇਖੋ' },
  ask_price: { en: 'Ask Price', hi: 'कीमत पूछें', pa: 'ਕੀਮਤ ਪੁੱਛੋ' },

  // Calculator
  silver_calculator: { en: 'Silver Calculator', hi: 'चांदी कैलकुलेटर', pa: 'ਚਾਂਦੀ ਕੈਲਕੁਲੇਟਰ' },
  single_item: { en: 'Single Item', hi: 'एक आइटम', pa: 'ਇੱਕ ਆਈਟਮ' },
  multi_item_bill: { en: 'Multi Item Bill', hi: 'बहु-आइटम बिल', pa: 'ਬਹੁ-ਆਈਟਮ ਬਿਲ' },
  item_name: { en: 'Item Name', hi: 'आइटम नाम', pa: 'ਆਈਟਮ ਨਾਮ' },
  weight_grams: { en: 'Weight (grams)', hi: 'वजन (ग्राम)', pa: 'ਭਾਰ (ਗ੍ਰਾਮ)' },
  rate_per_gram: { en: 'Rate (₹/gram)', hi: 'दर (₹/ग्राम)', pa: 'ਦਰ (₹/ਗ੍ਰਾਮ)' },
  making: { en: 'Making (₹)', hi: 'बनावट (₹)', pa: 'ਬਣਾਵਟ (₹)' },
  discount: { en: 'Discount (₹)', hi: 'छूट (₹)', pa: 'ਛੂਟ (₹)' },
  base_amount: { en: 'Base Amount', hi: 'मूल राशि', pa: 'ਮੂਲ ਰਕਮ' },
  total: { en: 'TOTAL', hi: 'कुल', pa: 'ਕੁੱਲ' },
  grand_total: { en: 'GRAND TOTAL', hi: 'कुल योग', pa: 'ਕੁੱਲ ਜੋੜ' },
  clear_all: { en: 'Clear All', hi: 'सब साफ करें', pa: 'ਸਭ ਸਾਫ਼ ਕਰੋ' },
  add_item: { en: 'Add Item', hi: 'आइटम जोड़ें', pa: 'ਆਈਟਮ ਜੋੜੋ' },
  subtotal: { en: 'Subtotal', hi: 'उप-योग', pa: 'ਉਪ-ਜੋੜ' },

  // Profile
  account: { en: 'ACCOUNT', hi: 'खाता', pa: 'ਖਾਤਾ' },
  tools: { en: 'TOOLS', hi: 'उपकरण', pa: 'ਸੰਦ' },
  contact: { en: 'CONTACT', hi: 'संपर्क', pa: 'ਸੰਪਰਕ' },
  admin: { en: 'ADMIN', hi: 'एडमिन', pa: 'ਐਡਮਿਨ' },
  my_requests: { en: 'My Requests', hi: 'मेरे अनुरोध', pa: 'ਮੇਰੀਆਂ ਬੇਨਤੀਆਂ' },
  wishlist: { en: 'Wishlist', hi: 'विशलिस्ट', pa: 'ਵਿਸ਼ਲਿਸਟ' },
  rewards_history: { en: 'Rewards History', hi: 'रिवॉर्ड इतिहास', pa: 'ਇਨਾਮ ਇਤਿਹਾਸ' },
  silver_knowledge: { en: 'Silver Knowledge', hi: 'चांदी ज्ञान', pa: 'ਚਾਂਦੀ ਗਿਆਨ' },
  admin_dashboard: { en: 'Admin Dashboard', hi: 'एडमिन डैशबोर्ड', pa: 'ਐਡਮਿਨ ਡੈਸ਼ਬੋਰਡ' },
  executive_panel: { en: 'Executive Panel', hi: 'एक्ज़ीक्यूटिव पैनल', pa: 'ਐਗਜ਼ੈਕਟਿਵ ਪੈਨਲ' },
  logout: { en: 'Logout', hi: 'लॉग आउट', pa: 'ਲੌਗ ਆਊਟ' },
  recent_requests: { en: 'RECENT REQUESTS', hi: 'हाल के अनुरोध', pa: 'ਤਾਜ਼ਾ ਬੇਨਤੀਆਂ' },
  reward_points: { en: 'Reward Points', hi: 'रिवॉर्ड पॉइंट्स', pa: 'ਇਨਾਮ ਪੁਆਇੰਟ' },
  language: { en: 'Language', hi: 'भाषा', pa: 'ਭਾਸ਼ਾ' },
  settings: { en: 'SETTINGS', hi: 'सेटिंग्स', pa: 'ਸੈਟਿੰਗਾਂ' },

  // Request
  contact_us: { en: 'Contact Us', hi: 'संपर्क करें', pa: 'ਸੰਪਰਕ ਕਰੋ' },
  request_type: { en: 'REQUEST TYPE', hi: 'अनुरोध प्रकार', pa: 'ਬੇਨਤੀ ਦੀ ਕਿਸਮ' },
  category_interest: { en: 'CATEGORY OF INTEREST', hi: 'रुचि की श्रेणी', pa: 'ਦਿਲਚਸਪੀ ਦੀ ਸ਼੍ਰੇਣੀ' },
  preferred_time: { en: 'PREFERRED TIME', hi: 'पसंदीदा समय', pa: 'ਤਰਜੀਹੀ ਸਮਾਂ' },
  notes_optional: { en: 'NOTES (OPTIONAL)', hi: 'नोट्स (वैकल्पिक)', pa: 'ਨੋਟਸ (ਵਿਕਲਪਿਕ)' },
  send_request: { en: 'SEND REQUEST', hi: 'अनुरोध भेजें', pa: 'ਬੇਨਤੀ ਭੇਜੋ' },

  // Rewards
  how_to_earn: { en: 'HOW TO EARN', hi: 'कैसे कमाएं', pa: 'ਕਿਵੇਂ ਕਮਾਓ' },
  recent_activity: { en: 'RECENT ACTIVITY', hi: 'हाल की गतिविधि', pa: 'ਤਾਜ਼ਾ ਗਤੀਵਿਧੀ' },

  // Knowledge
  education_subtitle: { en: 'Education content you can show your customers', hi: 'ग्राहकों को दिखाने योग्य शैक्षिक सामग्री', pa: 'ਗਾਹਕਾਂ ਨੂੰ ਦਿਖਾਉਣ ਯੋਗ ਸਿੱਖਿਆ ਸਮੱਗਰੀ' },

  // Feed
  collection: { en: 'Collection', hi: 'संग्रह', pa: 'ਸੰਗ੍ਰਹਿ' },
  search_products: { en: 'Search products...', hi: 'उत्पाद खोजें...', pa: 'ਉਤਪਾਦ ਖੋਜੋ...' },
  no_products: { en: 'No products found', hi: 'कोई उत्पाद नहीं मिला', pa: 'ਕੋਈ ਉਤਪਾਦ ਨਹੀਂ ਮਿਲਿਆ' },

  // AI
  ai_title: { en: 'Yash Trade AI', hi: 'Yash Trade AI', pa: 'Yash Trade AI' },
  ai_subtitle: { en: 'Ask me about selling tips, silver knowledge, trends, and customer education content.', hi: 'मुझसे बिक्री टिप्स, चांदी ज्ञान, ट्रेंड और ग्राहक शिक्षा सामग्री के बारे में पूछें।', pa: 'ਮੈਨੂੰ ਵੇਚਣ ਦੇ ਸੁਝਾਅ, ਚਾਂਦੀ ਗਿਆਨ, ਰੁਝਾਨ ਅਤੇ ਗਾਹਕ ਸਿੱਖਿਆ ਬਾਰੇ ਪੁੱਛੋ।' },
  ai_placeholder: { en: 'Ask anything about jewellery business...', hi: 'ज्वेलरी व्यापार के बारे में कुछ भी पूछें...', pa: 'ਗਹਿਣਿਆਂ ਦੇ ਕਾਰੋਬਾਰ ਬਾਰੇ ਕੁਝ ਵੀ ਪੁੱਛੋ...' },

  // Executive
  exec_panel: { en: 'Request Management', hi: 'अनुरोध प्रबंधन', pa: 'ਬੇਨਤੀ ਪ੍ਰਬੰਧਨ' },
  all_requests: { en: 'ALL REQUESTS', hi: 'सभी अनुरोध', pa: 'ਸਾਰੀਆਂ ਬੇਨਤੀਆਂ' },
  pending: { en: 'Pending', hi: 'लंबित', pa: 'ਬਕਾਇਆ' },
  in_progress: { en: 'In Progress', hi: 'प्रगति में', pa: 'ਜਾਰੀ ਹੈ' },
  contacted: { en: 'Contacted', hi: 'संपर्क किया', pa: 'ਸੰਪਰਕ ਕੀਤਾ' },
  resolved: { en: 'Resolved', hi: 'हल किया', pa: 'ਹੱਲ ਕੀਤਾ' },
  no_response: { en: 'No Response', hi: 'कोई जवाब नहीं', pa: 'ਕੋਈ ਜਵਾਬ ਨਹੀਂ' },
};

export function t(key: string, lang: Language = 'en'): string {
  return T[key]?.[lang] || T[key]?.en || key;
}

export const LANGUAGE_OPTIONS: { key: Language; label: string; native: string }[] = [
  { key: 'en', label: 'English', native: 'English' },
  { key: 'hi', label: 'Hindi', native: 'हिंदी' },
  { key: 'pa', label: 'Punjabi', native: 'ਪੰਜਾਬੀ' },
];

export async function getSavedLanguage(): Promise<Language> {
  try {
    const lang = await AsyncStorage.getItem('app_language');
    if (lang === 'hi' || lang === 'pa') return lang;
  } catch {}
  return 'en';
}

export async function saveLanguage(lang: Language) {
  try { await AsyncStorage.setItem('app_language', lang); } catch {}
}
