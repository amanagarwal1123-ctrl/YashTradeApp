import React, { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, KeyboardAvoidingView, Platform, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api } from '../src/api';

export default function LoginScreen() {
  const [phone, setPhone] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const router = useRouter();

  const handleSendOTP = async () => {
    if (phone.length < 10) { setError('Enter a valid 10-digit phone number'); return; }
    setLoading(true); setError('');
    try {
      await api.post('/auth/send-otp', { phone });
      router.push({ pathname: '/verify-otp', params: { phone } });
    } catch (e: any) {
      setError(e.message || 'Failed to send OTP');
    } finally { setLoading(false); }
  };

  return (
    <SafeAreaView style={styles.container}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={styles.inner}>
        <View style={styles.header}>
          <View style={styles.logoContainer}>
            <Ionicons name="diamond" size={48} color={Colors.gold} />
          </View>
          <Text style={styles.brand}>YASH TRADE</Text>
          <Text style={styles.tagline}>Premium Silver • Gold • Diamond</Text>
        </View>

        <View style={styles.form}>
          <Text style={styles.label}>LOGIN WITH MOBILE</Text>
          <View style={styles.inputRow}>
            <Text style={styles.prefix}>+91</Text>
            <TextInput
              testID="phone-input"
              style={styles.input}
              placeholder="Enter mobile number"
              placeholderTextColor={Colors.textMuted}
              keyboardType="phone-pad"
              maxLength={10}
              value={phone}
              onChangeText={(t) => { setPhone(t.replace(/[^0-9]/g, '')); setError(''); }}
            />
          </View>
          {error ? <Text style={styles.error}>{error}</Text> : null}

          <TouchableOpacity testID="send-otp-btn" style={[styles.btn, phone.length < 10 && styles.btnDisabled]} onPress={handleSendOTP} disabled={loading || phone.length < 10}>
            {loading ? <ActivityIndicator color="#000" /> : <Text style={styles.btnText}>GET OTP</Text>}
          </TouchableOpacity>

          <Text style={styles.hint}>Demo: Use any 10-digit number, OTP is 1234</Text>
        </View>

        <View style={styles.footer}>
          <Text style={styles.footerText}>Private app for verified jewellers only</Text>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  inner: { flex: 1, paddingHorizontal: Spacing.lg },
  header: { alignItems: 'center', marginTop: 60, marginBottom: 48 },
  logoContainer: { width: 88, height: 88, borderRadius: 44, backgroundColor: 'rgba(212,175,55,0.1)', borderWidth: 1, borderColor: Colors.borderGold, alignItems: 'center', justifyContent: 'center', marginBottom: Spacing.lg },
  brand: { fontSize: FontSize.xxl, fontWeight: '700', color: Colors.gold, letterSpacing: 4 },
  tagline: { fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: Spacing.md, letterSpacing: 1 },
  form: { width: '100%' },
  label: { fontSize: FontSize.xs, color: Colors.textSecondary, letterSpacing: 2, marginBottom: Spacing.sm, fontWeight: '600' },
  inputRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: Colors.surface, borderRadius: 12, borderWidth: 1, borderColor: Colors.border, paddingHorizontal: Spacing.md, marginBottom: Spacing.md },
  prefix: { fontSize: FontSize.lg, color: Colors.textSecondary, marginRight: Spacing.sm, fontWeight: '500' },
  input: { flex: 1, fontSize: FontSize.lg, color: Colors.text, paddingVertical: 16, fontWeight: '500' },
  error: { color: Colors.error, fontSize: FontSize.sm, marginBottom: Spacing.sm },
  btn: { backgroundColor: Colors.gold, borderRadius: 12, paddingVertical: 16, alignItems: 'center', marginTop: Spacing.sm },
  btnDisabled: { opacity: 0.4 },
  btnText: { fontSize: FontSize.base, fontWeight: '700', color: '#000', letterSpacing: 2 },
  hint: { fontSize: FontSize.xs, color: Colors.textMuted, textAlign: 'center', marginTop: Spacing.md },
  footer: { position: 'absolute', bottom: 32, left: 0, right: 0, alignItems: 'center' },
  footerText: { fontSize: FontSize.xs, color: Colors.textMuted, letterSpacing: 1 },
});
