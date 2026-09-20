import React, { useCallback, useEffect, useState } from 'react';
import { Text, View } from 'react-native';
import { api } from '../../api';
import { useAuth } from '../../context/AuthContext';
import { Button, Busy, dateText, Input, ui } from './Controls';
import { istDate, typeLabel } from './requestHelpers';

/**
 * Completion reports (R13-A): distinct completed queries per completing telecaller for an Asia/Kolkata day or custom
 * range (both dates inclusive). Counts come from the immutable completion ledger — a retried Mark Complete adds no
 * record, a reopened completion is excluded, a later re-completion is a new record. Telecallers see their own numbers.
 */
export default function CompletionReports({ staff }: { staff: any[] }) {
  const { user } = useAuth();
  const [start, setStart] = useState(istDate()), [end, setEnd] = useState(istDate()), [telecaller, setTelecaller] = useState('');
  const [report, setReport] = useState<any>(null), [error, setError] = useState(''), [loading, setLoading] = useState(false), [page, setPage] = useState(1);
  const admin = user?.role === 'admin';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams({ start, end, telecaller, page: String(page), limit: '50' });
      setReport(await api.get(`/requests/reports/completions?${qs}`)); setError('');
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  }, [start, end, telecaller, page]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { setPage(1); }, [start, end, telecaller]);

  const shift = (days: number) => { const d = new Date(`${start}T00:00:00+05:30`); d.setDate(d.getDate() + days); const v = istDate(d); setStart(v); setEnd(v); };

  return <View style={{ gap: 16 }} testID="completion-reports">
    <Text style={ui.label}>COMPLETED QUERIES · ASIA/KOLKATA · START AND END DATES INCLUSIVE</Text>
    <View style={ui.row}>
      <Button id="report-prev-day" title="◀ Day" onPress={() => shift(-1)} />
      <Button id="report-today" title="Today" onPress={() => { setStart(istDate()); setEnd(istDate()); }} />
      <Button id="report-next-day" title="Day ▶" onPress={() => shift(1)} />
      <Button id="report-week" title="Last 7 days" onPress={() => { const d = new Date(); d.setDate(d.getDate() - 6); setStart(istDate(d)); setEnd(istDate()); }} />
      <Button id="report-month" title="Last 30 days" onPress={() => { const d = new Date(); d.setDate(d.getDate() - 29); setStart(istDate(d)); setEnd(istDate()); }} />
    </View>
    <Input id="report-start" label="From (YYYY-MM-DD)" value={start} onChange={setStart} />
    <Input id="report-end" label="To (YYYY-MM-DD)" value={end} onChange={setEnd} />
    {admin && <View style={ui.row}><Button id="report-telecaller-all" title="All telecallers" active={!telecaller} onPress={() => setTelecaller('')} />{staff.filter(s => s.role === 'telecaller' || s.role === 'admin').map(s => <Button key={s.id} id={`report-telecaller-${s.id}`} title={s.name || 'Unnamed'} active={telecaller === s.id} onPress={() => setTelecaller(s.id)} />)}</View>}
    {!!error && <Text testID="report-error" style={ui.error}>{error}</Text>}
    {loading && !report && <Busy />}
    {report && <>
      <Text testID="report-total" style={ui.text}>{report.total_completed} completed {report.total_completed === 1 ? 'query' : 'queries'} in {report.calendar_days} calendar day{report.calendar_days === 1 ? '' : 's'}</Text>
      {report.telecallers.length === 0 && <Text testID="report-empty" style={ui.muted}>No completions in this interval.</Text>}
      {report.telecallers.map((r: any) => <View key={r.id} style={ui.card} testID={`report-row-${r.id}`}>
        <Text style={ui.text}>{r.name} · {r.completed} completed</Text>
        <Text style={ui.muted}>{r.role.replace(/_/g, ' ')} · account {r.account_status}{r.records !== r.completed ? ` · ${r.records} ledger records (re-completions counted once per query)` : ''}</Text>
      </View>)}
      <Text style={ui.label}>RECORDS · {report.total_records}</Text>
      {report.records.map((rec: any) => <View key={rec.id} style={ui.card} testID={`report-record-${rec.id}`}>
        <Text style={ui.text}>{rec.customer_name || 'Customer'} · {typeLabel(rec.request_type)}</Text>
        <Text style={ui.muted}>{dateText(rec.completed_at)} · by {rec.actor_name} · outcome {String(rec.outcome || 'other').replace(/_/g, ' ')}{rec.superseded_at ? ' · superseded by reopen' : ''}</Text>
      </View>)}
      <View style={ui.row}><Button id="report-prev" title="Previous" disabled={page <= 1} onPress={() => setPage(page - 1)} /><Text style={ui.text}>Page {page} / {Math.max(report.pages || 1, 1)}</Text><Button id="report-next" title="Next" disabled={page >= (report.pages || 1)} onPress={() => setPage(page + 1)} /></View>
      <Text style={ui.muted}>{report.semantics?.completed}. {report.semantics?.retry}. {report.semantics?.reopen}. Cancelled queries are never counted.</Text>
    </>}
  </View>;
}
