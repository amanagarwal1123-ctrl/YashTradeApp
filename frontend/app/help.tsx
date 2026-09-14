import React from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Linking } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import Constants from 'expo-constants';
import { Colors, Spacing, FontSize } from '../src/theme';
import { useLang } from '../src/context/LanguageContext';

const ENROLLMENT_URL = Constants.expoConfig?.extra?.enrollmentUrl || '';
const PRIVACY_URL = process.env.EXPO_PUBLIC_PRIVACY_URL || 'https://yash-register.emergent.host/privacy';

const T: Record<string, Record<string, string>> = {
  en: {
    title: 'Help',
    signInTitle: 'Signing in',
    signInBody: 'Enter your registered 10-digit mobile number and tap GET OTP. A one-time password arrives by SMS; enter it on the next screen. The app is for jewellers verified by Yash Ornaments.',
    registerTitle: 'Not registered yet?',
    registerBody: 'Enrol on the Yash Ornaments website and verify your phone number first, then sign in here with the same number.',
    enroll: 'ENROL ON WEBSITE',
    otpTitle: "Didn't receive the OTP?",
    otpBody: 'Check the number, wait 60 seconds before requesting again and make sure the phone has network coverage. Each code is valid for 10 minutes.',
    privacyTitle: 'Privacy & your data',
    privacyBody: 'The AI assistant is optional: nothing you write is sent to the AI provider until you allow it, and you can withdraw under Profile → AI Data Sharing. You can delete your account under Profile → Delete My Account.',
    privacy: 'Privacy Policy',
    reviewTitle: 'App review access',
    reviewBody: 'For Google Play and App Store review teams only. Sign in with the Reviewer ID and Access key given in the store review form.',
    reviewOpen: 'Open reviewer sign-in',
  },
  hi: {
    title: 'सहायता',
    signInTitle: 'लॉगिन कैसे करें',
    signInBody: 'अपना रजिस्टर्ड 10-अंकों का मोबाइल नंबर दर्ज करें और OTP प्राप्त करें दबाएँ। SMS से मिला वन-टाइम पासवर्ड अगली स्क्रीन पर दर्ज करें। यह ऐप Yash Ornaments द्वारा सत्यापित ज्वेलर्स के लिए है।',
    registerTitle: 'अभी रजिस्टर्ड नहीं हैं?',
    registerBody: 'पहले Yash Ornaments वेबसाइट पर एनरोल करें और फोन नंबर वेरिफाई करें, फिर उसी नंबर से यहाँ लॉगिन करें।',
    enroll: 'वेबसाइट पर एनरोल करें',
    otpTitle: 'OTP नहीं मिला?',
    otpBody: 'नंबर जाँचें, दोबारा माँगने से पहले 60 सेकंड रुकें और फोन में नेटवर्क होना सुनिश्चित करें। हर कोड 10 मिनट तक मान्य है।',
    privacyTitle: 'गोपनीयता और आपका डेटा',
    privacyBody: 'AI असिस्टेंट वैकल्पिक है: आपकी अनुमति के बिना कुछ भी AI प्रोवाइडर को नहीं भेजा जाता, और आप प्रोफ़ाइल → AI Data Sharing में अनुमति वापस ले सकते हैं। प्रोफ़ाइल → Delete My Account से खाता हटाया जा सकता है।',
    privacy: 'गोपनीयता नीति',
    reviewTitle: 'App review access',
    reviewBody: 'केवल Google Play और App Store समीक्षा टीमों के लिए। स्टोर रिव्यू फ़ॉर्म में दिए गए Reviewer ID और Access key से साइन इन करें।',
    reviewOpen: 'रिव्यूअर साइन-इन खोलें',
  },
  pa: {
    title: 'ਮਦਦ',
    signInTitle: 'ਲੌਗਿਨ ਕਿਵੇਂ ਕਰੀਏ',
    signInBody: 'ਆਪਣਾ ਰਜਿਸਟਰਡ 10-ਅੰਕਾਂ ਦਾ ਮੋਬਾਈਲ ਨੰਬਰ ਦਰਜ ਕਰੋ ਅਤੇ OTP ਪ੍ਰਾਪਤ ਕਰੋ ਦਬਾਓ। SMS ਰਾਹੀਂ ਮਿਲਿਆ ਵਨ-ਟਾਈਮ ਪਾਸਵਰਡ ਅਗਲੀ ਸਕ੍ਰੀਨ ਤੇ ਦਰਜ ਕਰੋ। ਇਹ ਐਪ Yash Ornaments ਵੱਲੋਂ ਪ੍ਰਮਾਣਿਤ ਜ੍ਵੈਲਰਜ਼ ਲਈ ਹੈ।',
    registerTitle: 'ਅਜੇ ਰਜਿਸਟਰਡ ਨਹੀਂ?',
    registerBody: 'ਪਹਿਲਾਂ Yash Ornaments ਵੈੱਬਸਾਈਟ ਤੇ ਐਨਰੋਲ ਕਰੋ ਅਤੇ ਫੋਨ ਨੰਬਰ ਵੈਰੀਫਾਈ ਕਰੋ, ਫਿਰ ਉਸੇ ਨੰਬਰ ਨਾਲ ਇੱਥੇ ਲੌਗਿਨ ਕਰੋ।',
    enroll: 'ਵੈੱਬਸਾਈਟ ਤੇ ਐਨਰੋਲ ਕਰੋ',
    otpTitle: 'OTP ਨਹੀਂ ਮਿਲਿਆ?',
    otpBody: 'ਨੰਬਰ ਜਾਂਚੋ, ਦੁਬਾਰਾ ਮੰਗਣ ਤੋਂ ਪਹਿਲਾਂ 60 ਸਕਿੰਟ ਰੁਕੋ ਅਤੇ ਫੋਨ ਵਿੱਚ ਨੈੱਟਵਰਕ ਹੋਣਾ ਯਕੀਨੀ ਬਣਾਓ। ਹਰ ਕੋਡ 10 ਮਿੰਟ ਤੱਕ ਵੈਧ ਹੈ।',
    privacyTitle: 'ਗੁਪਤਤਾ ਅਤੇ ਤੁਹਾਡਾ ਡੇਟਾ',
    privacyBody: 'AI ਸਹਾਇਕ ਵਿਕਲਪਿਕ ਹੈ: ਤੁਹਾਡੀ ਇਜਾਜ਼ਤ ਬਿਨਾਂ ਕੁਝ ਵੀ AI ਪ੍ਰੋਵਾਈਡਰ ਨੂੰ ਨਹੀਂ ਭੇਜਿਆ ਜਾਂਦਾ, ਅਤੇ ਤੁਸੀਂ ਪ੍ਰੋਫ਼ਾਈਲ → AI Data Sharing ਵਿੱਚ ਇਜਾਜ਼ਤ ਵਾਪਸ ਲੈ ਸਕਦੇ ਹੋ। ਪ੍ਰੋਫ਼ਾਈਲ → Delete My Account ਤੋਂ ਖਾਤਾ ਹਟਾਇਆ ਜਾ ਸਕਦਾ ਹੈ।',
    privacy: 'ਗੁਪਤਤਾ ਨੀਤੀ',
    reviewTitle: 'App review access',
    reviewBody: 'ਸਿਰਫ਼ Google Play ਅਤੇ App Store ਸਮੀਖਿਆ ਟੀਮਾਂ ਲਈ। ਸਟੋਰ ਰਿਵਿਊ ਫਾਰਮ ਵਿੱਚ ਦਿੱਤੇ Reviewer ID ਅਤੇ Access key ਨਾਲ ਸਾਈਨ ਇਨ ਕਰੋ।',
    reviewOpen: 'ਰਿਵਿਊਅਰ ਸਾਈਨ-ਇਨ ਖੋਲ੍ਹੋ',
  },
};

/** Public help screen (no session required). Also the only entry point to the store-review sign-in. */
export default function HelpScreen() {
  const router = useRouter();
  const { language } = useLang();
  const t = T[language] || T.en;

  return (
    <SafeAreaView style={st.container} edges={['top']}>
      <View style={st.header}>
        <TouchableOpacity testID="help-back-btn" onPress={() => router.back()} style={st.backBtn} accessibilityRole="button" accessibilityLabel="Back">
          <Ionicons name="arrow-back" size={24} color={Colors.text} />
        </TouchableOpacity>
        <Text style={st.headerTitle}>{t.title}</Text>
        <View style={{ width: 44 }} />
      </View>
      <ScrollView contentContainerStyle={st.content}>
        <Section icon="phone-portrait-outline" title={t.signInTitle} body={t.signInBody} />
        <Section icon="person-add-outline" title={t.registerTitle} body={t.registerBody}>
          <TouchableOpacity testID="help-enroll-btn" style={st.primaryBtn} onPress={() => Linking.openURL(ENROLLMENT_URL).catch(() => {})} accessibilityRole="link">
            <Ionicons name="open-outline" size={16} color="#000" />
            <Text style={st.primaryText}>{t.enroll}</Text>
          </TouchableOpacity>
        </Section>
        <Section icon="chatbubble-ellipses-outline" title={t.otpTitle} body={t.otpBody} />
        <Section icon="shield-checkmark-outline" title={t.privacyTitle} body={t.privacyBody}>
          <TouchableOpacity testID="help-privacy-btn" style={st.linkRow} onPress={() => Linking.openURL(PRIVACY_URL).catch(() => {})} accessibilityRole="link">
            <Ionicons name="document-text-outline" size={16} color={Colors.gold} />
            <Text style={st.linkText}>{t.privacy}</Text>
          </TouchableOpacity>
        </Section>
        <Section icon="clipboard-outline" title={t.reviewTitle} body={t.reviewBody} testID="help-review-access-section">
          <TouchableOpacity testID="help-review-access-link" style={st.secondaryBtn} onPress={() => router.push('/review-access')} accessibilityRole="button">
            <Text style={st.secondaryText}>{t.reviewOpen}</Text>
            <Ionicons name="chevron-forward" size={16} color={Colors.gold} />
          </TouchableOpacity>
        </Section>
        <View style={{ height: 40 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

function Section({ icon, title, body, children, testID }: { icon: any; title: string; body: string; children?: React.ReactNode; testID?: string }) {
  return (
    <View style={st.card} testID={testID}>
      <View style={st.titleRow}>
        <Ionicons name={icon} size={20} color={Colors.gold} />
        <Text style={st.cardTitle}>{title}</Text>
      </View>
      <Text style={st.body}>{body}</Text>
      {children}
    </View>
  );
}

const st = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md },
  backBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: Colors.surface, alignItems: 'center', justifyContent: 'center' },
  headerTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text },
  content: { paddingHorizontal: Spacing.lg, gap: Spacing.md },
  card: { backgroundColor: Colors.card, borderRadius: 16, borderWidth: 1, borderColor: Colors.cardBorder, padding: Spacing.md, gap: 8 },
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  cardTitle: { fontSize: FontSize.md, fontWeight: '700', color: Colors.text },
  body: { fontSize: FontSize.sm, color: Colors.textSecondary, lineHeight: 20 },
  primaryBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: Colors.gold, borderRadius: 10, minHeight: 48, marginTop: 4 },
  primaryText: { fontSize: FontSize.sm, fontWeight: '700', color: '#000', letterSpacing: 1 },
  secondaryBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', borderWidth: 1, borderColor: Colors.gold, borderRadius: 10, minHeight: 48, paddingHorizontal: Spacing.md, marginTop: 4 },
  secondaryText: { fontSize: FontSize.sm, fontWeight: '700', color: Colors.gold },
  linkRow: { flexDirection: 'row', alignItems: 'center', gap: 6, minHeight: 44 },
  linkText: { fontSize: FontSize.sm, color: Colors.gold, fontWeight: '600', textDecorationLine: 'underline' },
});
