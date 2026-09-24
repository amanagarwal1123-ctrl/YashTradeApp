import React, { useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextInput, ActivityIndicator, Linking } from 'react-native';
import { KeyboardAwareScreen } from '../src/components/KeyboardScreen';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api } from '../src/api';
import { displayPhone } from '../src/phone';
import { useAuth } from '../src/context/AuthContext';
import { showAlert, confirmAlert } from '../src/utils/alert';
import { guestHomeRoute } from '../src/navigation';

const PRIVACY_URL = process.env.EXPO_PUBLIC_PRIVACY_URL || 'https://yash-register.emergent.host/privacy';

const REMOVED = ['Name, phone, shop and location profile', 'Login access and sessions', 'Cart and wishlist', 'AI assistant chat history, AI consent record and content reports', 'Any usage analytics events stored for your account', 'Reward points and reward history', 'Customer notes and follow-ups', 'Consents and personal query details', 'OTP, sign-in grant and SMS-delivery log rows for your number'];
const KEPT = ['Anonymous operational query history (your name, phone, shop and notes are blanked; only status, dates and type remain)', 'Deletion reference and a keyed (hashed) identity tombstone that stops the number from being re-enrolled automatically', 'The erasure event for the enrolment website, kept until the website confirms it has removed its copy'];
const NOT_ERASED = 'Not erased by this request: the SMS provider (MSG91) keeps its own delivery logs for the one-time codes sent to your number, and, if you used the AI assistant, the AI provider and its gateway keep whatever they retain under their own terms. There is no automatic deletion request for these providers. Where a provider accepts a manual request, Yash Trade submits it and records the request date, the provider\'s answer and any retention exception in a ledger you can ask about, quoting your deletion reference. Provider erasure is only counted as done when the provider confirms it in writing; we do not state their retention periods.';
const NOT_COLLECTED = 'The app does not collect photos, files or other personal uploads from customers, so there is no personal media to erase from external storage.';

export default function DeleteAccountScreen() {
  const { user, logout } = useAuth();
  const router = useRouter();
  const [step, setStep] = useState<'info' | 'otp'>('info');
  const [otp, setOtp] = useState('');
  const [simulatedOtp, setSimulatedOtp] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const requestOtp = async () => {
    setBusy(true); setError('');
    try {
      const res = await api.post('/auth/delete-account/request');
      // Store-review sessions only: the server discloses the simulated code to the same authenticated sample account.
      if (res?.simulated_otp) { setSimulatedOtp(String(res.simulated_otp)); setOtp(String(res.simulated_otp)); }
      setStep('otp');
    } catch (e: any) {
      setError(e?.message || 'Could not send OTP. Please try again.');
    } finally { setBusy(false); }
  };

  const confirmDelete = () => {
    if (otp.length !== 4) { setError('Enter the 4-digit OTP'); return; }
    confirmAlert('Delete account?', 'This cannot be undone. You will be logged out immediately.', async () => {
      setBusy(true); setError('');
      try {
        const res = await api.post('/auth/delete-account/confirm', { otp });
        await logout();
        const remaining = res?.erasure?.local_personal_records_remaining;
        showAlert('Account deleted', `Your profile has been anonymized and all sessions revoked. Reference: ${res.reference}. Personal records remaining in the app: ${remaining ?? 'unknown'}. The enrolment website removes its copy on receiving this deletion event. Provider-held copies (SMS delivery logs, AI provider) are NOT erased by this request; their manual erasure requests are tracked separately under your reference.`);
        router.replace(guestHomeRoute() as any);
      } catch (e: any) {
        setError(e?.message || 'Could not verify OTP');
      } finally { setBusy(false); }
    }, 'Delete');
  };

  return (
    <SafeAreaView style={st.container} edges={['top']}>
      <View style={st.header}>
        <TouchableOpacity testID="delete-account-back" onPress={() => router.back()} style={st.backBtn}>
          <Ionicons name="arrow-back" size={24} color={Colors.text} />
        </TouchableOpacity>
        <Text style={st.headerTitle}>Delete My Account</Text>
        <View style={{ width: 44 }} />
      </View>

      <KeyboardAwareScreen style={{ flex: 1 }} contentContainerStyle={st.content}>
          <View style={st.warnCard}>
            <Ionicons name="warning" size={22} color={Colors.error} />
            <Text style={st.warnText}>Deletion revokes your sessions and removes or anonymizes your data in the app immediately. The enrolment website is notified to remove its copy. Enrollment retries cannot automatically restore this identity.</Text>
          </View>

          <Text style={st.label}>WHAT WILL BE REMOVED</Text>
          <View style={st.card}>
            {REMOVED.map(item => (
              <View key={item} style={st.row}><Ionicons name="close-circle" size={16} color={Colors.error} /><Text style={st.rowText}>{item}</Text></View>
            ))}
          </View>

          <Text style={st.label}>RESTRICTED DELETION & OPERATIONAL RECORD</Text>
          <View style={st.card}>
            {KEPT.map(item => (
              <View key={item} style={st.row}><Ionicons name="checkmark-circle" size={16} color={Colors.textMuted} /><Text style={st.rowText}>{item}</Text></View>
            ))}
            <Text style={st.hint}>Your name, phone number and shop details are not retained as a business record.</Text>
            <Text style={st.hint} testID="delete-not-erased">{NOT_ERASED}</Text>
            <Text style={st.hint}>{NOT_COLLECTED}</Text>
          </View>

          <TouchableOpacity testID="delete-privacy-link" style={st.linkRow} onPress={() => Linking.openURL(PRIVACY_URL).catch(() => {})}>
            <Ionicons name="shield-checkmark-outline" size={16} color={Colors.gold} />
            <Text style={st.linkText}>Read our Privacy Policy</Text>
          </TouchableOpacity>

          {step === 'info' ? (
            <TouchableOpacity testID="delete-send-otp" style={[st.dangerBtn, busy && { opacity: 0.5 }]} onPress={requestOtp} disabled={busy}>
              {busy ? <ActivityIndicator color="#fff" /> : <Text style={st.dangerBtnText}>SEND OTP TO {displayPhone(user?.phone || '')}</Text>}
            </TouchableOpacity>
          ) : (
            <View style={st.otpCard}>
              <Text style={st.otpTitle}>Confirm with OTP</Text>
              {simulatedOtp ? (
                <View style={st.reviewNote} testID="delete-simulated-otp">
                  <Text style={st.reviewNoteTitle}>STORE-REVIEW ENVIRONMENT</Text>
                  <Text style={st.reviewNoteText}>SMS is simulated for sample accounts. Your one-time code is <Text style={st.reviewNoteCode}>{simulatedOtp}</Text>. Deleting removes the data of this sample profile; the next reviewer sign-in starts a fresh sample profile.</Text>
                </View>
              ) : <Text style={st.hint}>Enter the 4-digit code sent to {displayPhone(user?.phone || '')}</Text>}
              <TextInput
                testID="delete-otp-input"
                style={st.otpInput}
                placeholder="OTP"
                placeholderTextColor={Colors.textMuted}
                keyboardType="number-pad"
                maxLength={4}
                value={otp}
                onChangeText={v => { setOtp(v.replace(/[^0-9]/g, '')); setError(''); }}
                autoComplete="one-time-code"
                textContentType="oneTimeCode"
              />
              <TouchableOpacity testID="delete-confirm" style={[st.dangerBtn, (busy || otp.length !== 4) && { opacity: 0.5 }]} onPress={confirmDelete} disabled={busy || otp.length !== 4}>
                {busy ? <ActivityIndicator color="#fff" /> : <Text style={st.dangerBtnText}>DELETE MY ACCOUNT</Text>}
              </TouchableOpacity>
              <TouchableOpacity testID="delete-resend" style={st.resendBtn} onPress={requestOtp} disabled={busy}>
                <Text style={st.resendText}>Resend OTP</Text>
              </TouchableOpacity>
            </View>
          )}
          {error ? <Text testID="delete-error" style={st.errorText}>{error}</Text> : null}

          <TouchableOpacity testID="delete-cancel" style={st.cancelBtn} onPress={() => router.back()}>
            <Text style={st.cancelText}>Keep my account</Text>
          </TouchableOpacity>
          <View style={{ height: 40 }} />
      </KeyboardAwareScreen>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md },
  backBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: Colors.surface, alignItems: 'center', justifyContent: 'center' },
  headerTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text },
  content: { paddingHorizontal: Spacing.lg },
  warnCard: { flexDirection: 'row', gap: 12, alignItems: 'flex-start', backgroundColor: Colors.error + '12', borderRadius: 12, borderWidth: 1, borderColor: Colors.error + '40', padding: Spacing.md, marginTop: Spacing.sm },
  warnText: { flex: 1, fontSize: FontSize.sm, color: Colors.text, lineHeight: 20 },
  label: { fontSize: FontSize.xs, color: Colors.textSecondary, letterSpacing: 1.5, fontWeight: '600', marginTop: Spacing.lg, marginBottom: 6 },
  card: { backgroundColor: Colors.card, borderRadius: 12, borderWidth: 1, borderColor: Colors.cardBorder, padding: Spacing.md, gap: 8 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  rowText: { fontSize: FontSize.sm, color: Colors.textSecondary, flex: 1 },
  hint: { fontSize: FontSize.xs, color: Colors.textMuted, marginTop: 6, lineHeight: 16 },
  linkRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: Spacing.lg, minHeight: 44 },
  linkText: { fontSize: FontSize.sm, color: Colors.gold, fontWeight: '600' },
  dangerBtn: { backgroundColor: Colors.error, borderRadius: 10, paddingVertical: 14, alignItems: 'center', marginTop: Spacing.md, minHeight: 48 },
  dangerBtnText: { fontSize: FontSize.sm, fontWeight: '700', color: '#fff', letterSpacing: 1 },
  otpCard: { backgroundColor: Colors.card, borderRadius: 12, borderWidth: 1, borderColor: Colors.error + '40', padding: Spacing.md, marginTop: Spacing.md },
  otpTitle: { fontSize: FontSize.md, fontWeight: '700', color: Colors.text },
  reviewNote: { backgroundColor: Colors.gold + '18', borderRadius: 10, borderWidth: 1, borderColor: Colors.gold, padding: Spacing.sm, marginTop: Spacing.sm, gap: 4 },
  reviewNoteTitle: { fontSize: FontSize.xs, fontWeight: '700', color: Colors.gold, letterSpacing: 1.5 },
  reviewNoteText: { fontSize: FontSize.sm, color: Colors.text, lineHeight: 20 },
  reviewNoteCode: { fontWeight: '700', color: Colors.gold, letterSpacing: 2 },
  otpInput: { backgroundColor: Colors.surface, borderRadius: 10, borderWidth: 1, borderColor: Colors.border, color: Colors.text, paddingHorizontal: 14, paddingVertical: 12, fontSize: FontSize.lg, textAlign: 'center', letterSpacing: 8, fontWeight: '700', marginTop: Spacing.sm },
  resendBtn: { alignSelf: 'center', marginTop: Spacing.sm, minHeight: 44, justifyContent: 'center' },
  resendText: { fontSize: FontSize.sm, color: Colors.gold, fontWeight: '600' },
  errorText: { fontSize: FontSize.sm, color: Colors.error, marginTop: Spacing.sm, textAlign: 'center' },
  cancelBtn: { alignItems: 'center', marginTop: Spacing.lg, minHeight: 44, justifyContent: 'center' },
  cancelText: { fontSize: FontSize.sm, color: Colors.textMuted, fontWeight: '600' },
});
