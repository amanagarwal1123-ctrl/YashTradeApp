import React, { useCallback, useEffect, useRef, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextInput, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../../theme';
import { api } from '../../api';
import { showAlert } from '../../utils/alert';

type SmsLog = {
  id: string;
  phone: string;
  purpose: string;
  status: 'accepted' | 'rejected';
  error?: string | null;
  request_id?: string | null;
  sent_at: string;
  delivery_status: 'pending' | 'delivered' | 'failed' | 'dropped' | 'n/a';
  delivery_detail?: string;
  last_checked_at?: string | null;
};

type Diagnostics = {
  build: string;
  provider_check: 'ok' | 'FAILED';
  provider_message: string;
  checked_at: string;
  configured: boolean;
  authkey_valid: boolean | null;
  authkey_hint?: string | null;
  template_id?: string | null;
  template: {
    name?: string; sender_id?: string; dlt_id?: string; dlt_verified?: boolean; active?: boolean; version?: string; text?: string;
  };
  demo_mode: boolean;
  demo_phones: string[];
  counters_24h: { total: number; accepted: number; delivered: number; failed: number; dropped: number; pending: number; rejected: number };
  recent: SmsLog[];
};

const DELIVERY_META: Record<SmsLog['delivery_status'], { label: string; color: string }> = {
  delivered: { label: 'Delivered', color: Colors.success },
  failed: { label: 'Failed', color: Colors.error },
  dropped: { label: 'Dropped by MSG91', color: Colors.error },
  pending: { label: 'Pending', color: Colors.warning },
  'n/a': { label: 'Not sent', color: Colors.textMuted },
};

const PURPOSE_LABEL: Record<string, string> = { login_otp: 'Login OTP', phone_change: 'Phone change', admin_test: 'Admin test' };

const fmtTime = (iso?: string | null) => (iso ? new Date(iso).toLocaleString('en-IN', { hour12: true }) : '—');

export default function SmsDiagnostics() {
  const [diag, setDiag] = useState<Diagnostics | null>(null);
  const [loading, setLoading] = useState(true);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState('');
  const [testPhone, setTestPhone] = useState('');
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ phone: string; otp: string; requestId: string } | null>(null);
  const [recheckingId, setRecheckingId] = useState('');
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  const load = useCallback(async (force = false) => {
    if (force) setChecking(true); else setLoading(true);
    setError('');
    try {
      setDiag(await api.get(`/admin/sms/diagnostics${force ? '?force=true' : ''}`));
    } catch (e: any) {
      setError(e.message || 'Failed to load SMS diagnostics');
    } finally {
      setLoading(false); setChecking(false);
    }
  }, []);

  useEffect(() => {
    load();
    return () => { timers.current.forEach(clearTimeout); };
  }, [load]);

  // The server re-checks delivery at +6s/+20s/+60s — refresh the table just after each pass
  const scheduleRefresh = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [8000, 24000, 66000].map(ms => setTimeout(() => load(), ms));
  };

  const sendTest = async () => {
    if (testPhone.length !== 10) { showAlert('Invalid number', 'Enter a 10-digit mobile number.'); return; }
    setTesting(true); setTestResult(null);
    try {
      const r = await api.post('/admin/sms/test', { phone: testPhone });
      setTestResult({ phone: testPhone, otp: r.otp, requestId: r.log?.request_id || '' });
      load(); scheduleRefresh();
    } catch (e: any) {
      showAlert('Test SMS was NOT sent', e.message);
      load();
    } finally {
      setTesting(false);
    }
  };

  const recheck = async (id: string) => {
    setRecheckingId(id);
    try {
      const updated: SmsLog = await api.post(`/admin/sms/logs/${id}/recheck`);
      setDiag(d => (d ? { ...d, recent: d.recent.map(r => (r.id === id ? updated : r)) } : d));
    } catch (e: any) {
      showAlert('Re-check failed', e.message);
    } finally {
      setRecheckingId('');
    }
  };

  if (loading && !diag) return <ActivityIndicator color={Colors.gold} style={{ marginTop: 40 }} />;

  if (!diag) {
    return (
      <View style={st.card}>
        <Text style={st.errorText}>{error || 'Diagnostics unavailable'}</Text>
        <TouchableOpacity testID="sms-retry" style={st.primaryBtn} onPress={() => load()}><Text style={st.primaryBtnText}>RETRY</Text></TouchableOpacity>
      </View>
    );
  }

  const ok = diag.provider_check === 'ok';
  const statusColor = ok ? Colors.success : Colors.error;
  const tpl = diag.template || {};
  const c = diag.counters_24h;

  return (
    <View testID="sms-diagnostics">
      <View style={st.titleRow}>
        <Text style={st.sectionTitle}>SMS PROVIDER (MSG91) – LIVE DIAGNOSTICS</Text>
        <TouchableOpacity testID="sms-recheck-provider" style={st.ghostBtn} onPress={() => load(true)} disabled={checking}>
          {checking ? <ActivityIndicator size="small" color={Colors.gold} /> : <Ionicons name="refresh" size={14} color={Colors.gold} />}
          <Text style={st.ghostBtnText}>RE-RUN CHECK</Text>
        </TouchableOpacity>
      </View>
      {error ? <Text style={st.errorText}>{error}</Text> : null}

      {/* Provider status */}
      <View style={[st.card, { borderColor: statusColor + '60' }]}>
        <View style={st.statusHead}>
          <View style={[st.statusBadge, { backgroundColor: statusColor + '20' }]}>
            <Ionicons name={ok ? 'checkmark-circle' : 'alert-circle'} size={16} color={statusColor} />
            <Text testID="sms-provider-status" style={[st.statusBadgeText, { color: statusColor }]}>{ok ? 'PROVIDER OK' : 'PROVIDER FAILED'}</Text>
          </View>
          <Text style={st.meta}>build {diag.build}</Text>
        </View>
        <Text testID="sms-provider-message" style={[st.statusMsg, !ok && { color: Colors.error }]}>{diag.provider_message}</Text>
        <Text style={st.meta}>Checked from this server at {fmtTime(diag.checked_at)} • cached 5 min</Text>

        <View style={st.kvGrid}>
          <KV label="Authkey" value={diag.authkey_valid === null ? (diag.configured ? 'Not checked' : 'Missing') : diag.authkey_valid ? `Valid ${diag.authkey_hint || ''}` : 'INVALID'} color={diag.authkey_valid ? Colors.success : Colors.error} />
          <KV label="Template ID" value={diag.template_id || 'Missing'} color={diag.template_id ? Colors.text : Colors.error} mono />
          <KV label="Template" value={tpl.name ? `${tpl.name} (${tpl.version || 'v?'})` : '—'} />
          <KV label="Sender ID" value={tpl.sender_id || '—'} />
          <KV label="DLT Template ID" value={tpl.dlt_id || '—'} mono />
          <KV label="DLT verified flag" value={tpl.dlt_id ? (tpl.dlt_verified ? 'Yes' : 'No (MSG91 flag)') : '—'} color={tpl.dlt_verified ? Colors.success : Colors.warning} />
          <KV label="Active version" value={tpl.dlt_id ? (tpl.active ? 'Yes' : 'NO') : '—'} color={tpl.active ? Colors.success : Colors.error} />
          <KV label="Demo mode" value={diag.demo_mode ? 'ON — all numbers get 1234' : `Off • ${diag.demo_phones.length} allow-listed`} color={diag.demo_mode ? Colors.warning : Colors.textSecondary} />
        </View>
        {tpl.text ? <Text style={st.templateText}>“{tpl.text}”</Text> : null}
      </View>

      {/* 24h counters */}
      <Text style={st.sectionTitle}>LAST 24 HOURS</Text>
      <View style={st.statsGrid}>
        <Stat label="Accepted" value={c.accepted} color={Colors.info} />
        <Stat label="Delivered" value={c.delivered} color={Colors.success} />
        <Stat label="Failed" value={c.failed} color={Colors.error} />
        <Stat label="Dropped" value={c.dropped} color={Colors.error} />
        <Stat label="Pending" value={c.pending} color={Colors.warning} />
        <Stat label="Rejected" value={c.rejected} color={Colors.textMuted} />
      </View>

      {/* Send test */}
      <Text style={st.sectionTitle}>SEND TEST SMS</Text>
      <View style={st.card}>
        <Text style={st.hint}>Sends a real OTP SMS through the exact production path (uses one MSG91 credit). Delivery is confirmed against MSG91's log at +6s, +20s and +60s.</Text>
        <View style={st.testRow}>
          <TextInput
            testID="sms-test-phone"
            style={st.input}
            value={testPhone}
            onChangeText={v => setTestPhone(v.replace(/\D/g, '').slice(0, 10))}
            placeholder="10-digit mobile number"
            placeholderTextColor={Colors.textMuted}
            keyboardType="phone-pad"
            maxLength={10}
          />
          <TouchableOpacity testID="sms-test-send" style={[st.primaryBtn, (testing || testPhone.length !== 10 || !ok) && st.btnDisabled]} onPress={sendTest} disabled={testing || testPhone.length !== 10 || !ok}>
            {testing ? <ActivityIndicator size="small" color="#000" /> : <Text style={st.primaryBtnText}>SEND TEST</Text>}
          </TouchableOpacity>
        </View>
        {!ok && <Text style={st.errorText}>Fix the provider configuration above before sending — MSG91 would silently drop the message.</Text>}
        {testResult && (
          <View testID="sms-test-result" style={st.resultBox}>
            <Ionicons name="paper-plane" size={16} color={Colors.success} />
            <Text style={st.resultText}>
              Accepted by MSG91 for {testResult.phone} — the SMS should read OTP <Text style={st.bold}>{testResult.otp}</Text>.
              {testResult.requestId ? ` Request ID ${testResult.requestId}.` : ''} Delivery status updates below.
            </Text>
          </View>
        )}
      </View>

      {/* Recent messages */}
      <View style={st.titleRow}>
        <Text style={st.sectionTitle}>RECENT MESSAGES ({diag.recent.length})</Text>
        <TouchableOpacity testID="sms-refresh-list" style={st.ghostBtn} onPress={() => load()}>
          <Ionicons name="reload" size={14} color={Colors.gold} /><Text style={st.ghostBtnText}>REFRESH</Text>
        </TouchableOpacity>
      </View>
      {diag.recent.length === 0 && <Text style={st.emptyText}>No SMS sent from this server yet.</Text>}
      {diag.recent.map(row => {
        const rejected = row.status === 'rejected';
        const meta = DELIVERY_META[row.delivery_status] || DELIVERY_META['n/a'];
        const color = rejected ? Colors.error : meta.color;
        return (
          <View key={row.id} testID={`sms-row-${row.id}`} style={st.row}>
            <View style={st.rowTop}>
              <View style={{ flex: 1 }}>
                <Text style={st.rowPhone}>{row.phone} <Text style={st.rowPurpose}>• {PURPOSE_LABEL[row.purpose] || row.purpose}</Text></Text>
                <Text style={st.meta}>{fmtTime(row.sent_at)}{row.request_id ? ` • req ${row.request_id}` : ''}</Text>
              </View>
              <View style={[st.pill, { backgroundColor: color + '20' }]}>
                <Text style={[st.pillText, { color }]}>{rejected ? 'REJECTED' : meta.label.toUpperCase()}</Text>
              </View>
            </View>
            <Text style={[st.rowDetail, (rejected || row.delivery_status === 'failed' || row.delivery_status === 'dropped') && { color: Colors.error }]}>
              {rejected ? row.error : row.delivery_detail || '—'}
            </Text>
            {!rejected && row.delivery_status !== 'delivered' && row.delivery_status !== 'failed' && (
              <TouchableOpacity testID={`sms-recheck-${row.id}`} style={st.ghostBtn} onPress={() => recheck(row.id)} disabled={recheckingId === row.id}>
                {recheckingId === row.id ? <ActivityIndicator size="small" color={Colors.gold} /> : <Ionicons name="search" size={13} color={Colors.gold} />}
                <Text style={st.ghostBtnText}>RE-CHECK DELIVERY</Text>
              </TouchableOpacity>
            )}
            {row.last_checked_at ? <Text style={st.meta}>Last checked {fmtTime(row.last_checked_at)}</Text> : null}
          </View>
        );
      })}
    </View>
  );
}

function KV({ label, value, color, mono }: { label: string; value: string; color?: string; mono?: boolean }) {
  return (
    <View style={st.kv}>
      <Text style={st.kvLabel}>{label}</Text>
      <Text style={[st.kvValue, color ? { color } : null, mono && st.mono]} numberOfLines={2}>{value}</Text>
    </View>
  );
}

function Stat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <View style={st.stat}>
      <Text style={[st.statVal, { color }]}>{value}</Text>
      <Text style={st.statLbl}>{label}</Text>
    </View>
  );
}

const st = StyleSheet.create({
  titleRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: Spacing.sm },
  sectionTitle: { fontSize: FontSize.xs, color: Colors.textSecondary, letterSpacing: 2, fontWeight: '700', marginTop: Spacing.lg, marginBottom: Spacing.md, flexShrink: 1 },
  card: { backgroundColor: Colors.card, borderRadius: 14, padding: Spacing.md, borderWidth: 1, borderColor: Colors.cardBorder, marginBottom: Spacing.sm },
  statusHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: Spacing.sm, flexWrap: 'wrap' },
  statusBadge: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8 },
  statusBadgeText: { fontSize: FontSize.sm, fontWeight: '700', letterSpacing: 1 },
  statusMsg: { fontSize: FontSize.md, color: Colors.text, marginTop: Spacing.sm, lineHeight: 20 },
  meta: { fontSize: FontSize.xs, color: Colors.textMuted, marginTop: 4 },
  kvGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: Spacing.md },
  kv: { width: '47%', minWidth: 140, backgroundColor: Colors.surface, borderRadius: 10, padding: 10 },
  kvLabel: { fontSize: FontSize.xs, color: Colors.textMuted, marginBottom: 2 },
  kvValue: { fontSize: FontSize.sm, color: Colors.text, fontWeight: '600' },
  mono: { fontFamily: 'monospace', fontSize: FontSize.xs, fontWeight: '500' },
  templateText: { fontSize: FontSize.xs, color: Colors.textSecondary, fontStyle: 'italic', marginTop: Spacing.md, lineHeight: 16 },
  statsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  stat: { width: '30%', minWidth: 96, backgroundColor: Colors.card, borderRadius: 14, padding: Spacing.md, alignItems: 'center', gap: 4, borderWidth: 1, borderColor: Colors.cardBorder },
  statVal: { fontSize: FontSize.xl, fontWeight: '700' },
  statLbl: { fontSize: FontSize.xs, color: Colors.textMuted },
  hint: { fontSize: FontSize.xs, color: Colors.textSecondary, lineHeight: 16, marginBottom: Spacing.sm },
  testRow: { flexDirection: 'row', gap: 8, alignItems: 'center', flexWrap: 'wrap' },
  input: { flex: 1, minWidth: 160, backgroundColor: Colors.surface, borderRadius: 10, paddingHorizontal: Spacing.md, paddingVertical: 12, fontSize: FontSize.md, color: Colors.text, borderWidth: 1, borderColor: Colors.border },
  primaryBtn: { backgroundColor: Colors.gold, paddingVertical: 12, paddingHorizontal: 18, borderRadius: 10, alignItems: 'center', justifyContent: 'center', minHeight: 44 },
  primaryBtnText: { fontSize: FontSize.sm, fontWeight: '700', color: '#000', letterSpacing: 2 },
  btnDisabled: { opacity: 0.45 },
  ghostBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 8, borderRadius: 8, alignSelf: 'flex-start', minHeight: 36 },
  ghostBtnText: { fontSize: FontSize.xs, color: Colors.gold, fontWeight: '700', letterSpacing: 1 },
  resultBox: { flexDirection: 'row', gap: 8, alignItems: 'flex-start', backgroundColor: Colors.success + '12', borderRadius: 10, padding: 10, marginTop: Spacing.sm },
  resultText: { flex: 1, fontSize: FontSize.sm, color: Colors.text, lineHeight: 18 },
  bold: { fontWeight: '700', color: Colors.gold },
  errorText: { fontSize: FontSize.sm, color: Colors.error, marginTop: Spacing.sm, lineHeight: 18 },
  emptyText: { fontSize: FontSize.md, color: Colors.textMuted, textAlign: 'center', marginVertical: Spacing.lg },
  row: { backgroundColor: Colors.card, borderRadius: 12, padding: Spacing.md, marginBottom: Spacing.sm, borderWidth: 1, borderColor: Colors.cardBorder },
  rowTop: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm },
  rowPhone: { fontSize: FontSize.md, fontWeight: '600', color: Colors.text },
  rowPurpose: { fontSize: FontSize.xs, color: Colors.textMuted, fontWeight: '500' },
  rowDetail: { fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: 6, lineHeight: 18 },
  pill: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6 },
  pillText: { fontSize: 9, fontWeight: '700', letterSpacing: 0.5 },
});
