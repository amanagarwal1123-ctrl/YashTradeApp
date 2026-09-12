import React, { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, KeyboardAvoidingView, Platform, ActivityIndicator, ScrollView } from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api } from '../src/api';
import { useAuth } from '../src/context/AuthContext';

/**
 * Store-review sign-in. Reviewer ID + reusable access key issued privately by the operator.
 * The server decides the role and binds the session to the isolated synthetic dataset; nothing
 * here selects a role, database or environment. Ordinary users keep using phone + SMS OTP.
 */
export default function ReviewAccessScreen() {
  const [reviewerId, setReviewerId] = useState('');
  const [accessKey, setAccessKey] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const router = useRouter();
  const { login } = useAuth();

  const submit = async () => {
    if (loading) return;
    setLoading(true); setError('');
    try {
      const res = await api.post('/auth/review/login', { reviewer_id: reviewerId.trim(), access_key: accessKey.trim() });
      const user = await login(res.token, res.user, res.refresh_token);
      if (user.role === 'telecaller') router.replace('/telecaller');
      else if (user.role === 'admin' || user.role === 'billing_executive') router.replace('/panel');
      else router.replace('/(tabs)');
    } catch (e: any) {
      if (e?.code === 'REVIEW_UNAVAILABLE') setError('Store-review access is not enabled on this server.');
      else if (e?.status === 429) setError('Too many attempts. Please wait a minute and try again.');
      else setError(e?.message || 'Reviewer ID or access key is incorrect');
    } finally { setLoading(false); }
  };

  const ready = reviewerId.trim().length >= 3 && accessKey.trim().length >= 20;

  return (
    <SafeAreaView style={styles.container}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={styles.inner}>
        <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.scroll}>
          <TouchableOpacity testID="review-back-btn" onPress={() => router.back()} style={styles.backBtn} accessibilityRole="button" accessibilityLabel="Back">
            <Ionicons name="arrow-back" size={24} color={Colors.text} />
          </TouchableOpacity>
          <View style={styles.header}>
            <Ionicons name="clipboard-outline" size={44} color={Colors.gold} />
            <Text style={styles.title}>Store reviewer access</Text>
            <Text style={styles.subtitle}>For Google Play / App Store review teams</Text>
          </View>

          <View style={styles.notice} testID="review-notice">
            <Text style={styles.noticeTitle}>Synthetic review environment</Text>
            <Text style={styles.noticeText}>
              Reviewer accounts open the same app screens, business rules and role permissions, but only against
              clearly labelled sample data. SMS, calls and messages are simulated and no real customer, price or
              stock record is read or changed. Access keys are issued privately by Yash Trade and can be reused.
            </Text>
          </View>

          <Text style={styles.label}>REVIEWER ID</Text>
          <TextInput testID="reviewer-id-input" style={styles.input} placeholder="e.g. store-review-customer" placeholderTextColor={Colors.textMuted}
            autoCapitalize="none" autoCorrect={false} value={reviewerId} onChangeText={(v) => { setReviewerId(v); setError(''); }} />
          <Text style={styles.label}>ACCESS KEY</Text>
          <View style={styles.keyRow}>
            <TextInput testID="reviewer-key-input" style={[styles.input, styles.keyInput]} placeholder="Paste the access key" placeholderTextColor={Colors.textMuted}
              autoCapitalize="none" autoCorrect={false} secureTextEntry={!showKey} value={accessKey} onChangeText={(v) => { setAccessKey(v); setError(''); }} />
            <TouchableOpacity testID="reviewer-key-toggle" onPress={() => setShowKey(s => !s)} style={styles.eye} accessibilityRole="button" accessibilityLabel={showKey ? 'Hide key' : 'Show key'}>
              <Ionicons name={showKey ? 'eye-off-outline' : 'eye-outline'} size={22} color={Colors.textSecondary} />
            </TouchableOpacity>
          </View>
          {error ? <Text testID="review-login-error" style={styles.error}>{error}</Text> : null}
          <TouchableOpacity testID="review-login-btn" style={[styles.btn, !ready && styles.btnDisabled]} onPress={submit} disabled={loading || !ready} accessibilityRole="button">
            {loading ? <ActivityIndicator color="#000" /> : <Text style={styles.btnText}>SIGN IN AS REVIEWER</Text>}
          </TouchableOpacity>
          <Text style={styles.hint}>Normal customers and staff sign in with their mobile number and SMS OTP.</Text>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  inner: { flex: 1 },
  scroll: { paddingHorizontal: Spacing.lg, paddingBottom: Spacing.xl },
  backBtn: { marginTop: Spacing.md, padding: Spacing.sm, alignSelf: 'flex-start', minWidth: 44, minHeight: 44, justifyContent: 'center' },
  header: { alignItems: 'center', marginTop: Spacing.md, marginBottom: Spacing.lg },
  title: { fontSize: FontSize.xl, fontWeight: '700', color: Colors.text, marginTop: Spacing.md },
  subtitle: { fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: Spacing.xs },
  notice: { backgroundColor: Colors.card, borderRadius: 12, borderWidth: 1, borderColor: Colors.borderGold, padding: Spacing.md, marginBottom: Spacing.lg },
  noticeTitle: { fontSize: FontSize.md, fontWeight: '700', color: Colors.gold, marginBottom: 6 },
  noticeText: { fontSize: FontSize.sm, color: Colors.textSecondary, lineHeight: 19 },
  label: { fontSize: FontSize.xs, color: Colors.textSecondary, letterSpacing: 2, marginBottom: Spacing.sm, fontWeight: '600' },
  input: { backgroundColor: Colors.surface, borderRadius: 12, borderWidth: 1, borderColor: Colors.border, paddingHorizontal: Spacing.md, paddingVertical: 14, fontSize: FontSize.base, color: Colors.text, marginBottom: Spacing.md },
  keyRow: { flexDirection: 'row', alignItems: 'center' },
  keyInput: { flex: 1, marginRight: Spacing.sm },
  eye: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center', marginBottom: Spacing.md },
  error: { color: Colors.error, fontSize: FontSize.sm, marginBottom: Spacing.sm },
  btn: { backgroundColor: Colors.gold, borderRadius: 12, paddingVertical: 16, alignItems: 'center', marginTop: Spacing.sm, minHeight: 52 },
  btnDisabled: { opacity: 0.4 },
  btnText: { fontSize: FontSize.base, fontWeight: '700', color: '#000', letterSpacing: 2 },
  hint: { fontSize: FontSize.xs, color: Colors.textMuted, textAlign: 'center', marginTop: Spacing.lg },
});
