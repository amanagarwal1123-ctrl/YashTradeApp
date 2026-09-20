import React, { useState, useEffect } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, Platform, ActivityIndicator, Linking } from 'react-native';
import { KeyboardAvoidingView } from 'react-native-keyboard-controller';
import { useRouter } from 'expo-router';
import { useAuth } from '../src/context/AuthContext';
import { homeRouteFor } from '../src/navigation';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import PhoneField from '../src/components/PhoneField';
import { canonicalPhone, COUNTRIES, DEFAULT_COUNTRY } from '../src/phone';
import type { CountryCode } from 'libphonenumber-js';
import { api } from '../src/api';
import { useLang } from '../src/context/LanguageContext';
import { LANGUAGE_OPTIONS } from '../src/i18n';
import Constants from 'expo-constants';

const PRIVACY_URL = Constants.expoConfig?.extra?.privacyUrl || process.env.EXPO_PUBLIC_PRIVACY_URL || '';
const TERMS_URL = Constants.expoConfig?.extra?.termsUrl || PRIVACY_URL;

export default function LoginScreen() {
  const [phone, setPhone] = useState('');
  const [country, setCountry] = useState<CountryCode>(DEFAULT_COUNTRY);
  const canonical = canonicalPhone(phone, country);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const router = useRouter();
  const { language, setLang } = useLang();
  const { user, loading: authLoading } = useAuth();
  // A signed-in user never sees the login screen (reached through back navigation or a stale link): bounce to home.
  useEffect(() => { if (!authLoading && user) router.replace(homeRouteFor(user.role) as any); }, [authLoading, user]);

  const T: Record<string, any> = {
    en: { brand: 'YASH TRADE', tagline: 'Premium Silver \u2022 Gold \u2022 Diamond', loginWith: 'LOGIN WITH MOBILE', enterMobile: 'Enter mobile number', getOtp: 'GET OTP', hint: 'You will receive a one-time password by SMS', footer: 'Private app for verified jewellers only', selectLang: 'Select Language', invalidPhone: 'Enter a valid 10-digit phone number', newHint: 'New here? Your account is created as soon as the OTP is verified. Already registered on the website? Use the same number.', consent: 'By continuing you agree to our', terms: 'Terms', and: 'and', privacy: 'Privacy Policy', help: 'Help' },
    hi: { brand: 'YASH TRADE', tagline: '\u092a\u094d\u0930\u0940\u092e\u093f\u092f\u092e \u091a\u093e\u0902\u0926\u0940 \u2022 \u0938\u094b\u0928\u093e \u2022 \u0939\u0940\u0930\u093e', loginWith: '\u092e\u094b\u092c\u093e\u0907\u0932 \u0938\u0947 \u0932\u0949\u0917\u093f\u0928 \u0915\u0930\u0947\u0902', enterMobile: '\u092e\u094b\u092c\u093e\u0907\u0932 \u0928\u0902\u092c\u0930 \u0926\u0930\u094d\u091c \u0915\u0930\u0947\u0902', getOtp: 'OTP \u092a\u094d\u0930\u093e\u092a\u094d\u0924 \u0915\u0930\u0947\u0902', hint: 'आपको SMS द्वारा वन-टाइम पासवर्ड मिलेगा', footer: '\u0915\u0947\u0935\u0932 \u0938\u0924\u094d\u092f\u093e\u092a\u093f\u0924 \u091c\u094d\u0935\u0947\u0932\u0930\u094d\u0938 \u0915\u0947 \u0932\u093f\u090f \u0928\u093f\u091c\u0940 \u0910\u092a', selectLang: '\u092d\u093e\u0937\u093e \u091a\u0941\u0928\u0947\u0902', invalidPhone: '\u090f\u0915 \u0935\u0948\u0927 10-\u0905\u0902\u0915\u094b\u0902 \u0915\u093e \u092b\u094b\u0928 \u0928\u0902\u092c\u0930 \u0926\u0930\u094d\u091c \u0915\u0930\u0947\u0902', newHint: 'नए हैं? OTP सत्यापित होते ही आपका खाता बन जाएगा। वेबसाइट पर पहले से रजिस्टर्ड हैं? वही नंबर उपयोग करें।', consent: 'आगे बढ़ने पर आप सहमत होते हैं', terms: 'नियम', and: 'और', privacy: 'गोपनीयता नीति', help: 'सहायता' },
    pa: { brand: 'YASH TRADE', tagline: '\u0a2a\u0a4d\u0a30\u0a40\u0a2e\u0a40\u0a05\u0a2e \u0a1a\u0a3e\u0a02\u0a26\u0a40 \u2022 \u0a38\u0a4b\u0a28\u0a3e \u2022 \u0a39\u0a40\u0a30\u0a3e', loginWith: '\u0a2e\u0a4b\u0a2c\u0a3e\u0a07\u0a32 \u0a28\u0a3e\u0a32 \u0a32\u0a4c\u0a17\u0a3f\u0a28 \u0a15\u0a30\u0a4b', enterMobile: '\u0a2e\u0a4b\u0a2c\u0a3e\u0a07\u0a32 \u0a28\u0a02\u0a2c\u0a30 \u0a26\u0a30\u0a1c \u0a15\u0a30\u0a4b', getOtp: 'OTP \u0a2a\u0a4d\u0a30\u0a3e\u0a2a\u0a24 \u0a15\u0a30\u0a4b', hint: 'ਤੁਹਾਨੂੰ SMS ਰਾਹੀਂ ਵਨ-ਟਾਈਮ ਪਾਸਵਰਡ ਮਿਲੇਗਾ', footer: '\u0a15\u0a47\u0a35\u0a32 \u0a2a\u0a4d\u0a30\u0a2e\u0a3e\u0a23\u0a3f\u0a24 \u0a1c\u0a4d\u0a35\u0a48\u0a32\u0a30\u0a1c\u0a3c \u0a32\u0a08 \u0a28\u0a3f\u0a1c\u0a40 \u0a10\u0a2a', selectLang: '\u0a2d\u0a3e\u0a36\u0a3e \u0a1a\u0a41\u0a23\u0a4b', invalidPhone: '\u0a07\u0a71\u0a15 \u0a35\u0a48\u0a27 10-\u0a05\u0a02\u0a15\u0a3e\u0a02 \u0a26\u0a3e \u0a2b\u0a4b\u0a28 \u0a28\u0a02\u0a2c\u0a30 \u0a26\u0a30\u0a1c \u0a15\u0a30\u0a4b', newHint: 'ਨਵੇਂ ਹੋ? OTP ਦੀ ਪੁਸ਼ਟੀ ਹੁੰਦੇ ਹੀ ਤੁਹਾਡਾ ਖਾਤਾ ਬਣ ਜਾਵੇਗਾ। ਵੈੱਬਸਾਈਟ ਤੇ ਪਹਿਲਾਂ ਹੀ ਰਜਿਸਟਰਡ ਹੋ? ਉਹੀ ਨੰਬਰ ਵਰਤੋ।', consent: 'ਅੱਗੇ ਵਧਣ ਤੇ ਤੁਸੀਂ ਸਹਿਮਤ ਹੁੰਦੇ ਹੋ', terms: 'ਸ਼ਰਤਾਂ', and: 'ਅਤੇ', privacy: 'ਪਰਦੇਦਾਰੀ ਨੀਤੀ', help: 'ਮਦਦ' },
  };
  const t = T[language] || T.en;

  const handleSendOTP = async () => {
    if (!canonical) { setError(country === 'IN' ? t.invalidPhone : `Enter a valid ${COUNTRIES.find(c => c.code === country)?.label} number`); return; }
    setLoading(true); setError('');
    try {
      // Login-or-register: an unknown number gets an OTP too and the account is created once it is verified.
      // Indian numbers travel as 10 digits (existing accounts); other supported countries as +E.164.
      const result = await api.post('/auth/send-otp', { phone: canonical, channel: 'mobile' });
      router.push({ pathname: '/verify-otp', params: { phone: canonical, challengeId: result.challenge_id, newAccount: result.account_exists === false ? '1' : '0',
        resendAt: result.resend_at || '', serverTime: result.server_time || '' } });
    } catch (e: any) {
      setError(e.message || 'Failed to send OTP');
    } finally { setLoading(false); }
  };

  return (
    <SafeAreaView style={styles.container}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} keyboardVerticalOffset={16} style={styles.inner}>
        {/* Language Selector at Top */}
        <View style={styles.langSection}>
          <Text style={styles.langLabel}>{t.selectLang}</Text>
          <View style={styles.langRow}>
            {LANGUAGE_OPTIONS.map(lo => (
              <TouchableOpacity
                key={lo.key}
                testID={`login-lang-${lo.key}`}
                style={[styles.langBtn, language === lo.key && styles.langBtnActive]}
                onPress={() => setLang(lo.key)}
              >
                <Text style={[styles.langBtnText, language === lo.key && styles.langBtnTextActive]}>{lo.native}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        <View style={styles.header}>
          <View style={styles.logoContainer}>
            <Ionicons name="diamond" size={48} color={Colors.gold} />
          </View>
          <Text style={styles.brand}>{t.brand}</Text>
          <Text style={styles.tagline}>{t.tagline}</Text>
        </View>

        <View style={styles.form}>
          <Text style={styles.label}>{t.loginWith}</Text>
          <View style={{ marginBottom: Spacing.md }}>
            <PhoneField testID="phone-input" country={country} national={phone} placeholder={country === 'IN' ? t.enterMobile : undefined}
              onChange={(c, v) => { setCountry(c); setPhone(v); setError(''); }} />
          </View>
          {error ? <Text testID="login-error" style={styles.error}>{error}</Text> : null}

          <TouchableOpacity testID="send-otp-btn" style={[styles.btn, !canonical && styles.btnDisabled]} onPress={handleSendOTP} disabled={loading || !canonical}>
            {loading ? <ActivityIndicator color="#000" /> : <Text style={styles.btnText}>{t.getOtp}</Text>}
          </TouchableOpacity>

          <Text style={styles.hint}>{t.hint}</Text>
          <Text style={styles.newHint} testID="login-new-hint">{t.newHint}</Text>
          {/* Consent recorded on account creation (backend CONSENT_VERSION); links open the live documents. */}
          <Text style={styles.consent} testID="login-consent">
            {t.consent}{' '}
            <Text testID="login-terms-link" style={styles.consentLink} onPress={() => TERMS_URL && Linking.openURL(TERMS_URL).catch(() => {})}>{t.terms}</Text>
            {' '}{t.and}{' '}
            <Text testID="login-privacy-link" style={styles.consentLink} onPress={() => PRIVACY_URL && Linking.openURL(PRIVACY_URL).catch(() => {})}>{t.privacy}</Text>.
          </Text>
        </View>

        <View style={styles.footer}>
          <Text style={styles.footerText}>{t.footer}</Text>
          <TouchableOpacity testID="login-help-link" onPress={() => router.push('/help')} style={styles.helpLink} accessibilityRole="button">
            <Ionicons name="help-circle-outline" size={16} color={Colors.textSecondary} />
            <Text style={styles.helpLinkText}>{t.help}</Text>
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  inner: { flex: 1, paddingHorizontal: Spacing.lg },
  langSection: { alignItems: 'center', marginTop: Spacing.lg },
  langLabel: { fontSize: FontSize.xs, color: Colors.textMuted, letterSpacing: 1, marginBottom: 6, fontWeight: '600' },
  langRow: { flexDirection: 'row', gap: 8 },
  langBtn: { paddingHorizontal: 18, paddingVertical: 8, borderRadius: 20, backgroundColor: Colors.surface, borderWidth: 1, borderColor: Colors.border },
  langBtnActive: { backgroundColor: Colors.gold + '20', borderColor: Colors.gold },
  langBtnText: { fontSize: FontSize.sm, color: Colors.textMuted, fontWeight: '500' },
  langBtnTextActive: { color: Colors.gold, fontWeight: '700' },
  header: { alignItems: 'center', marginTop: 32, marginBottom: 36 },
  logoContainer: { width: 88, height: 88, borderRadius: 44, backgroundColor: 'rgba(212,175,55,0.1)', borderWidth: 1, borderColor: Colors.borderGold, alignItems: 'center', justifyContent: 'center', marginBottom: Spacing.lg },
  brand: { fontSize: FontSize.xxl, fontWeight: '700', color: Colors.gold, letterSpacing: 4 },
  tagline: { fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: Spacing.md, letterSpacing: 1 },
  form: { width: '100%' },
  label: { fontSize: FontSize.xs, color: Colors.textSecondary, letterSpacing: 2, marginBottom: Spacing.sm, fontWeight: '600' },
  inputRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: Colors.surface, borderRadius: 12, borderWidth: 1, borderColor: Colors.border, paddingHorizontal: Spacing.md, marginBottom: Spacing.md },
  prefix: { fontSize: FontSize.lg, color: Colors.textSecondary, marginRight: Spacing.sm, fontWeight: '500' },
  input: { flex: 1, fontSize: FontSize.lg, color: Colors.text, paddingVertical: 16, fontWeight: '500' },
  error: { color: Colors.error, fontSize: FontSize.sm, marginBottom: Spacing.sm },
  newHint: { fontSize: FontSize.xs, color: Colors.textSecondary, textAlign: 'center', marginTop: Spacing.sm, lineHeight: 18 },
  consent: { fontSize: FontSize.xs, color: Colors.textMuted, textAlign: 'center', marginTop: Spacing.md, lineHeight: 18 },
  consentLink: { color: Colors.gold, textDecorationLine: 'underline', fontWeight: '600' },
  btn: { backgroundColor: Colors.gold, borderRadius: 12, paddingVertical: 16, alignItems: 'center', marginTop: Spacing.sm },
  btnDisabled: { opacity: 0.4 },
  btnText: { fontSize: FontSize.base, fontWeight: '700', color: '#000', letterSpacing: 2 },
  hint: { fontSize: FontSize.xs, color: Colors.textMuted, textAlign: 'center', marginTop: Spacing.md },
  footer: { position: 'absolute', bottom: 24, left: 0, right: 0, alignItems: 'center' },
  footerText: { fontSize: FontSize.xs, color: Colors.textMuted, letterSpacing: 1 },
  helpLink: { flexDirection: 'row', alignItems: 'center', gap: 6, minHeight: 44, justifyContent: 'center', paddingHorizontal: Spacing.md },
  helpLinkText: { fontSize: FontSize.sm, color: Colors.textSecondary, textDecorationLine: 'underline', letterSpacing: 0.5 },
});
