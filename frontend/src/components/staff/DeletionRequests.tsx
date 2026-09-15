import React, { useCallback, useEffect, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextInput, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../../theme';
import MaintenanceCard from './MaintenanceCard';
import { api } from '../../api';
import { showAlert } from '../../utils/alert';

type ProviderKey = 'sms_provider' | 'ai_provider' | 'object_storage';
type ProviderState = 'not_applicable' | 'not_requested' | 'requested' | 'no_procedure' | 'confirmed' | 'refused';
interface ProviderEntry {
  provider: string; state: ProviderState; data_present: boolean | 'unknown'; procedure: string; holds: string;
  requested_at?: string | null; request_reference?: string | null; channel?: string | null; outcome?: string | null; outcome_at?: string | null;
  retention_exception?: { reason: string; basis?: string; review_at?: string | null; recorded_at?: string } | null; note?: string;
}
interface DeletionRow {
  reference: string; source: string; requested_at: string; status: string;
  cleanup: { app: string; website: string; website_acknowledged_at?: string | null; completed_at?: string | null; note?: string; resumed?: { at: string; actor_id: string }[] };
  provider_erasure: 'not_applicable' | 'outstanding' | 'completed' | 'retained_with_exception' | 'superseded';
  providers: Record<ProviderKey, ProviderEntry>;
}

const fmt = (v?: string | null) => (v ? new Date(v).toLocaleString() : '—');
const STATUS_LABEL: Record<string, string> = { local_cleanup_pending: 'APP CLEANUP INTERRUPTED · RESUME', external_erasure_pending: 'APP DONE · WEBSITE ACK PENDING', cleanup_completed: 'APP + WEBSITE CLEANUP COMPLETED', superseded_reactivated: 'SUPERSEDED · ACCOUNT ACTIVE AGAIN', completed: 'OLDER ROW · RECONCILE FIRST' };
const STATUS_COLOR: Record<string, string> = { cleanup_completed: Colors.success, superseded_reactivated: Colors.textMuted };
const ERASURE_LABEL: Record<string, string> = { not_applicable: 'NO PROVIDER DATA', outstanding: 'PROVIDER ERASURE OUTSTANDING', completed: 'PROVIDER ERASURE CONFIRMED', retained_with_exception: 'RETAINED · EXCEPTION RECORDED', superseded: 'NO ERASURE OWED' };
const ERASURE_COLOR: Record<string, string> = { not_applicable: Colors.textMuted, outstanding: Colors.warning, completed: Colors.success, retained_with_exception: Colors.info, superseded: Colors.textMuted };
const STATE_COLOR: Record<ProviderState, string> = { not_applicable: Colors.textMuted, not_requested: Colors.warning, requested: Colors.info, no_procedure: Colors.warning, confirmed: Colors.success, refused: Colors.info };

/** Admin ledger: app/website cleanup and provider erasure shown as two separate outcomes; manual provider requests recorded here. */
export default function DeletionRequests() {
  const [rows, setRows] = useState<DeletionRow[] | null>(null);
  const [error, setError] = useState<{ code?: string; message: string } | null>(null);
  const [open, setOpen] = useState<string>('');

  const load = useCallback(async () => {
    try { const d = await api.get('/admin/deletion-requests'); setRows(d.requests || []); setError(null); }
    catch (e: any) { setError({ code: e?.code, message: e?.message || 'Could not load deletion requests' }); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (error) {
    return <Text testID="deletion-ledger-error" style={st.muted}>{error.code === 'PERMISSION_DENIED' ? 'Administrator only.' : error.message}</Text>;
  }
  if (!rows) return <ActivityIndicator color={Colors.gold} style={{ marginVertical: Spacing.md }} />;
  return (
    <View testID="deletion-ledger">
      <MaintenanceCard onApplied={load} />
      <Text style={st.sectionTitle}>ACCOUNT DELETION REQUESTS ({rows.length})</Text>
      <Text style={st.legend}>Two outcomes per request, never merged: app + website cleanup, and erasure by each service provider (manual request, recorded here). A website acknowledgement does not erase provider copies.</Text>
      {rows.length === 0 && <Text style={[st.muted, { textAlign: 'center', marginBottom: Spacing.lg }]}>No deletion requests yet.</Text>}
      {rows.map(d => (
        <View key={d.reference} style={st.card} testID={`deletion-row-${d.reference}`}>
          <TouchableOpacity style={st.head} onPress={() => setOpen(open === d.reference ? '' : d.reference)} testID={`deletion-toggle-${d.reference}`}>
            <View style={{ flex: 1 }}>
              <Text style={st.ref}>{d.reference}</Text>
              <Text style={st.muted}>via {d.source} · requested {fmt(d.requested_at)}</Text>
              <View style={st.badges}>
                <Badge text={STATUS_LABEL[d.status] || d.status.toUpperCase()} color={STATUS_COLOR[d.status] || Colors.warning} testID={`cleanup-status-${d.reference}`} />
                <Badge text={ERASURE_LABEL[d.provider_erasure] || d.provider_erasure.toUpperCase()} color={ERASURE_COLOR[d.provider_erasure] || Colors.warning} testID={`provider-erasure-${d.reference}`} />
              </View>
            </View>
            <Ionicons name={open === d.reference ? 'chevron-up' : 'chevron-down'} size={18} color={Colors.textMuted} />
          </TouchableOpacity>
          {open === d.reference && (
            <View style={st.body}>
              <Text style={st.sub}>CLEANUP</Text>
              <Text style={st.line}>App records: {d.cleanup.app} · Website copy: {d.cleanup.website}{d.cleanup.website_acknowledged_at ? ` (${fmt(d.cleanup.website_acknowledged_at)})` : ''}</Text>
              {d.cleanup.note ? <Text style={st.muted}>{d.cleanup.note}</Text> : null}
              {d.cleanup.resumed?.length ? <Text style={st.muted} testID={`resumed-note-${d.reference}`}>Cleanup resumed by an administrator {fmt(d.cleanup.resumed[d.cleanup.resumed.length - 1].at)} ({d.cleanup.resumed.length}×)</Text> : null}
              {d.status === 'local_cleanup_pending' && (
                <View style={st.actions}>
                  <Small testID={`resume-cleanup-${d.reference}`} label="RESUME APP CLEANUP" onPress={async () => {
                    try { await api.post(`/admin/deletion-requests/${d.reference}/cleanup`, {}); load(); }
                    catch (e: any) { showAlert('Not resumed', e?.message || 'Please try again.'); }
                  }} />
                </View>
              )}
              <Text style={st.sub}>PROVIDER ERASURE LEDGER</Text>
              {d.provider_erasure === 'superseded' ? (
                <Text style={st.muted} testID={`superseded-note-${d.reference}`}>The account was re-activated after this legacy request, so no provider erasure is owed for it. A new deletion request will start its own ledger.</Text>
              ) : (Object.keys(d.providers) as ProviderKey[]).map(key => (
                <ProviderCard key={key} reference={d.reference} providerKey={key} entry={d.providers[key]} onChanged={load} />
              ))}
            </View>
          )}
        </View>
      ))}
    </View>
  );
}

function Badge({ text, color, testID }: { text: string; color: string; testID?: string }) {
  return <View style={[st.badge, { backgroundColor: color + '22', borderColor: color + '66' }]} testID={testID}><Text style={[st.badgeText, { color }]}>{text}</Text></View>;
}

function ProviderCard({ reference, providerKey, entry, onChanged }: { reference: string; providerKey: ProviderKey; entry: ProviderEntry; onChanged: () => void }) {
  const [mode, setMode] = useState<'' | 'requested' | 'confirmed' | 'refused' | 'no_procedure'>('');
  const [refText, setRefText] = useState('');
  const [channel, setChannel] = useState('');
  const [outcome, setOutcome] = useState('');
  const [reason, setReason] = useState('');
  const [basis, setBasis] = useState('');
  const [reviewAt, setReviewAt] = useState('');
  const [busy, setBusy] = useState(false);
  const id = `${reference}-${providerKey}`;

  const send = async (body: any) => {
    setBusy(true);
    try { await api.post(`/admin/deletion-requests/${reference}/providers/${providerKey}`, body); setMode(''); setOutcome(''); setReason(''); onChanged(); }
    catch (e: any) { showAlert('Not recorded', e?.message || 'Please check the entry and try again.'); }
    finally { setBusy(false); }
  };
  const submit = () => {
    if (mode === 'requested') return send({ action: 'requested', request_reference: refText.trim(), channel: channel.trim() });
    if (mode === 'confirmed') return send({ action: 'confirmed', outcome: outcome.trim() });
    if (mode === 'no_procedure') return send({ action: 'no_procedure', outcome: outcome.trim() });
    if (mode === 'refused') return send({ action: 'refused', outcome: outcome.trim(), retention_exception: { reason: reason.trim(), basis: basis.trim(), review_at: reviewAt.trim() || null } });
  };
  const na = entry.state === 'not_applicable';
  return (
    <View style={st.provider} testID={`provider-${id}`}>
      <View style={st.providerHead}>
        <Text style={st.providerName}>{entry.provider}</Text>
        <Text style={[st.state, { color: STATE_COLOR[entry.state] }]} testID={`provider-state-${id}`}>{entry.state.replace('_', ' ').toUpperCase()}</Text>
      </View>
      <Text style={st.muted}>{entry.holds}{entry.data_present === 'unknown' ? ' · data presence unknown (historical request) — treated as outstanding' : ''}</Text>
      {entry.requested_at ? <Text style={st.line}>Requested {fmt(entry.requested_at)}{entry.request_reference ? ` · ref ${entry.request_reference}` : ''}{entry.channel ? ` · ${entry.channel}` : ''}</Text> : null}
      {entry.outcome ? <Text style={st.line}>Outcome ({fmt(entry.outcome_at)}): {entry.outcome}</Text> : null}
      {entry.retention_exception ? <Text style={st.line}>Retention exception: {entry.retention_exception.reason}{entry.retention_exception.basis ? ` · basis ${entry.retention_exception.basis}` : ''}{entry.retention_exception.review_at ? ` · review ${entry.retention_exception.review_at}` : ''}</Text> : null}
      {na ? <Text style={st.muted}>No data of this account was transferred to this provider.</Text> : (
        <>
          <Text style={st.procedure}>How to request: {entry.procedure}</Text>
          {!mode ? (
            <View style={st.actions}>
              {(entry.state === 'not_requested' || entry.state === 'no_procedure' || entry.state === 'requested') && <Small testID={`act-requested-${id}`} label={entry.state === 'requested' ? 'UPDATE REQUEST' : 'MARK REQUESTED'} onPress={() => setMode('requested')} />}
              {entry.state === 'requested' && <Small testID={`act-confirmed-${id}`} label="RECORD CONFIRMATION" onPress={() => setMode('confirmed')} />}
              {entry.state === 'requested' && <Small testID={`act-refused-${id}`} label="RECORD REFUSAL + EXCEPTION" onPress={() => setMode('refused')} />}
              {entry.state === 'not_requested' && <Small testID={`act-no-procedure-${id}`} label="NO PROCEDURE EXISTS" onPress={() => setMode('no_procedure')} />}
              {(entry.state === 'confirmed' || entry.state === 'refused' || entry.state === 'no_procedure') && <Small testID={`act-reopen-${id}`} label="REOPEN" onPress={() => send({ action: 'reopen' })} />}
            </View>
          ) : (
            <View style={st.form}>
              {mode === 'requested' && <>
                <TextInput testID={`in-ref-${id}`} style={st.input} placeholder="Ticket / request reference" placeholderTextColor={Colors.textMuted} value={refText} onChangeText={setRefText} />
                <TextInput testID={`in-channel-${id}`} style={st.input} placeholder="Channel (e.g. email support@…)" placeholderTextColor={Colors.textMuted} value={channel} onChangeText={setChannel} />
                <Text style={st.muted}>Request date is recorded as now.</Text>
              </>}
              {(mode === 'confirmed' || mode === 'no_procedure' || mode === 'refused') && (
                <TextInput testID={`in-outcome-${id}`} style={[st.input, { minHeight: 60 }]} multiline placeholder={mode === 'confirmed' ? "Provider's written confirmation (what, when)" : mode === 'no_procedure' ? 'Why no request procedure exists (recorded reason)' : "Provider's written refusal"} placeholderTextColor={Colors.textMuted} value={outcome} onChangeText={setOutcome} />
              )}
              {mode === 'refused' && <>
                <TextInput testID={`in-reason-${id}`} style={st.input} placeholder="Retention exception: reason (min 10 chars)" placeholderTextColor={Colors.textMuted} value={reason} onChangeText={setReason} />
                <TextInput testID={`in-basis-${id}`} style={st.input} placeholder="Basis (contract clause / law)" placeholderTextColor={Colors.textMuted} value={basis} onChangeText={setBasis} />
                <TextInput testID={`in-review-${id}`} style={st.input} placeholder="Review date (YYYY-MM-DD)" placeholderTextColor={Colors.textMuted} value={reviewAt} onChangeText={setReviewAt} />
              </>}
              <View style={st.actions}>
                <Small testID={`submit-${id}`} label={busy ? '…' : 'SAVE'} onPress={submit} primary />
                <Small testID={`cancel-${id}`} label="CANCEL" onPress={() => setMode('')} />
              </View>
            </View>
          )}
        </>
      )}
    </View>
  );
}

function Small({ label, onPress, primary, testID }: { label: string; onPress: () => void; primary?: boolean; testID?: string }) {
  return (
    <TouchableOpacity testID={testID} style={[st.small, primary && st.smallPrimary]} onPress={onPress}>
      <Text style={[st.smallText, primary && { color: '#000' }]}>{label}</Text>
    </TouchableOpacity>
  );
}

const st = StyleSheet.create({
  sectionTitle: { fontSize: FontSize.xs, color: Colors.textSecondary, letterSpacing: 2, fontWeight: '700', marginTop: Spacing.lg, marginBottom: Spacing.sm },
  legend: { fontSize: FontSize.xs, color: Colors.textMuted, lineHeight: 17, marginBottom: Spacing.sm },
  card: { backgroundColor: Colors.card, borderRadius: 12, borderWidth: 1, borderColor: Colors.cardBorder, marginBottom: Spacing.sm },
  head: { flexDirection: 'row', alignItems: 'center', padding: Spacing.md, gap: 8, minHeight: 56 },
  ref: { fontSize: FontSize.sm, fontWeight: '700', color: Colors.text },
  muted: { fontSize: FontSize.xs, color: Colors.textMuted, lineHeight: 17 },
  badges: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 6 },
  badge: { borderRadius: 6, borderWidth: 1, paddingHorizontal: 8, paddingVertical: 3 },
  badgeText: { fontSize: 10, fontWeight: '700', letterSpacing: 0.5 },
  body: { paddingHorizontal: Spacing.md, paddingBottom: Spacing.md, gap: 6 },
  sub: { fontSize: FontSize.xs, color: Colors.textSecondary, letterSpacing: 1.2, fontWeight: '600', marginTop: 4 },
  line: { fontSize: FontSize.xs, color: Colors.textSecondary, lineHeight: 17 },
  provider: { backgroundColor: Colors.surface, borderRadius: 10, padding: Spacing.sm, gap: 4 },
  providerHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 },
  providerName: { fontSize: FontSize.sm, fontWeight: '700', color: Colors.text, flex: 1 },
  state: { fontSize: 10, fontWeight: '700', letterSpacing: 0.5 },
  procedure: { fontSize: FontSize.xs, color: Colors.textSecondary, lineHeight: 16, fontStyle: 'italic' },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 4 },
  small: { borderWidth: 1, borderColor: Colors.gold, borderRadius: 8, paddingHorizontal: 10, minHeight: 36, justifyContent: 'center' },
  smallPrimary: { backgroundColor: Colors.gold },
  smallText: { fontSize: 10, fontWeight: '700', color: Colors.gold, letterSpacing: 0.5 },
  form: { gap: 6, marginTop: 4 },
  input: { backgroundColor: Colors.background, borderRadius: 8, borderWidth: 1, borderColor: Colors.border, color: Colors.text, paddingHorizontal: 10, paddingVertical: 8, fontSize: FontSize.xs },
});
