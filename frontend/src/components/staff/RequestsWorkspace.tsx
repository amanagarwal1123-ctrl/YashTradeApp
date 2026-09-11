import React, { useCallback, useEffect, useState } from 'react';
import { AppState, KeyboardAvoidingView, Modal, Platform, RefreshControl, ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';
import { api } from '../../api';
import { useAuth } from '../../context/AuthContext';
import { Button, Busy, dateText, duration, Input, ui } from './Controls';

const statuses = ['open', 'pending', 'in_progress', 'contacted', 'no_response', 'resolved', 'cancelled', 'all'];
const today = () => new Date(Date.now()+330*60000).toISOString().slice(0,10);

export default function RequestsWorkspace({ onBack, onCRM }: { onBack?: () => void; onCRM?: () => void }) {
  const { user, logout } = useAuth(); const router = useRouter();
  const [data, setData] = useState<any>(null), [metrics, setMetrics] = useState<any>(null);
  const [error, setError] = useState(''), [loading, setLoading] = useState(false);
  const [search, setSearch] = useState(''), [status, setStatus] = useState('open'), [view, setView] = useState('all');
  const [page, setPage] = useState(1), [type, setType] = useState(''), [types, setTypes] = useState<string[]>([]);
  const [advanced, setAdvanced] = useState(false), [sort, setSort] = useState('oldest');
  const [start, setStart] = useState(today()), [end, setEnd] = useState(today());
  const [createdFrom, setCreatedFrom] = useState(''), [createdTo, setCreatedTo] = useState('');
  const [minAge, setMinAge] = useState(''), [maxAge, setMaxAge] = useState('');
  const [assignee, setAssignee] = useState(''), [resolver, setResolver] = useState('');
  const [periodResolver, setPeriodResolver] = useState('');
  const [detail, setDetail] = useState<any>(null), [note, setNote] = useState(''), [busy, setBusy] = useState(false);
  const [staff, setStaff] = useState<any[]>([]);
  const billing = user?.role === 'billing_executive';

  const load = useCallback(async () => {
    if (!user || user.role === 'customer') return;
    setLoading(true);
    try {
      const qs = new URLSearchParams({ page: String(page), limit: '25', search, status, view, sort, request_type: type, assignee, resolver, created_from: createdFrom, created_to: createdTo });
      if (minAge) qs.set('min_age_minutes', minAge); if (maxAge) qs.set('max_age_minutes', maxAge);
      if(periodResolver) { qs.set('period_resolver',periodResolver); qs.set('period_start',start); qs.set('period_end',end); }
      const [r, m] = await Promise.all([api.get(`/requests?${qs}`), billing ? null : api.get(`/requests/metrics/summary?${new URLSearchParams({ start, end, search, request_type: type })}`)]);
      setData(r); setMetrics(m); setError('');
    } catch (e: any) { setError(`Could not refresh. Displayed data may be stale. ${e.message}`); }
    finally { setLoading(false); }
  }, [user, page, search, status, view, sort, type, assignee, resolver, createdFrom, createdTo, minAge, maxAge, start, end, billing, periodResolver]);

  useFocusEffect(useCallback(() => { load(); const timer = setInterval(load, 15000); return () => clearInterval(timer); }, [load]));
  useEffect(() => { const s = AppState.addEventListener('change', state => { if (state === 'active') load(); }); return () => s.remove(); }, [load]);
  useEffect(() => { api.get('/requests/catalog').then(r => setTypes(r.types)).catch((e: any) => setError(e.message)); }, []);
  useEffect(() => { setPage(1); }, [search, status, view, type, assignee, resolver, createdFrom, createdTo, minAge, maxAge]);
  const open = async (id: string) => {
    setBusy(true); setNote('');
    try { setDetail(await api.get(`/requests/${id}/history`)); if (user?.role === 'admin') setStaff((await api.get('/integrations/staff?status=active')).users); }
    catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };
  const mutate = async (body: any) => {
    setBusy(true);
    try { await api.patch(`/requests/${detail.request.id}`, { ...body, version: detail.request.version, idempotency_key: `${Date.now()}-${Math.random()}` }); await open(detail.request.id); await load(); }
    catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };
  const request = detail?.request;
  const own = user?.role === 'admin' || request?.assignee_id === user?.id;
  if (!user || user.role === 'customer') return <SafeAreaView style={ui.screen}><Text testID="requests-access-denied" style={ui.error}>Staff sign-in required</Text><Button id="requests-login" title="Sign in" onPress={() => router.replace('/login')}/></SafeAreaView>;

  return <SafeAreaView style={ui.screen} edges={['top', 'bottom']}>
    <View style={ui.header}>{onBack && <Button id="requests-back" title="Back" onPress={onBack}/>}<Text testID="requests-title" style={ui.title}>{billing ? 'Pending queries' : 'Requests'}</Text></View>
    <KeyboardAvoidingView style={ui.screen} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={ui.content} refreshControl={<RefreshControl refreshing={loading} onRefresh={load}/>}>
        <Text testID="requests-staff-name" style={ui.muted}>{user.name} · {user.role.replace('_', ' ')}</Text>
        <View style={ui.row}>{onCRM && <Button id="requests-open-crm" title="Customer leads" onPress={onCRM} icon="people-outline"/>}<Button id="requests-refresh" title="Refresh" onPress={load} icon="refresh"/><Button id="requests-logout" title="Sign out" onPress={async () => { await logout(); router.replace('/login'); }}/></View>
        {!!error && <Text testID="requests-error" style={ui.error}>{error}</Text>}
        {metrics && <View style={ui.card}>
          <Text testID="metrics-heading" style={ui.label}>REPORTING · ASIA/KOLKATA</Text>
          <Input id="metrics-start" label="From YYYY-MM-DD" value={start} onChange={setStart}/><Input id="metrics-end" label="To YYYY-MM-DD" value={end} onChange={setEnd}/>
          <Button id="metrics-today" title="Today" onPress={() => { setStart(today()); setEnd(today()); }}/>
          <Text testID="received-cohort" style={ui.text}>Received {metrics.received_cohort.received} · Open {metrics.received_cohort.open} · Completed {metrics.received_cohort.resolved} · Cancelled {metrics.received_cohort.cancelled}</Text>
          <Text testID="period-throughput" style={ui.text}>Period throughput: {metrics.period_throughput} distinct resolved queries</Text>
          <Text testID="metrics-explanation" style={ui.muted}>Received cohort uses creation dates. Throughput uses resolution dates, including older queries. Status chips affect the list only.</Text>
          {metrics.telecallers.map((r: any) => <View testID={`performance-${r.id}`} key={r.id} style={ui.card}>
            <Text style={[ui.text, r.top_performer && ui.success]}>{r.name}{r.top_performer ? ' · Top resolver' : ''}</Text>
            <Text testID={`performance-count-${r.id}`} style={ui.muted}>Resolved {r.resolved} / {r.team_resolved} team resolutions{ '\n' }Assigned cohort: {r.resolved_from_assigned} resolved / {r.assigned_workload} assigned · {r.open_workload} open{ '\n' }Active days {r.active_days} / {r.calendar_days} calendar days</Text>
            <Button id={`performance-drilldown-${r.id}`} title="Show handled queries" onPress={() => { setPeriodResolver(r.id); setResolver(''); setStatus('all'); setPage(1); }}/>
            {Object.entries(r.daily).map(([day, d]: any) => <Text key={day} testID={`daily-${r.id}-${day}`} style={ui.muted}>{day}: {d.resolved} completed · {d.work_events} work events</Text>)}
          </View>)}
        </View>}
        <Input id="request-search" label="Search name, phone, shop or place" value={search} onChange={setSearch}/>
        {!!periodResolver && <Button id="clear-performance-drilldown" title="Clear period-resolution drilldown" onPress={()=>setPeriodResolver('')}/>}
        <View style={ui.row}>{['all', 'mine', 'unassigned'].map(v => <Button key={v} id={`request-view-${v}`} title={v} active={view === v} onPress={() => setView(v)}/>)}</View>
        <View style={ui.row}>{statuses.map(s => <Button key={s} id={`request-status-${s}`} title={s === 'resolved' ? 'Completed' : s.replace('_',' ')} active={s === status} onPress={() => setStatus(s)}/>)}</View>
        <Button id="request-filters-toggle" title={advanced ? 'Hide filters' : 'Type, dates, age & sorting'} onPress={() => setAdvanced(!advanced)} icon="options-outline"/>
        {advanced && <View style={ui.card}>
          <View style={ui.row}><Button id="request-type-all" title="All types" active={!type} onPress={() => setType('')}/>{types.map(t => <Button key={t} id={`request-type-${t}`} title={`${t.replace(/_/g,' ')} (${data?.open_counts_by_type?.[t] || 0})`} active={t === type} onPress={() => setType(t)}/>)}</View>
          <Input id="request-created-from" label="Created from YYYY-MM-DD (optional)" value={createdFrom} onChange={setCreatedFrom}/><Input id="request-created-to" label="Created to YYYY-MM-DD (optional)" value={createdTo} onChange={setCreatedTo}/>
          <Input id="request-min-age" label="Minimum pending minutes" value={minAge} onChange={setMinAge}/><Input id="request-max-age" label="Maximum pending minutes" value={maxAge} onChange={setMaxAge}/>
          <Input id="request-assignee" label="Assignee ID (optional)" value={assignee} onChange={setAssignee}/><Input id="request-resolver" label="Resolver ID (optional)" value={resolver} onChange={setResolver}/>
          <View style={ui.row}>{['oldest','newest','longest_wait'].map(s => <Button id={`request-sort-${s}`} key={s} title={s.replace('_',' ')} active={s === sort} onPress={() => setSort(s)}/>)}</View>
        </View>}
        <Text testID="request-total" style={ui.label}>{data?.total ?? '—'} MATCHING QUERIES</Text>
        {data?.requests.map((r: any) => <View testID={`request-row-${r.id}`} key={r.id} style={ui.card}>
          <Text testID={`request-customer-${r.id}`} style={ui.text}>{r.customer_name || r.user_name || 'Customer'} · {r.customer_phone || r.user_phone}</Text>
          <Text style={ui.muted}>{r.customer_shop_name || 'Shop not recorded'} · {r.customer_location || r.user_city}</Text>
          <Text style={ui.label}>{r.request_type.replace(/_/g,' ')} · {r.status === 'resolved' ? 'Completed' : r.status}</Text>
          <Text testID={`request-age-${r.id}`} style={ui.muted}>Created {dateText(r.created_at)}{ '\n' }{r.status === 'resolved' ? `Handling duration ${duration(r.handling_seconds)}` : r.status === 'cancelled' ? 'Cancelled' : `Waiting ${duration(r.pending_seconds)} · Original age ${duration(r.age_seconds)}`}</Text>
          <Text testID={`request-attribution-${r.id}`} style={ui.muted}>Assigned: {r.assignee_name || 'Unassigned'} · Resolved by: {r.resolver_name || 'Not recorded'}</Text>
          <Button id={`request-open-${r.id}`} title="Details & history" onPress={() => open(r.id)}/>
        </View>)}
        {data?.total === 0 && <Text testID="requests-empty" style={ui.muted}>No queries match these filters.</Text>}
        <View style={ui.row}><Button id="requests-prev" title="Previous" disabled={page <= 1} onPress={() => setPage(page-1)}/><Text testID="requests-page" style={ui.text}>Page {page} / {Math.max(data?.pages || 1, 1)}</Text><Button id="requests-next" title="Next" disabled={!data || page >= data.pages} onPress={() => setPage(page+1)}/></View>
        <Text testID="requests-last-updated" style={ui.muted}>Last refreshed {dateText(data?.server_time)} · Automatic refresh every 15 seconds</Text>
      </ScrollView>
    </KeyboardAvoidingView>
    <Modal visible={!!detail} animationType="slide" onRequestClose={() => setDetail(null)}>
      <SafeAreaView style={ui.screen}><KeyboardAvoidingView style={ui.screen} behavior={Platform.OS === 'ios' ? 'padding' : undefined}><ScrollView contentContainerStyle={ui.content} keyboardShouldPersistTaps="handled">
        <Button id="request-detail-close" title="Close details" onPress={() => setDetail(null)}/>
        {request && <>
          <Text testID="request-detail-title" style={ui.title}>{request.user_name || 'Query details'}</Text><Text style={ui.text}>{request.notes || 'No customer note'}</Text>
          {!!error && <Text testID="request-detail-error" style={ui.error}>{error}</Text>}{busy && <Busy/>}
          {!billing && !request.assignee_id && !['resolved','cancelled'].includes(request.status) && <Button id="request-claim" title="Claim this query" disabled={busy} onPress={() => mutate({ action: 'claim' })}/>}
          {!billing && own && <View style={ui.card}>
            <Input id="request-note" label="Internal note" value={note} onChange={setNote} multiline/>
            <Button id="request-save-note" title="Save note" disabled={busy || !note.trim()} onPress={() => mutate({ notes: note })}/>
            <View style={ui.row}>{(['resolved','cancelled'].includes(request.status) ? ['pending'] : ['in_progress','contacted','no_response','resolved','cancelled']).map(s => <Button key={s} id={`request-transition-${s}`} title={s === 'pending' ? 'Reopen' : s === 'resolved' ? 'Complete' : s.replace('_',' ')} disabled={busy} onPress={() => mutate({ status: s, action: s === 'pending' ? 'reopen' : 'update' })}/>)}</View>
          </View>}
          {user.role === 'admin' && <View style={ui.card}><Text style={ui.label}>EXPLICIT REASSIGNMENT</Text>{staff.filter(s => ['admin','telecaller'].includes(s.role)).map(s => <Button id={`request-assign-${s.id}`} key={s.id} title={`Assign to ${s.name}`} disabled={busy} onPress={() => mutate({ action: 'assign', assigned_to: s.id })}/>)}</View>}
          <Text testID="request-history-heading" style={ui.label}>APPEND-ONLY HISTORY</Text>
          {detail.history.map((e: any) => <View testID={`request-event-${e.id}`} key={e.id} style={ui.card}><Text style={ui.text}>{e.type.replace(/_/g,' ')} · {e.status || ''}</Text><Text style={ui.muted}>{e.actor_name || 'Legacy actor unknown'} · {dateText(e.timestamp)}</Text>{!!e.notes && <Text style={ui.text}>{e.notes}</Text>}</View>)}
        </>}
      </ScrollView></KeyboardAvoidingView></SafeAreaView>
    </Modal>
  </SafeAreaView>;
}