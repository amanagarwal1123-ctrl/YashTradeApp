import React, { useCallback, useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, TextInput, ActivityIndicator, Platform } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as Clipboard from 'expo-clipboard';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api, API_BASE, BACKEND_URL } from '../src/api';
import { showAlert, confirmAlert } from '../src/utils/alert';
import { useAuth } from '../src/context/AuthContext';

type Action = 'provision' | 'rotate' | 'revoke' | 'reset_data';
interface Account { reviewer_id: string; role: string; role_label: string; exists: boolean; enabled: boolean; rotated_at?: string | null; revoked_at?: string | null; last_login_at?: string | null; }
interface Status { enabled: boolean; usable: boolean; storage: string; isolation: string; database: string; accounts: Account[]; missing_accounts?: string[]; dataset?: any; review_state: { reason?: string | null; detail: string }; sign_in_steps: string[]; store_form_text: string[]; fresh_authentication: string; }
interface Issued { reviewer_id: string; role: string; role_label: string; access_key: string; }
interface KeysResult { action: Action; issued: Issued[]; unchanged: string[]; note_text: string | null; detail: string; revoked?: any; accounts: Account[]; }

const ENVIRONMENT: 'preview' | 'production' = /preview\.emergentagent\.com/.test(BACKEND_URL) ? 'preview' : 'production';
const fmt = (v?: string | null) => (v ? new Date(v).toLocaleString() : '—');

async function downloadNote(text: string) {
  const name = `yash-review-access-${ENVIRONMENT}-${new Date().toISOString().slice(0, 10)}.txt`;
  if (Platform.OS === 'web') {
    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = name; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    return;
  }
  const FileSystem = await import('expo-file-system/legacy');
  const Sharing = await import('expo-sharing');
  const path = `${FileSystem.cacheDirectory}${name}`;
  await FileSystem.writeAsStringAsync(path, text);
  if (await Sharing.isAvailableAsync()) await Sharing.shareAsync(path, { mimeType: 'text/plain', dialogTitle: 'Save the private reviewer-access note' });
  else showAlert('Sharing unavailable', 'Use the copy buttons instead.');
  setTimeout(() => FileSystem.deleteAsync(path, { idempotent: true }).catch(() => {}), 60000);
}

/** Owner-only console: provision / rotate / revoke store-review accounts with a fresh OTP; keys are shown once. */
export default function ReviewKeysScreen() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState<{ code?: string; message: string } | null>(null);
  const [pending, setPending] = useState<{ action: Action; reviewer_id?: string } | null>(null);
  const [challenge, setChallenge] = useState<{ challenge_id: string; resend_after: number } | null>(null);
  const [otp, setOtp] = useState('');
  const [busy, setBusy] = useState(false);
  const [otpError, setOtpError] = useState('');
  const [result, setResult] = useState<KeysResult | null>(null);
  const [copied, setCopied] = useState('');

  const load = useCallback(async () => {
    try { setStatus(await api.get('/admin/review/status')); setError(null); }
    catch (e: any) { setError({ code: e?.code, message: e?.message || 'Could not load the store-review status' }); }
  }, []);
  useEffect(() => {
    if (authLoading) return;
    if (!user) { router.replace('/login'); return; }
    load();
  }, [authLoading, user?.id, load]);

  const begin = (action: Action, reviewer_id?: string) => {
    const start = async () => {
      setBusy(true); setOtp(''); setOtpError(''); setResult(null);
      try {
        const res = await api.post('/admin/review/challenge');
        setPending({ action, reviewer_id }); setChallenge({ challenge_id: res.challenge_id, resend_after: res.resend_after });
      } catch (e: any) { showAlert('OTP not sent', e?.message || 'Please try again.'); }
      finally { setBusy(false); }
    };
    if (action === 'revoke') confirmAlert('Revoke this reviewer account?', `${reviewer_id} will be disabled and its sessions ended. A later rotation re-enables it with a new key.`, start, 'Revoke');
    else if (action === 'rotate') confirmAlert('Rotate this key?', `The current key for ${reviewer_id} stops working immediately, including in the store review forms, and its live sessions end.`, start, 'Rotate');
    else if (action === 'reset_data') confirmAlert('Reset the sample data?', 'Every sample record in the store-review environment is wiped and rebuilt and all reviewer sessions are signed out. The four access keys stay valid. Live customer data is never touched.', start, 'Reset');
    else start();
  };

  const submit = async () => {
    if (!pending || !challenge || otp.length !== 4) { setOtpError('Enter the 4-digit OTP'); return; }
    setBusy(true); setOtpError('');
    try {
      const res: KeysResult = await api.post('/admin/review/keys', { action: pending.action, reviewer_id: pending.reviewer_id || '', otp, challenge_id: challenge.challenge_id, environment: ENVIRONMENT, api_base_url: API_BASE });
      setResult(res); setPending(null); setChallenge(null); setOtp('');
      setStatus(prev => prev ? { ...prev, accounts: res.accounts, missing_accounts: res.accounts.filter(a => !a.exists).map(a => a.reviewer_id) } : prev);
    } catch (e: any) { setOtpError(e?.message || 'Could not complete the action'); }
    finally { setBusy(false); }
  };

  const copy = async (label: string, text: string) => {
    await Clipboard.setStringAsync(text); setCopied(label); setTimeout(() => setCopied(''), 2000);
  };

  const missing = status?.missing_accounts || [];

  return (
    <SafeAreaView style={st.container} edges={['top']}>
      <View style={st.header}>
        <TouchableOpacity testID="review-keys-back" onPress={() => router.back()} style={st.backBtn}><Ionicons name="arrow-back" size={24} color={Colors.text} /></TouchableOpacity>
        <Text style={st.headerTitle}>Store review access</Text>
        <TouchableOpacity testID="review-keys-refresh" onPress={load} style={st.backBtn}><Ionicons name="refresh" size={20} color={Colors.text} /></TouchableOpacity>
      </View>
      <ScrollView contentContainerStyle={st.content} keyboardShouldPersistTaps="handled">
        <View style={[st.envBadge, ENVIRONMENT === 'production' ? st.envProd : st.envPreview]}>
          <Ionicons name={ENVIRONMENT === 'production' ? 'cloud-done-outline' : 'flask-outline'} size={14} color="#000" />
          <Text style={st.envText}>{ENVIRONMENT.toUpperCase()} · {BACKEND_URL.replace(/^https?:\/\//, '')}</Text>
        </View>

        {error ? (
          <View style={st.card} testID="review-keys-error">
            <Ionicons name="lock-closed-outline" size={28} color={Colors.error} />
            <Text style={st.errorTitle}>{error.code === 'OWNER_ADMIN_REQUIRED' ? 'Owner administrator only' : error.code === 'REVIEW_SCOPE_FORBIDDEN' ? 'Not available in the store-review environment' : 'Unavailable'}</Text>
            <Text style={st.muted}>{error.message}</Text>
          </View>
        ) : !status ? <ActivityIndicator color={Colors.gold} style={{ marginTop: 40 }} /> : (
          <>
            <View style={st.card}>
              <Text style={st.cardTitle}>Environment</Text>
              <Row label="Review access" value={status.enabled ? (status.usable ? 'ON · usable' : `ON · not usable (${status.review_state.reason})`) : 'OFF (REVIEW_ACCESS_ENABLED)'} ok={status.usable} />
              <Row label="Storage" value={`${status.storage} in database ${status.database}`} />
              <Row label="Isolation" value={`${status.isolation.replace('_', '-')} (server session scope, not database-level)`} />
              <Row label="Key operations" value={`Fresh ${status.fresh_authentication}`} />
              {status.dataset ? <Row label="Sample data" value={`${status.dataset.users} users · ${status.dataset.products} products · ${status.dataset.requests} enquiries`} /> : null}
            </View>

            <View style={st.card}>
              <Text style={st.cardTitle}>Reviewer accounts</Text>
              {status.accounts.map(a => (
                <View key={a.reviewer_id} style={st.accountRow} testID={`review-account-${a.reviewer_id}`}>
                  <View style={{ flex: 1 }}>
                    <Text style={st.accountId}>{a.reviewer_id}</Text>
                    <Text style={st.muted}>{a.role_label}</Text>
                    <Text style={[st.state, { color: !a.exists ? Colors.textMuted : a.enabled ? Colors.success : Colors.error }]}>
                      {!a.exists ? 'not provisioned' : a.enabled ? 'enabled' : `revoked ${fmt(a.revoked_at)}`}
                    </Text>
                    {a.exists ? <Text style={st.muted}>last sign-in {fmt(a.last_login_at)} · key rotated {fmt(a.rotated_at)}</Text> : null}
                  </View>
                  {a.exists && status.usable ? (
                    <View style={st.actions}>
                      <TouchableOpacity testID={`rotate-${a.reviewer_id}`} style={st.smallBtn} onPress={() => begin('rotate', a.reviewer_id)} disabled={busy}><Text style={st.smallBtnText}>ROTATE</Text></TouchableOpacity>
                      {a.enabled ? <TouchableOpacity testID={`revoke-${a.reviewer_id}`} style={[st.smallBtn, st.smallDanger]} onPress={() => begin('revoke', a.reviewer_id)} disabled={busy}><Text style={[st.smallBtnText, { color: Colors.error }]}>REVOKE</Text></TouchableOpacity> : null}
                    </View>
                  ) : null}
                </View>
              ))}
              {status.usable ? (
                <>
                  <TouchableOpacity testID="review-provision" style={[st.primaryBtn, (busy || missing.length === 0) && { opacity: 0.5 }]} onPress={() => begin('provision')} disabled={busy || missing.length === 0}>
                    {busy && !pending ? <ActivityIndicator color="#000" /> : <Text style={st.primaryText}>{missing.length ? `PROVISION ${missing.length} MISSING ACCOUNT${missing.length > 1 ? 'S' : ''} + SAMPLE DATA` : 'ALL 4 ACCOUNTS EXIST — USE ROTATE FOR A NEW KEY'}</Text>}
                  </TouchableOpacity>
                  <TouchableOpacity testID="review-reset-data" style={[st.secondaryBtn, busy && { opacity: 0.5 }]} onPress={() => begin('reset_data')} disabled={busy}>
                    <Text style={st.secondaryText}>RESET SAMPLE DATA (KEEPS THE 4 KEYS)</Text>
                  </TouchableOpacity>
                </>
              ) : <Text style={st.muted}>Switch REVIEW_ACCESS_ENABLED on for this deployment and redeploy before provisioning.</Text>}
              <Text style={st.footnote}>Provisioning never changes an existing key. Only an explicit ROTATE invalidates a key and its sessions. Reset rebuilds the sample records (e.g. after a reviewer deleted the sample profile) and signs every reviewer out.</Text>
            </View>

            {pending && challenge ? (
              <View style={[st.card, st.otpCard]} testID="review-otp-card">
                <Text style={st.cardTitle}>Confirm with a fresh OTP</Text>
                <Text style={st.muted}>Action: {pending.action === 'reset_data' ? 'reset sample data' : pending.action}{pending.reviewer_id ? ` · ${pending.reviewer_id}` : pending.action === 'provision' ? ' · all missing accounts' : ''}. A 4-digit code was sent to your registered owner number; it is valid once for 10 minutes.</Text>
                <TextInput testID="review-otp-input" style={st.otpInput} placeholder="OTP" placeholderTextColor={Colors.textMuted} keyboardType="number-pad" maxLength={4}
                  value={otp} onChangeText={v => { setOtp(v.replace(/[^0-9]/g, '')); setOtpError(''); }} autoComplete="one-time-code" textContentType="oneTimeCode" />
                {otpError ? <Text testID="review-otp-error" style={st.errorText}>{otpError}</Text> : null}
                <TouchableOpacity testID="review-otp-submit" style={[st.primaryBtn, (busy || otp.length !== 4) && { opacity: 0.5 }]} onPress={submit} disabled={busy || otp.length !== 4}>
                  {busy ? <ActivityIndicator color="#000" /> : <Text style={st.primaryText}>CONFIRM {pending.action === 'reset_data' ? 'RESET' : pending.action.toUpperCase()}</Text>}
                </TouchableOpacity>
                <TouchableOpacity testID="review-otp-cancel" style={st.linkBtn} onPress={() => { setPending(null); setChallenge(null); setOtp(''); }}><Text style={st.linkText}>Cancel</Text></TouchableOpacity>
              </View>
            ) : null}

            {result ? (
              <View style={[st.card, result.issued.length ? st.resultCard : null]} testID="review-keys-result">
                <Text style={st.cardTitle}>{result.issued.length ? 'New access keys — shown once' : 'Done'}</Text>
                <Text style={st.muted}>{result.detail}</Text>
                {result.issued.map(k => (
                  <View key={k.reviewer_id} style={st.keyBox} testID={`issued-${k.reviewer_id}`}>
                    <Text style={st.accountId}>{k.reviewer_id} <Text style={st.muted}>· {k.role_label}</Text></Text>
                    <Text selectable style={st.keyText}>{k.access_key}</Text>
                    <TouchableOpacity testID={`copy-${k.reviewer_id}`} style={st.smallBtn} onPress={() => copy(k.reviewer_id, `Reviewer ID: ${k.reviewer_id}\nAccess key: ${k.access_key}`)}>
                      <Text style={st.smallBtnText}>{copied === k.reviewer_id ? 'COPIED' : 'COPY ID + KEY'}</Text>
                    </TouchableOpacity>
                  </View>
                ))}
                {result.note_text ? (
                  <View style={st.actionsRow}>
                    <TouchableOpacity testID="copy-note" style={st.primaryBtn} onPress={() => copy('note', result.note_text!)}><Text style={st.primaryText}>{copied === 'note' ? 'NOTE COPIED' : 'COPY PRIVATE NOTE'}</Text></TouchableOpacity>
                    <TouchableOpacity testID="download-note" style={st.secondaryBtn} onPress={() => downloadNote(result.note_text!).catch(e => showAlert('Download failed', e?.message))}><Text style={st.secondaryText}>DOWNLOAD .TXT</Text></TouchableOpacity>
                  </View>
                ) : null}
                {result.issued.length ? <Text style={st.warn}>Save the note in a private place now. The server keeps only hashes; these keys cannot be shown again — only rotated. Never paste them into chat, tickets or screenshots.</Text> : null}
              </View>
            ) : null}

            <View style={st.card}>
              <Text style={st.cardTitle}>Entering the credentials in the stores</Text>
              <Text style={st.sub}>GOOGLE PLAY CONSOLE</Text>
              <Text style={st.item}>App content → App access → &ldquo;All or some functionality is restricted&rdquo; → Add instructions: Reviewer ID as username, Access key as password, plus the sign-in steps below. Add the customer account first; add the admin, telecaller and billing accounts as additional credentials with their role labels.</Text>
              <Text style={st.sub}>APP STORE CONNECT</Text>
              <Text style={st.item}>App Review Information → Sign-in required → User name = Reviewer ID, Password = Access key (customer account). Put the other three accounts and the sign-in steps in Notes.</Text>
              <Text style={st.sub}>SIGN-IN STEPS FOR REVIEWERS</Text>
              {status.sign_in_steps.map(s => <Text key={s} style={st.item}>{s}</Text>)}
              <Text style={st.sub}>NOTES TEXT</Text>
              {status.store_form_text.map(s => <Text key={s} style={st.item}>• {s}</Text>)}
            </View>
          </>
        )}
        <View style={{ height: 40 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const Row = ({ label, value, ok }: { label: string; value: string; ok?: boolean }) => (
  <View style={st.row}>
    <Text style={st.rowLabel}>{label}</Text>
    <Text style={[st.rowValue, ok === false && { color: Colors.warning }]}>{value}</Text>
  </View>
);

const st = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md },
  backBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: Colors.surface, alignItems: 'center', justifyContent: 'center' },
  headerTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text },
  content: { paddingHorizontal: Spacing.lg, gap: Spacing.md },
  envBadge: { flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6 },
  envProd: { backgroundColor: Colors.gold }, envPreview: { backgroundColor: Colors.warning },
  envText: { fontSize: FontSize.xs, fontWeight: '700', color: '#000', letterSpacing: 0.5 },
  card: { backgroundColor: Colors.card, borderRadius: 16, borderWidth: 1, borderColor: Colors.cardBorder, padding: Spacing.md, gap: 8 },
  otpCard: { borderColor: Colors.gold + '80' }, resultCard: { borderColor: Colors.gold },
  cardTitle: { fontSize: FontSize.md, fontWeight: '700', color: Colors.text },
  row: { flexDirection: 'row', gap: 10 }, rowLabel: { width: 110, fontSize: FontSize.xs, color: Colors.textMuted }, rowValue: { flex: 1, fontSize: FontSize.xs, color: Colors.textSecondary },
  accountRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: Colors.border },
  accountId: { fontSize: FontSize.sm, fontWeight: '700', color: Colors.text },
  state: { fontSize: FontSize.xs, fontWeight: '600', marginTop: 2 },
  actions: { gap: 6 }, actionsRow: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  smallBtn: { borderWidth: 1, borderColor: Colors.gold, borderRadius: 8, paddingHorizontal: 10, minHeight: 36, justifyContent: 'center', alignItems: 'center' },
  smallDanger: { borderColor: Colors.error },
  smallBtnText: { fontSize: FontSize.xs, fontWeight: '700', color: Colors.gold, letterSpacing: 0.5 },
  primaryBtn: { backgroundColor: Colors.gold, borderRadius: 10, paddingVertical: 14, paddingHorizontal: 14, alignItems: 'center', minHeight: 48, justifyContent: 'center', flexGrow: 1 },
  primaryText: { fontSize: FontSize.xs, fontWeight: '700', color: '#000', letterSpacing: 1, textAlign: 'center' },
  secondaryBtn: { borderWidth: 1, borderColor: Colors.gold, borderRadius: 10, paddingVertical: 14, paddingHorizontal: 14, alignItems: 'center', minHeight: 48, justifyContent: 'center', flexGrow: 1 },
  secondaryText: { fontSize: FontSize.xs, fontWeight: '700', color: Colors.gold, letterSpacing: 1 },
  linkBtn: { alignItems: 'center', minHeight: 44, justifyContent: 'center' }, linkText: { color: Colors.textMuted, fontWeight: '600', fontSize: FontSize.sm },
  otpInput: { backgroundColor: Colors.surface, borderRadius: 10, borderWidth: 1, borderColor: Colors.border, color: Colors.text, paddingHorizontal: 14, paddingVertical: 12, fontSize: FontSize.lg, textAlign: 'center', letterSpacing: 8, fontWeight: '700' },
  keyBox: { backgroundColor: Colors.surface, borderRadius: 12, padding: Spacing.sm, gap: 6 },
  keyText: { fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace', default: 'monospace' }), fontSize: FontSize.sm, color: Colors.text },
  muted: { fontSize: FontSize.xs, color: Colors.textMuted, lineHeight: 17 },
  footnote: { fontSize: FontSize.xs, color: Colors.textMuted, marginTop: 4 },
  warn: { fontSize: FontSize.xs, color: Colors.warning, lineHeight: 17 },
  sub: { fontSize: FontSize.xs, color: Colors.textSecondary, letterSpacing: 1.2, fontWeight: '600', marginTop: 4 },
  item: { fontSize: FontSize.xs, color: Colors.textSecondary, lineHeight: 17 },
  errorTitle: { fontSize: FontSize.md, fontWeight: '700', color: Colors.text },
  errorText: { fontSize: FontSize.sm, color: Colors.error, textAlign: 'center' },
});
