import React, { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, KeyboardAvoidingView, Platform, ActivityIndicator, Linking } from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api } from '../src/api';
import { useLang } from '../src/context/LanguageContext';
import { LANGUAGE_OPTIONS, Language } from '../src/i18n';

const ENROLLMENT_URL = process.env.EXPO_PUBLIC_ENROLLMENT_URL || 'https://enroll.yashornaments.com';

export default function LoginScreen() {
  const [phone, setPhone] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [registrationRequired, setRegistrationRequired] = useState(false);
  const router = useRouter();
  const { language, setLang } = useLang();

  const T: Record<string, any> = {
    en: { brand: 'YASH TRADE', tagline: 'Premium Silver \u2022 Gold \u2022 Diamond', loginWith: 'LOGIN WITH MOBILE', enterMobile: 'Enter mobile number', getOtp: 'GET OTP', hint: 'You will receive a one-time password by SMS', footer: 'Private app for verified jewellers only', selectLang: 'Select Language', invalidPhone: 'Enter a valid 10-digit phone number', regTitle: 'Registration Required', regMsg: 'This number is not registered. Please enroll on the Yash Ornaments website and verify your phone number before using the app.', regBtn: 'ENROLL ON WEBSITE' },
    hi: { brand: 'YASH TRADE', tagline: '\u092a\u094d\u0930\u0940\u092e\u093f\u092f\u092e \u091a\u093e\u0902\u0926\u0940 \u2022 \u0938\u094b\u0928\u093e \u2022 \u0939\u0940\u0930\u093e', loginWith: '\u092e\u094b\u092c\u093e\u0907\u0932 \u0938\u0947 \u0932\u0949\u0917\u093f\u0928 \u0915\u0930\u0947\u0902', enterMobile: '\u092e\u094b\u092c\u093e\u0907\u0932 \u0928\u0902\u092c\u0930 \u0926\u0930\u094d\u091c \u0915\u0930\u0947\u0902', getOtp: 'OTP \u092a\u094d\u0930\u093e\u092a\u094d\u0924 \u0915\u0930\u0947\u0902', hint: 'आपको SMS द्वारा वन-टाइम पासवर्ड मिलेगा', footer: '\u0915\u0947\u0935\u0932 \u0938\u0924\u094d\u092f\u093e\u092a\u093f\u0924 \u091c\u094d\u0935\u0947\u0932\u0930\u094d\u0938 \u0915\u0947 \u0932\u093f\u090f \u0928\u093f\u091c\u0940 \u0910\u092a', selectLang: '\u092d\u093e\u0937\u093e \u091a\u0941\u0928\u0947\u0902', invalidPhone: '\u090f\u0915 \u0935\u0948\u0927 10-\u0905\u0902\u0915\u094b\u0902 \u0915\u093e \u092b\u094b\u0928 \u0928\u0902\u092c\u0930 \u0926\u0930\u094d\u091c \u0915\u0930\u0947\u0902', regTitle: 'रजिस्ट्रेशन आवश्यक है', regMsg: 'यह नंबर रजिस्टर्ड नहीं है। ऐप उपयोग करने से पहले कृपया Yash Ornaments वेबसाइट पर एनरोल करें और अपना फोन नंबर वेरिफाई करें।', regBtn: 'वेबसाइट पर एनरोल करें' },
    pa: { brand: 'YASH TRADE', tagline: '\u0a2a\u0a4d\u0a30\u0a40\u0a2e\u0a40\u0a05\u0a2e \u0a1a\u0a3e\u0a02\u0a26\u0a40 \u2022 \u0a38\u0a4b\u0a28\u0a3e \u2022 \u0a39\u0a40\u0a30\u0a3e', loginWith: '\u0a2e\u0a4b\u0a2c\u0a3e\u0a07\u0a32 \u0a28\u0a3e\u0a32 \u0a32\u0a4c\u0a17\u0a3f\u0a28 \u0a15\u0a30\u0a4b', enterMobile: '\u0a2e\u0a4b\u0a2c\u0a3e\u0a07\u0a32 \u0a28\u0a02\u0a2c\u0a30 \u0a26\u0a30\u0a1c \u0a15\u0a30\u0a4b', getOtp: 'OTP \u0a2a\u0a4d\u0a30\u0a3e\u0a2a\u0a24 \u0a15\u0a30\u0a4b', hint: 'ਤੁਹਾਨੂੰ SMS ਰਾਹੀਂ ਵਨ-ਟਾਈਮ ਪਾਸਵਰਡ ਮਿਲੇਗਾ', footer: '\u0a15\u0a47\u0a35\u0a32 \u0a2a\u0a4d\u0a30\u0a2e\u0a3e\u0a23\u0a3f\u0a24 \u0a1c\u0a4d\u0a35\u0a48\u0a32\u0a30\u0a1c\u0a3c \u0a32\u0a08 \u0a28\u0a3f\u0a1c\u0a40 \u0a10\u0a2a', selectLang: '\u0a2d\u0a3e\u0a36\u0a3e \u0a1a\u0a41\u0a23\u0a4b', invalidPhone: '\u0a07\u0a71\u0a15 \u0a35\u0a48\u0a27 10-\u0a05\u0a02\u0a15\u0a3e\u0a02 \u0a26\u0a3e \u0a2b\u0a4b\u0a28 \u0a28\u0a02\u0a2c\u0a30 \u0a26\u0a30\u0a1c \u0a15\u0a30\u0a4b', regTitle: 'ਰਜਿਸਟ੍ਰੇਸ਼ਨ ਜ਼ਰੂਰੀ ਹੈ', regMsg: 'ਇਹ ਨੰਬਰ ਰਜਿਸਟਰਡ ਨਹੀਂ ਹੈ। ਐਪ ਵਰਤਣ ਤੋਂ ਪਹਿਲਾਂ ਕਿਰਪਾ ਕਰਕੇ Yash Ornaments ਵੈੱਬਸਾਈਟ ਤੇ ਐਨਰੋਲ ਕਰੋ ਅਤੇ ਆਪਣਾ ਫੋਨ ਨੰਬਰ ਵੈਰੀਫਾਈ ਕਰੋ।', regBtn: 'ਵੈੱਬਸਾਈਟ ਤੇ ਐਨਰੋਲ ਕਰੋ' },
  };
  const t = T[language] || T.en;

  const handleSendOTP = async () => {
    if (phone.length < 10) { setError(t.invalidPhone); return; }
    setLoading(true); setError(''); setRegistrationRequired(false);
    try {
      await api.post('/auth/send-otp', { phone });
      router.push({ pathname: '/verify-otp', params: { phone } });
    } catch (e: any) {
      if (e?.status === 404) {
        setRegistrationRequired(true);
      } else {
        setError(e.message || 'Failed to send OTP');
      }
    } finally { setLoading(false); }
  };

  return (
    <SafeAreaView style={styles.container}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={styles.inner}>
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
          <View style={styles.inputRow}>
            <Text style={styles.prefix}>+91</Text>
            <TextInput
              testID="phone-input"
              style={styles.input}
              placeholder={t.enterMobile}
              placeholderTextColor={Colors.textMuted}
              keyboardType="phone-pad"
              maxLength={10}
              value={phone}
              onChangeText={(val) => { setPhone(val.replace(/[^0-9]/g, '')); setError(''); setRegistrationRequired(false); }}
            />
          </View>
          {error ? <Text style={styles.error}>{error}</Text> : null}

          {registrationRequired && (
            <View style={styles.regBox} testID="registration-required">
              <View style={styles.regTitleRow}>
                <Ionicons name="person-add-outline" size={18} color={Colors.gold} />
                <Text style={styles.regTitle}>{t.regTitle}</Text>
              </View>
              <Text style={styles.regMsg}>{t.regMsg}</Text>
              <TouchableOpacity testID="enroll-btn" style={styles.regBtn} onPress={() => Linking.openURL(ENROLLMENT_URL).catch(() => {})}>
                <Ionicons name="open-outline" size={16} color="#000" />
                <Text style={styles.regBtnText}>{t.regBtn}</Text>
              </TouchableOpacity>
            </View>
          )}

          <TouchableOpacity testID="send-otp-btn" style={[styles.btn, phone.length < 10 && styles.btnDisabled]} onPress={handleSendOTP} disabled={loading || phone.length < 10}>
            {loading ? <ActivityIndicator color="#000" /> : <Text style={styles.btnText}>{t.getOtp}</Text>}
          </TouchableOpacity>

          <Text style={styles.hint}>{t.hint}</Text>
        </View>

        <View style={styles.footer}>
          <Text style={styles.footerText}>{t.footer}</Text>
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
  regBox: { backgroundColor: Colors.card, borderRadius: 12, borderWidth: 1, borderColor: Colors.borderGold, padding: Spacing.md, marginBottom: Spacing.md },
  regTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  regTitle: { fontSize: FontSize.md, fontWeight: '700', color: Colors.gold },
  regMsg: { fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: 6, lineHeight: 19 },
  regBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: Colors.gold, borderRadius: 10, paddingVertical: 12, marginTop: Spacing.md },
  regBtnText: { fontSize: FontSize.sm, fontWeight: '700', color: '#000', letterSpacing: 1 },
  btn: { backgroundColor: Colors.gold, borderRadius: 12, paddingVertical: 16, alignItems: 'center', marginTop: Spacing.sm },
  btnDisabled: { opacity: 0.4 },
  btnText: { fontSize: FontSize.base, fontWeight: '700', color: '#000', letterSpacing: 2 },
  hint: { fontSize: FontSize.xs, color: Colors.textMuted, textAlign: 'center', marginTop: Spacing.md },
  footer: { position: 'absolute', bottom: 32, left: 0, right: 0, alignItems: 'center' },
  footerText: { fontSize: FontSize.xs, color: Colors.textMuted, letterSpacing: 1 },
});
