import React, { useCallback, useEffect, useState } from 'react';
import { View, Text, StyleSheet, ActivityIndicator, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { api } from '../../api';
import { Colors, Spacing, FontSize } from '../../theme';
import { showAlert } from '../../utils/alert';

interface Report {
  pending: boolean;
  sms_log_retention: { retention_days: number; ttl_index: boolean; rows_without_expiry: number };
  deletion_ledger: { legacy_rows: number; rows_without_providers: number; rows_with_old_status: number; outbox_events_to_correct: number };
}

/**
 * Explicit admin maintenance (nothing runs at startup any more): apply the bounded SMS-log retention and converge
 * deletion requests written by older builds. Shows only what is pending; disappears when everything is applied.
 */
export default function MaintenanceCard({ onApplied }: { onApplied?: () => void }) {
  const [report, setReport] = useState<Report | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setReport(await api.get('/admin/maintenance')); } catch { setReport(null); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (!report || !report.pending) return null;
  const r = report.sms_log_retention;
  const d = report.deletion_ledger;
  const ledgerPending = d.legacy_rows + d.rows_without_providers + d.rows_with_old_status + d.outbox_events_to_correct;
  const retentionPending = !r.ttl_index || r.rows_without_expiry > 0;

  const run = async (key: string, path: string, done: string) => {
    setBusy(key);
    try { await api.post(path, {}); showAlert('Applied', done); await load(); onApplied?.(); }
    catch (e: any) { showAlert('Not applied', e?.message || 'Please try again.'); }
    finally { setBusy(null); }
  };

  return (
    <View style={st.card} testID="maintenance-card">
      <View style={st.head}>
        <Ionicons name="construct-outline" size={18} color={Colors.warning} />
        <Text style={st.title}>MAINTENANCE PENDING</Text>
      </View>
      <Text style={st.body}>One-off migrations run only when an administrator applies them here — deployments never change records on their own.</Text>
      {ledgerPending > 0 && (
        <View style={st.row}>
          <Text style={st.item} testID="maintenance-ledger-text">
            Deletion ledger: {d.legacy_rows} older row(s){d.rows_without_providers ? `, ${d.rows_without_providers} without provider ledger` : ''}{d.outbox_events_to_correct ? `, ${d.outbox_events_to_correct} website event(s) to correct` : ''}
          </Text>
          <TouchableOpacity testID="maintenance-reconcile" style={st.btn} disabled={!!busy}
            onPress={() => run('ledger', '/admin/maintenance/deletions/reconcile', 'Older deletion requests converged. Interrupted cleanups now appear below for you to resume.')}>
            {busy === 'ledger' ? <ActivityIndicator color="#000" size="small" /> : <Text style={st.btnText}>RECONCILE OLDER ROWS</Text>}
          </TouchableOpacity>
        </View>
      )}
      {retentionPending && (
        <View style={st.row}>
          <Text style={st.item} testID="maintenance-retention-text">
            SMS delivery logs: {r.ttl_index ? '' : `${r.retention_days}-day retention not yet enforced`}{!r.ttl_index && r.rows_without_expiry ? ', ' : ''}{r.rows_without_expiry ? `${r.rows_without_expiry} row(s) without expiry` : ''}
          </Text>
          <TouchableOpacity testID="maintenance-retention" style={st.btn} disabled={!!busy}
            onPress={() => run('retention', '/admin/maintenance/retention', `SMS delivery logs now expire after ${r.retention_days} days.`)}>
            {busy === 'retention' ? <ActivityIndicator color="#000" size="small" /> : <Text style={st.btnText}>APPLY {r.retention_days}-DAY RETENTION</Text>}
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

const st = StyleSheet.create({
  card: { backgroundColor: Colors.card, borderRadius: 14, borderWidth: 1, borderColor: Colors.warning, padding: Spacing.md, marginBottom: Spacing.md },
  head: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  title: { fontSize: FontSize.xs, fontWeight: '700', color: Colors.warning, letterSpacing: 1.5 },
  body: { fontSize: FontSize.xs, color: Colors.textMuted, marginTop: 6, lineHeight: 17 },
  row: { marginTop: Spacing.md, gap: 8 },
  item: { fontSize: FontSize.sm, color: Colors.text, lineHeight: 19 },
  btn: { alignSelf: 'flex-start', backgroundColor: Colors.gold, borderRadius: 8, paddingHorizontal: 14, paddingVertical: 10, minHeight: 40, justifyContent: 'center' },
  btnText: { fontSize: FontSize.xs, fontWeight: '700', color: '#000', letterSpacing: 1 },
});
