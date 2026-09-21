import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AppState, Linking, RefreshControl, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { api } from '../../api';
import { useAuth } from '../../context/AuthContext';
import { Colors } from '../../theme';
import { enablePush, permissionState, pushSupported, PermissionState } from '../../push';
import { KeyboardAwareScreen } from '../KeyboardScreen';
import { Button, Busy, dateText, duration, Input, ui } from './Controls';
import RequestDetail from './RequestDetail';
import CompletionReports from './CompletionReports';
import { ADMIN_VIEWS, HEAD_COLORS, VIEW_PRESETS, typeLabel } from './requestHelpers';

/**
 * ONE central query workspace for telecallers, administrators and billing (R11/R14). Every unfinished customer query
 * of every type and age is in All Pending (fresh-first, paginated over the full history); My Pending / My Completed are
 * the personal views. Claim, head, follow-up, notes and Mark Complete live in the detail sheet (server-enforced
 * ownership). Billing is read-only here. The list re-validates every 15 s, on focus and on app resume.
 */
export default function RequestsWorkspace({ onBack, onCRM }: { onBack?: () => void; onCRM?: () => void }) {
  const { user, logout } = useAuth(); const router = useRouter();
  const { request: deepLinkId, section: initialSection } = useLocalSearchParams<{ request?: string; section?: string }>();
  const [data, setData] = useState<any>(null), [error, setError] = useState(''), [loading, setLoading] = useState(false);
  const [view, setView] = useState('all_pending'), [search, setSearch] = useState(''), [type, setType] = useState(''), [head, setHead] = useState('');
  const [page, setPage] = useState(1), [types, setTypes] = useState<string[]>([]), [headLabels, setHeadLabels] = useState<Record<string, string>>({});
  const [staff, setStaff] = useState<any[]>([]), [openId, setOpenId] = useState<string | null>(null);
  const [section, setSection] = useState<'queue' | 'reports'>(initialSection === 'reports' ? 'reports' : 'queue'), [queue, setQueue] = useState<any>(null);
  const [push, setPush] = useState<{ state: PermissionState; canAskAgain: boolean } | null>(null);
  const [unread, setUnread] = useState(0);
  const requestSeq = useRef(0);
  const billing = user?.role === 'billing_executive';
  const admin = user?.role === 'admin';

  const load = useCallback(async () => {
    if (!user || user.role === 'customer') return;
    const seq = ++requestSeq.current;
    setLoading(true);
    if (!billing) api.get('/notifications/inbox?page=1&limit=1').then(r => setUnread(r?.unread || 0)).catch(() => {});
    try {
      const qs = new URLSearchParams({ page: String(page), limit: '25', view, search, request_type: type, head });
      const r = await api.get(`/requests?${qs}`);
      if (seq !== requestSeq.current) return; // a newer filter/page request superseded this response
      setData(r); setError('');
    } catch (e: any) { if (seq === requestSeq.current) setError(`Could not refresh; the list shown may be stale. ${e.message}`); }
    finally { if (seq === requestSeq.current) setLoading(false); }
  }, [user, billing, page, view, search, type, head]);

  useFocusEffect(useCallback(() => { load(); const timer = setInterval(load, 15000); return () => clearInterval(timer); }, [load]));
  useEffect(() => { const s = AppState.addEventListener('change', state => { if (state === 'active') load(); }); return () => s.remove(); }, [load]);
  useEffect(() => {
    api.get('/requests/catalog').then(r => { setTypes(r.types); setHeadLabels(r.head_labels || {}); }).catch((e: any) => setError(e.message));
    api.get('/requests/queue/status').then(setQueue).catch(() => {});
    if (user && user.role !== 'customer') api.get('/requests/staff-options').then(r => setStaff(r.users)).catch(() => {});
    if (pushSupported()) permissionState().then(setPush).catch(() => {});
  }, [user?.id]);
  useEffect(() => { setPage(1); }, [view, search, type, head]);
  useEffect(() => { if (deepLinkId) setOpenId(String(deepLinkId)); }, [deepLinkId]);

  if (!user || user.role === 'customer') return <SafeAreaView style={ui.screen}><Text testID="requests-access-denied" style={ui.error}>Staff sign-in required</Text><Button id="requests-login" title="Sign in" onPress={() => router.replace('/login')} /></SafeAreaView>;

  const views = admin ? ADMIN_VIEWS : VIEW_PRESETS;
  const counts = data?.counts || {};
  const completedView = view.endsWith('completed');

  return <SafeAreaView style={ui.screen} edges={['top', 'bottom']}>
    <View style={ui.header}>{onBack && <Button id="requests-back" title="Back" icon="arrow-back" onPress={onBack} />}<Text testID="requests-title" style={ui.title}>{billing ? 'Central queries' : 'Requests'}</Text></View>
    <KeyboardAwareScreen contentContainerStyle={ui.content} refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor={Colors.gold} />} testID="requests-scroll">
        <Text testID="requests-staff-name" style={ui.muted}>{user.name} · {user.role.replace(/_/g, ' ')}</Text>
        <View style={ui.row}>
          {!billing && <Button id="requests-section-queue" title="Queue" icon="list-outline" active={section === 'queue'} onPress={() => setSection('queue')} />}
          {!billing && <Button id="requests-section-reports" title="Completion reports" icon="bar-chart-outline" active={section === 'reports'} onPress={() => setSection('reports')} />}
          {onCRM && <Button id="requests-open-crm" title="Customer leads" onPress={onCRM} icon="people-outline" />}
          <Button id="requests-refresh" title="Refresh" onPress={load} icon="refresh" />
          {!billing && <Button id="requests-alerts" title={unread ? `Alerts (${unread > 99 ? '99+' : unread})` : 'Alerts'} icon={unread ? 'notifications' : 'notifications-outline'} onPress={() => router.push('/notifications')} />}
          <Button id="requests-logout" title="Sign out" onPress={async () => { await logout(); router.replace('/login'); }} />
        </View>
        {!!error && <Text testID="requests-error" style={ui.error}>{error}</Text>}

        {push && push.state !== 'granted' && !billing && <View style={ui.card} testID="requests-push-card">
          <Text style={ui.label}>NEW-QUERY ALERTS</Text>
          <Text style={ui.muted}>Allow notifications so a new customer query reaches this phone immediately. Receiving an alert never claims the query — the first explicit &quot;Take this query&quot; does.</Text>
          {push.state === 'blocked'
            ? <Button id="requests-push-settings" title="Open Settings" icon="settings-outline" onPress={() => Linking.openSettings()} />
            : <Button id="requests-push-enable" title="Allow notifications" icon="notifications-outline" onPress={async () => { const s = await enablePush(); setPush({ state: s, canAskAgain: s !== 'blocked' }); }} />}
        </View>}

        {section === 'reports' && !billing ? <CompletionReports staff={staff} /> : <>
          {queue && <Text testID="requests-queue-status" style={ui.muted}>Daily release at {queue.release_time} {queue.timezone}: every unfinished query returns to New at the top of this list · next {dateText(queue.next_boundary_utc)}{queue.worker_running ? '' : ' · release worker not running'}</Text>}
          <View style={ui.row}>{views.map(v => <Button key={v.key} id={`request-view-${v.key}`} title={`${v.label}${v.key === 'all_pending' && counts.all_pending != null ? ` (${counts.all_pending})` : v.key === 'my_pending' && counts.my_pending != null ? ` (${counts.my_pending})` : ''}`} active={view === v.key} onPress={() => setView(v.key)} />)}</View>
          <Input id="request-search" label="Search name, phone, shop, place, product or note" value={search} onChange={setSearch} />
          <View style={ui.row}><Button id="request-type-all" title="All types" active={!type} onPress={() => setType('')} />{types.map(t => <Button key={t} id={`request-type-${t}`} title={`${typeLabel(t)}${data?.open_counts_by_type?.[t] ? ` (${data.open_counts_by_type[t]})` : ''}`} active={t === type} onPress={() => setType(t === type ? '' : t)} />)}</View>
          {!completedView && <View style={ui.row}><Button id="request-head-all" title="All heads" active={!head} onPress={() => setHead('')} />{Object.keys(headLabels).map(h => <Button key={h} id={`request-head-filter-${h}`} title={`${headLabels[h]}${data?.open_counts_by_head?.[h] ? ` (${data.open_counts_by_head[h]})` : ''}`} active={h === head} onPress={() => setHead(h === head ? '' : h)} />)}</View>}

          <Text testID="request-total" style={ui.label}>{data?.total ?? '—'} {completedView ? 'COMPLETED' : 'PENDING'} QUERIES · PAGE {page} / {Math.max(data?.pages || 1, 1)}</Text>
          {loading && !data && <Busy />}
          {data?.requests.map((r: any) => {
            const mine = r.assignee_id && r.assignee_id === user.id;
            const open = !['resolved', 'cancelled'].includes(r.status);
            return <TouchableOpacity testID={`request-row-${r.id}`} key={r.id} style={[ui.card, mine && { borderColor: Colors.gold }]} onPress={() => setOpenId(r.id)} accessibilityRole="button" accessibilityLabel={`Open query from ${r.customer_name || 'customer'}`}>
              <View style={[ui.row, { justifyContent: 'space-between' }]}>
                <Text testID={`request-customer-${r.id}`} style={[ui.text, { flex: 1 }]}>{r.customer_name || r.user_name || 'Customer'}</Text>
                <View style={[badge, { borderColor: open ? (HEAD_COLORS[r.head] || Colors.border) : Colors.success }]} testID={`request-head-${r.id}`}><Text style={ui.muted}>{open ? (r.head_label || r.head) : 'Completed'}</Text></View>
              </View>
              <Text style={ui.muted}>{r.customer_shop_name || 'Shop not recorded'} · {r.customer_location || r.user_city || 'Place not recorded'}</Text>
              <Text style={ui.label}>{typeLabel(r.request_type)}{r.item_count ? ` · ${r.item_count} item${r.item_count === 1 ? '' : 's'}` : ''}</Text>
              <Text testID={`request-age-${r.id}`} style={ui.muted}>Created {dateText(r.created_at)}{r.reset_count ? ` · released ×${r.reset_count}` : ''}{'\n'}{open ? `Waiting ${duration(r.pending_seconds)}` : `Completed ${dateText(r.resolved_at)} by ${r.resolver_name || 'staff'}`}</Text>
              <View style={[ui.row, { justifyContent: 'space-between' }]}>
                <Text testID={`request-attribution-${r.id}`} style={[ui.muted, mine && ui.success]}>{open ? (r.assignee_id ? (mine ? 'Taken by you' : `Taken by ${r.assignee_name || 'a telecaller'}`) : 'Unclaimed') : `Outcome: ${(r.outcome || 'other').replace(/_/g, ' ')}`}</Text>
                {!!r.follow_up_at && <Text style={ui.muted}><Ionicons name="alarm-outline" size={12} color={Colors.warning} /> {dateText(r.follow_up_at)}</Text>}
              </View>
            </TouchableOpacity>;
          })}
          {data?.total === 0 && <Text testID="requests-empty" style={ui.muted}>{view === 'my_pending' ? 'You have no pending queries. Take one from All Pending.' : view === 'my_completed' ? 'No completed queries yet.' : 'No queries match these filters.'}</Text>}
          <View style={ui.row}><Button id="requests-prev" title="Previous" disabled={page <= 1} onPress={() => setPage(page - 1)} /><Text testID="requests-page" style={ui.text}>Page {page} / {Math.max(data?.pages || 1, 1)}</Text><Button id="requests-next" title="Next" disabled={!data || page >= data.pages} onPress={() => setPage(page + 1)} /></View>
          <Text testID="requests-last-updated" style={ui.muted}>Last refreshed {dateText(data?.server_time)} · automatic refresh every 15 seconds</Text>
        </>}
    </KeyboardAwareScreen>
    <RequestDetail requestId={openId} onClose={() => setOpenId(null)} onChanged={load} staff={staff}
      onOpenCustomer={admin ? (cid) => { setOpenId(null); router.push({ pathname: '/customer-directory', params: { customer: cid } } as any); } : undefined} />
  </SafeAreaView>;
}

const badge = { borderWidth: 1, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 4 } as const;
