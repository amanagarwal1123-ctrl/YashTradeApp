import React, { useState, useRef, useEffect, useCallback } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, Platform, ActivityIndicator, Pressable, AppState } from 'react-native';
import { KeyboardAvoidingView } from 'react-native-keyboard-controller';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { displayPhone } from '../src/phone';
import { api } from '../src/api';
import { useAuth } from '../src/context/AuthContext';
import { resetToHome } from '../src/navigation';

const LENGTH = 4;
export const digitsOnly = (text: string) => text.replace(/[^0-9]/g, '').slice(0, LENGTH);

/** Seconds until `resendAt` measured against the SERVER clock (skew-safe): offset = serverTime - deviceTime at receipt. */
export function secondsUntil(resendAt: string | undefined, serverTime: string | undefined, receivedAtMs: number, nowMs = Date.now()) {
  if (!resendAt) return 0;
  const target = Date.parse(resendAt);
  const server = serverTime ? Date.parse(serverTime) : receivedAtMs;
  const skew = server - receivedAtMs;
  return Math.max(0, Math.ceil((target - (nowMs + skew)) / 1000));
}

export default function VerifyOTPScreen() {
  const { phone, challengeId, newAccount, resendAt: initialResendAt, serverTime: initialServerTime } =
    useLocalSearchParams<{ phone: string; challengeId: string; newAccount?: string; resendAt?: string; serverTime?: string }>();
  // ONE logical OTP value rendered as four boxes: an OS autofill suggestion or a paste delivers the whole code in one
  // change event (never truncated by a per-box maxLength), manual typing appends digit by digit.
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [activeChallenge, setActiveChallenge] = useState(challengeId);
  const [timing, setTiming] = useState({ resendAt: initialResendAt, serverTime: initialServerTime, receivedAt: Date.now() });
  const [cooldown, setCooldown] = useState(() => secondsUntil(initialResendAt, initialServerTime, Date.now()));
  const input = useRef<TextInput>(null);
  const submitted = useRef<string | null>(null);
  const router = useRouter();
  const { login } = useAuth();

  const tick = useCallback(() => setCooldown(secondsUntil(timing.resendAt, timing.serverTime, timing.receivedAt)), [timing]);
  useEffect(() => {
    tick();
    const timer = setInterval(tick, 1000);
    const sub = AppState.addEventListener('change', s => { if (s === 'active') tick(); }); // resume: recompute, never drift
    return () => { clearInterval(timer); sub.remove(); };
  }, [tick]);

  const verifyOTP = useCallback(async (value: string) => {
    if (loading || submitted.current === value) return; // one submission per completed code, whatever produced it
    submitted.current = value;
    setLoading(true); setError('');
    try {
      // accept_terms: the sign-in screen states that continuing accepts the Terms & Privacy Policy; recorded only if an account is created.
      const res = await api.post('/auth/verify-otp', { phone, otp: value, challenge_id: activeChallenge, channel: 'mobile', accept_terms: true });
      const currentUser = await login(res.token, res.user, res.refresh_token);
      // Role-based routing: the backend-verified role decides; login/OTP screens leave the history.
      resetToHome(router, currentUser.role);
    } catch (e: any) {
      setError(e.message || 'Invalid OTP');
      setCode('');
      submitted.current = null;
      input.current?.focus();
    } finally { setLoading(false); }
  }, [loading, phone, activeChallenge, login, router]);

  const onChange = (text: string) => {
    const next = digitsOnly(text);
    setCode(next);
    setError('');
    if (next.length === LENGTH) verifyOTP(next);
  };

  const resend = async () => {
    setLoading(true); setError('');
    try {
      const sent = await api.post('/auth/send-otp', { phone, channel: 'mobile' });
      setActiveChallenge(sent.challenge_id);
      setTiming({ resendAt: sent.resend_at, serverTime: sent.server_time, receivedAt: Date.now() });
      setCode(''); submitted.current = null;
      input.current?.focus();
    } catch (e: any) {
      // The server's actual retry moment (cooldown or abuse limit), never a fake promise
      const body = e.body || {};
      if (body.resend_at) setTiming({ resendAt: body.resend_at, serverTime: body.server_time, receivedAt: Date.now() });
      setError(e.message);
    } finally { setLoading(false); }
  };

  return (
    <SafeAreaView style={styles.container}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} keyboardVerticalOffset={16} style={styles.inner}>
        <TouchableOpacity testID="back-btn" onPress={() => router.replace('/login')} style={styles.backBtn} accessibilityLabel="Change number">
          <Ionicons name="arrow-back" size={24} color={Colors.text} />
        </TouchableOpacity>

        <View style={styles.header}>
          <Ionicons name="shield-checkmark" size={48} color={Colors.gold} />
          <Text style={styles.title}>Verify OTP</Text>
          <Text style={styles.subtitle}>Enter the code sent to {displayPhone(phone || '')}</Text>
          {newAccount === '1' && <Text style={styles.newAccount} testID="verify-new-account">New number — your account will be created once the code is verified.</Text>}
        </View>

        <Pressable style={styles.otpRow} onPress={() => input.current?.focus()} testID="otp-boxes" accessibilityLabel="One-time code, 4 digits">
          {Array.from({ length: LENGTH }).map((_, i) => (
            <View key={i} testID={`otp-box-${i}`} style={[styles.otpBox, code[i] ? styles.otpBoxFilled : null, code.length === i && !loading ? styles.otpBoxActive : null]}>
              <Text style={styles.otpDigit}>{code[i] || ''}</Text>
            </View>
          ))}
          <TextInput
            ref={input}
            testID="otp-input"
            style={styles.hiddenInput}
            value={code}
            onChangeText={onChange}
            keyboardType="number-pad"
            inputMode="numeric"
            maxLength={LENGTH}
            editable={!loading}
            autoFocus
            caretHidden
            textContentType="oneTimeCode"
            autoComplete={Platform.OS === 'android' ? 'sms-otp' : 'one-time-code'}
            importantForAutofill="yes"
            returnKeyType="done"
            onSubmitEditing={() => { if (code.length === LENGTH) verifyOTP(code); }}
            accessibilityLabel="One-time code"
          />
        </Pressable>

        {error ? <Text testID="verify-otp-error" style={styles.error}>{error}</Text> : null}
        {loading && <ActivityIndicator color={Colors.gold} style={{ marginTop: Spacing.md }} />}

        <Text style={styles.hint}>OTP sent via SMS to your mobile number. Your phone may offer the code as a suggestion — tapping it fills all four boxes; you can also paste or type it.</Text>
        <TouchableOpacity testID="otp-resend" style={styles.resend} disabled={cooldown > 0 || loading} onPress={resend}>
          <Text testID="otp-resend-countdown" style={styles.subtitle}>{cooldown > 0 ? `Resend available in ${cooldown}s` : 'Resend OTP'}</Text>
        </TouchableOpacity>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  resend: { minHeight: 48, alignItems: 'center', justifyContent: 'center', marginTop: 20 },
  container: { flex: 1, backgroundColor: Colors.background },
  inner: { flex: 1, paddingHorizontal: Spacing.lg },
  backBtn: { marginTop: Spacing.md, padding: Spacing.sm, minWidth: 44, minHeight: 44 },
  header: { alignItems: 'center', marginTop: 40, marginBottom: 48 },
  title: { fontSize: FontSize.xl, fontWeight: '700', color: Colors.text, marginTop: Spacing.md },
  subtitle: { fontSize: FontSize.md, color: Colors.textSecondary, marginTop: Spacing.sm },
  newAccount: { fontSize: FontSize.xs, color: Colors.gold, marginTop: Spacing.sm, textAlign: 'center', paddingHorizontal: Spacing.lg, lineHeight: 18 },
  otpRow: { flexDirection: 'row', justifyContent: 'center', gap: 16, position: 'relative' },
  otpBox: { width: 60, height: 64, borderRadius: 12, backgroundColor: Colors.surface, borderWidth: 1, borderColor: Colors.border, alignItems: 'center', justifyContent: 'center' },
  otpBoxFilled: { borderColor: Colors.gold },
  otpBoxActive: { borderColor: Colors.textSecondary },
  otpDigit: { fontSize: FontSize.xxl, color: Colors.text, fontWeight: '700' },
  hiddenInput: { position: 'absolute', left: 0, right: 0, top: 0, bottom: 0, opacity: 0.02, color: 'transparent', fontSize: 1 },
  error: { color: Colors.error, fontSize: FontSize.sm, textAlign: 'center', marginTop: Spacing.md },
  hint: { fontSize: FontSize.xs, color: Colors.textMuted, textAlign: 'center', marginTop: Spacing.xl, lineHeight: 18 },
});
