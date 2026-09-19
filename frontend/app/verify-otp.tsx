import React, { useState, useRef, useEffect } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, KeyboardAvoidingView, Platform, ActivityIndicator } from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { displayPhone } from '../src/phone';
import { api } from '../src/api';
import { useAuth } from '../src/context/AuthContext';

export default function VerifyOTPScreen() {
  const { phone, challengeId, newAccount } = useLocalSearchParams<{ phone: string; challengeId: string; newAccount?: string }>();
  const [otp, setOtp] = useState(['', '', '', '']);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [activeChallenge, setActiveChallenge] = useState(challengeId);
  const [cooldown, setCooldown] = useState(60);
  useEffect(() => { const timer = setInterval(() => setCooldown(n => Math.max(0,n-1)),1000); return () => clearInterval(timer); }, []);
  const refs = [useRef<TextInput>(null), useRef<TextInput>(null), useRef<TextInput>(null), useRef<TextInput>(null)];
  const router = useRouter();
  const { login } = useAuth();

  const handleChange = (text: string, idx: number) => {
    const newOtp = [...otp];
    newOtp[idx] = text;
    setOtp(newOtp);
    setError('');
    if (text && idx < 3) refs[idx + 1].current?.focus();
    if (newOtp.every(d => d) && newOtp.join('').length === 4) {
      verifyOTP(newOtp.join(''));
    }
  };

  const handleKeyPress = (e: any, idx: number) => {
    if (e.nativeEvent.key === 'Backspace' && !otp[idx] && idx > 0) {
      refs[idx - 1].current?.focus();
    }
  };

  const verifyOTP = async (code: string) => {
    if (loading) return;
    setLoading(true); setError('');
    try {
      // accept_terms: the sign-in screen states that continuing accepts the Terms & Privacy Policy; recorded only if an account is created.
      const res = await api.post('/auth/verify-otp', { phone, otp: code, challenge_id: activeChallenge, channel: 'mobile', accept_terms: true });
      const currentUser = await login(res.token, res.user, res.refresh_token);
      // Role-based routing — the backend-verified role decides the experience
      const role = currentUser.role;
      if (role === 'telecaller') router.replace('/telecaller');
      else if (role === 'admin' || role === 'billing_executive') router.replace('/panel');
      else if (role === 'customer') router.replace('/(tabs)');
      else throw new Error('Unknown account role; contact support');
    } catch (e: any) {
      setError(e.message || 'Invalid OTP');
      setOtp(['', '', '', '']);
      refs[0].current?.focus();
    } finally { setLoading(false); }
  };

  return (
    <SafeAreaView style={styles.container}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={styles.inner}>
        <TouchableOpacity testID="back-btn" onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color={Colors.text} />
        </TouchableOpacity>

        <View style={styles.header}>
          <Ionicons name="shield-checkmark" size={48} color={Colors.gold} />
          <Text style={styles.title}>Verify OTP</Text>
          <Text style={styles.subtitle}>Enter the code sent to {displayPhone(phone || '')}</Text>
          {newAccount === '1' && <Text style={styles.newAccount} testID="verify-new-account">New number — your account will be created once the code is verified.</Text>}
        </View>

        <View style={styles.otpRow}>
          {otp.map((d, i) => (
            <TextInput
              key={i}
              ref={refs[i]}
              testID={`otp-input-${i}`}
              style={[styles.otpBox, d ? styles.otpBoxFilled : null]}
              keyboardType="number-pad"
              maxLength={1}
              value={d}
              editable={!loading}
              onChangeText={(t) => handleChange(t, i)}
              onKeyPress={(e) => handleKeyPress(e, i)}
              autoFocus={i === 0}
            />
          ))}
        </View>

          {error ? <Text testID="verify-otp-error" style={styles.error}>{error}</Text> : null}
        {loading && <ActivityIndicator color={Colors.gold} style={{ marginTop: Spacing.md }} />}

        <Text style={styles.hint}>OTP sent via SMS to your mobile number</Text>
        <TouchableOpacity testID="otp-resend" style={styles.resend} disabled={cooldown>0 || loading} onPress={async () => {
          setLoading(true); setError('');
          try { const sent=await api.post('/auth/send-otp',{phone,channel:'mobile'}); setActiveChallenge(sent.challenge_id); setCooldown(sent.resend_after); setOtp(['','','','']); }
          catch(e:any){setError(e.message);} finally{setLoading(false);}
        }}><Text testID="otp-resend-countdown" style={styles.subtitle}>{cooldown>0?`Resend available in ${cooldown}s`:'Resend OTP'}</Text></TouchableOpacity>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  resend: { minHeight: 48, alignItems: 'center', justifyContent: 'center', marginTop: 20 },
  container: { flex: 1, backgroundColor: Colors.background },
  inner: { flex: 1, paddingHorizontal: Spacing.lg },
  backBtn: { marginTop: Spacing.md, padding: Spacing.sm },
  header: { alignItems: 'center', marginTop: 40, marginBottom: 48 },
  title: { fontSize: FontSize.xl, fontWeight: '700', color: Colors.text, marginTop: Spacing.md },
  subtitle: { fontSize: FontSize.md, color: Colors.textSecondary, marginTop: Spacing.sm },
  newAccount: { fontSize: FontSize.xs, color: Colors.gold, marginTop: Spacing.sm, textAlign: 'center', paddingHorizontal: Spacing.lg, lineHeight: 18 },
  otpRow: { flexDirection: 'row', justifyContent: 'center', gap: 16 },
  otpBox: { width: 60, height: 64, borderRadius: 12, backgroundColor: Colors.surface, borderWidth: 1, borderColor: Colors.border, fontSize: FontSize.xxl, color: Colors.text, textAlign: 'center', fontWeight: '700' },
  otpBoxFilled: { borderColor: Colors.gold },
  error: { color: Colors.error, fontSize: FontSize.sm, textAlign: 'center', marginTop: Spacing.md },
  hint: { fontSize: FontSize.xs, color: Colors.textMuted, textAlign: 'center', marginTop: Spacing.xl },
});
