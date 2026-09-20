import React, { useCallback, useEffect, useState } from 'react';
import { Platform, ScrollView, Text, View } from 'react-native';
import { KeyboardAvoidingView } from 'react-native-keyboard-controller';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Image } from 'expo-image';
import { api, API_BASE } from '../src/api';
import { useAuth } from '../src/context/AuthContext';
import { useSafeBack } from '../src/navigation';
import { Colors } from '../src/theme';
import { confirmAlert } from '../src/utils/alert';
import { IMAGE_PLACEHOLDER } from '../src/imagePlaceholder';
import { Button, Busy, dateText, Input, ui } from '../src/components/staff/Controls';

const DESTINATIONS = [
  { key: '/notifications', label: 'Notification history' }, { key: '/(tabs)', label: 'Home' }, { key: '/rate-list', label: 'Rate list' },
  { key: '/schemes', label: 'Schemes' }, { key: '/brands', label: 'Brands' }, { key: '/exhibition', label: 'Exhibition' },
  { key: '/showroom', label: 'Showroom' }, { key: '/rewards', label: 'Rewards' }, { key: '/knowledge', label: 'Silver guide' },
];
const EMPTY_AUDIENCE = { target: 'customers', customer_ids: [] as string[], cities: [] as string[], customer_types: [] as string[], assigned_telecaller: '', lead_statuses: [] as string[], match: 'all' };

/**
 * Admin-only notification composer (R09-A): title, body, optional image (public https URL or a listed product photo),
 * safe in-app destination, explicit audience with server-resolved counts (users and devices counted separately),
 * preview, test-send to the administrator's own devices, drafts, a send confirmation that must match the inspected
 * count, and sent/failed history from the outbox. Recipient resolution and permissions live on the server.
 */
export default function AdminNotifications() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const back = useSafeBack(user?.role);
  const [tab, setTab] = useState<'compose' | 'history'>('compose');
  const [title, setTitle] = useState(''), [body, setBody] = useState(''), [imageUrl, setImageUrl] = useState(''), [destination, setDestination] = useState('/notifications');
  const [productId, setProductId] = useState('');
  const [audience, setAudience] = useState<any>(EMPTY_AUDIENCE);
  const [filters, setFilters] = useState<any>(null), [count, setCount] = useState<any>(null);
  const [customerQuery, setCustomerQuery] = useState(''), [customerHits, setCustomerHits] = useState<any[]>([]), [selected, setSelected] = useState<any[]>([]);
  const [draft, setDraft] = useState<any>(null), [campaigns, setCampaigns] = useState<any>(null), [detail, setDetail] = useState<any>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [info, setInfo] = useState('');
  const [products, setProducts] = useState<any[]>([]);
  const admin = user?.role === 'admin';

  useEffect(() => { if (!loading && !admin) router.replace('/panel'); }, [loading, admin]);
  useEffect(() => {
    if (!admin) return;
    api.get('/admin/notifications/filters').then(setFilters).catch((e: any) => setError(e.message));
    api.get('/products?limit=24').then(r => setProducts(r.products || [])).catch(() => {});
  }, [admin]);
  const loadHistory = useCallback(() => { if (admin) api.get('/admin/notifications/campaigns?limit=30').then(setCampaigns).catch((e: any) => setError(e.message)); }, [admin]);
  useEffect(() => { if (tab === 'history') loadHistory(); }, [tab, loadHistory]);

  useEffect(() => {
    if (!admin) return;
    const timer = setTimeout(() => {
      if (customerQuery.trim().length < 2) { setCustomerHits([]); return; }
      api.get(`/customers/search?q=${encodeURIComponent(customerQuery.trim())}`).then(r => setCustomerHits(r.customers || [])).catch(() => setCustomerHits([]));
    }, 300);
    return () => clearTimeout(timer);
  }, [customerQuery, admin]);

  const spec = () => ({ ...audience, customer_ids: audience.target === 'selected' ? selected.map(s => s.id) : [] });
  const toggle = (key: string, value: string) => setAudience((a: any) => ({ ...a, [key]: a[key].includes(value) ? a[key].filter((v: string) => v !== value) : [...a[key], value] }));

  const inspect = async () => {
    setBusy(true); setError(''); setCount(null);
    try { setCount(await api.post('/admin/notifications/audience', spec())); } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };
  const payload = () => ({ title: title.trim(), body: body.trim(), image_url: imageUrl.trim(), destination: productId ? `/product/${productId}` : destination, audience: spec() });
  const saveDraft = async () => {
    setBusy(true); setError('');
    try {
      const saved = draft ? await api.put(`/admin/notifications/campaigns/${draft.id}`, payload()) : await api.post('/admin/notifications/campaigns', payload());
      setDraft(saved); setInfo(`Draft saved (${saved.id})`);
    } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };
  const testSend = async () => {
    setBusy(true); setError('');
    try {
      const saved = draft ? await api.put(`/admin/notifications/campaigns/${draft.id}`, payload()) : await api.post('/admin/notifications/campaigns', payload());
      setDraft(saved);
      const r = await api.post(`/admin/notifications/campaigns/${saved.id}/test`);
      setInfo(`Test queued to your ${r.devices} device${r.devices === 1 ? '' : 's'} (provider acceptance is recorded per batch, not proof of display)`);
    } catch (e: any) { setError(e.code === 'NO_TEST_DEVICE' ? 'Allow notifications on this phone first (Notifications screen) so a test can reach you.' : e.message); }
    finally { setBusy(false); }
  };
  const send = async () => {
    if (!count) { setError('Inspect the audience first'); return; }
    setBusy(true); setError('');
    try {
      const saved = draft ? await api.put(`/admin/notifications/campaigns/${draft.id}`, payload()) : await api.post('/admin/notifications/campaigns', payload());
      setDraft(saved);
      const r = await api.post(`/admin/notifications/campaigns/${saved.id}/send`, { confirm_users: count.users });
      setInfo(`Queued: ${r.users} users · ${r.devices} devices · ${r.batches} batches. ${r.note}`);
      setDraft(null); setTitle(''); setBody(''); setImageUrl(''); setProductId(''); setCount(null); setTab('history');
    } catch (e: any) { setError(e.code === 'AUDIENCE_CHANGED' ? `${e.message} — inspect again before sending.` : e.message); setCount(null); }
    finally { setBusy(false); }
  };

  if (loading || !admin) return <SafeAreaView style={ui.screen}><Busy /></SafeAreaView>;
  const previewImage = imageUrl.trim();

  return <SafeAreaView style={ui.screen} edges={['top', 'bottom']}>
    <View style={ui.header}><Button id="admin-notifications-back" title="Back" icon="arrow-back" onPress={back} /><Text testID="admin-notifications-title" style={ui.title}>Notifications</Text></View>
    <View style={[ui.row, { paddingHorizontal: 20 }]}>
      <Button id="admin-notifications-tab-compose" title="Compose" icon="create-outline" active={tab === 'compose'} onPress={() => setTab('compose')} />
      <Button id="admin-notifications-tab-history" title="Sent / failed history" icon="time-outline" active={tab === 'history'} onPress={() => setTab('history')} />
    </View>
    <KeyboardAvoidingView style={ui.screen} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
      <ScrollView contentContainerStyle={ui.content} keyboardShouldPersistTaps="handled">
        {!!error && <Text testID="admin-notifications-error" style={ui.error}>{error}</Text>}
        {!!info && <Text testID="admin-notifications-info" style={[ui.muted, ui.success]}>{info}</Text>}
        {tab === 'compose' && <>
          <View style={ui.card}>
            <Text style={ui.label}>MESSAGE</Text>
            <Input id="notif-title" label={`Title (${title.length}/80)`} value={title} onChange={v => setTitle(v.slice(0, 80))} />
            <Input id="notif-body" label={`Text (${body.length}/240) — lock-screen text: avoid customer personal data`} value={body} onChange={v => setBody(v.slice(0, 240))} multiline />
            <Input id="notif-image" label="Image (public https URL, optional)" value={imageUrl} onChange={setImageUrl} />
            {products.length > 0 && <>
              <Text style={ui.muted}>…or pick a listed product photo (public catalogue image)</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false}><View style={ui.row}>
                {products.filter(p => p.thumbnail_path || p.storage_path).map(p => {
                  const url = `${API_BASE}/files/${p.storage_path || p.thumbnail_path}`;
                  return <Button key={p.id} id={`notif-image-product-${p.id}`} title={p.title?.slice(0, 18) || p.id} active={imageUrl === url} onPress={() => { setImageUrl(url); setProductId(p.id); }} />;
                })}
              </View></ScrollView>
            </>}
            <Text style={ui.label}>OPENS</Text>
            <View style={ui.row}>{DESTINATIONS.map(d => <Button key={d.key} id={`notif-destination-${d.label.replace(/\W+/g, '-').toLowerCase()}`} title={d.label} active={!productId && destination === d.key} onPress={() => { setDestination(d.key); setProductId(''); }} />)}
              {!!productId && <Button id="notif-destination-product" title={`Product ${productId.slice(0, 8)}…`} active onPress={() => setProductId('')} />}</View>
          </View>

          <View style={ui.card} testID="notif-preview">
            <Text style={ui.label}>PREVIEW</Text>
            <View style={{ flexDirection: 'row', gap: 12, alignItems: 'center' }}>
              {previewImage ? <Image source={{ uri: previewImage }} placeholder={IMAGE_PLACEHOLDER} contentFit="cover" style={{ width: 56, height: 56, borderRadius: 10, backgroundColor: Colors.surface }} /> : null}
              <View style={{ flex: 1 }}><Text style={ui.text}>{title || 'Title'}</Text><Text style={ui.muted}>{body || 'Message text'}</Text></View>
            </View>
            <Text style={ui.muted}>Android shows the image in the expanded alert; iOS needs the native notification extension in the store build and falls back to text when the image cannot be fetched.</Text>
          </View>

          <View style={ui.card} testID="notif-audience">
            <Text style={ui.label}>AUDIENCE</Text>
            <View style={ui.row}>{[['customers', 'All customers'], ['all_users', 'All app users (incl. staff)'], ['selected', 'Selected customers']].map(([k, l]) => <Button key={k} id={`notif-target-${k}`} title={l} active={audience.target === k} onPress={() => { setAudience({ ...audience, target: k }); setCount(null); }} />)}</View>
            {audience.target === 'selected' && <>
              <Input id="notif-customer-search" label="Find customers (name, phone, shop, place)" value={customerQuery} onChange={setCustomerQuery} />
              <View style={ui.row}>{customerHits.filter(h => !selected.some(s => s.id === h.id)).map(h => <Button key={h.id} id={`notif-customer-add-${h.id}`} title={`+ ${h.name || h.phone}`} onPress={() => { setSelected([...selected, h]); setCount(null); }} />)}</View>
              <Text style={ui.muted}>{selected.length} selected</Text>
              <View style={ui.row}>{selected.map(s => <Button key={s.id} id={`notif-customer-remove-${s.id}`} title={`× ${s.name || s.phone}`} active onPress={() => { setSelected(selected.filter(x => x.id !== s.id)); setCount(null); }} />)}</View>
            </>}
            {audience.target !== 'selected' && filters && <>
              <Text style={ui.muted}>Filters use real customer data only. Combine with:</Text>
              <View style={ui.row}>{['all', 'any'].map(m => <Button key={m} id={`notif-match-${m}`} title={m === 'all' ? 'ALL filters must match (AND)' : 'ANY filter may match (OR)'} active={audience.match === m} onPress={() => { setAudience({ ...audience, match: m }); setCount(null); }} />)}</View>
              {filters.cities?.length > 0 && <><Text style={ui.muted}>Place / city</Text><ScrollView horizontal showsHorizontalScrollIndicator={false}><View style={ui.row}>{filters.cities.slice(0, 60).map((v: string) => <Button key={v} id={`notif-city-${v.replace(/\W+/g, '-')}`} title={v} active={audience.cities.includes(v)} onPress={() => { toggle('cities', v); setCount(null); }} />)}</View></ScrollView></>}
              {filters.customer_types?.length > 0 && <><Text style={ui.muted}>Customer type</Text><View style={ui.row}>{filters.customer_types.map((v: string) => <Button key={v} id={`notif-type-${v}`} title={v} active={audience.customer_types.includes(v)} onPress={() => { toggle('customer_types', v); setCount(null); }} />)}</View></>}
              {filters.lead_statuses?.length > 0 && <><Text style={ui.muted}>Lead head</Text><View style={ui.row}>{filters.lead_statuses.map((v: string) => <Button key={v} id={`notif-lead-${v}`} title={v.replace(/_/g, ' ')} active={audience.lead_statuses.includes(v)} onPress={() => { toggle('lead_statuses', v); setCount(null); }} />)}</View></>}
              {filters.telecallers?.length > 0 && <><Text style={ui.muted}>Assigned telecaller</Text><View style={ui.row}><Button id="notif-telecaller-any" title="Any" active={!audience.assigned_telecaller} onPress={() => { setAudience({ ...audience, assigned_telecaller: '' }); setCount(null); }} />{filters.telecallers.map((t: any) => <Button key={t.id} id={`notif-telecaller-${t.id}`} title={t.name || t.id} active={audience.assigned_telecaller === t.id} onPress={() => { setAudience({ ...audience, assigned_telecaller: t.id }); setCount(null); }} />)}</View></>}
            </>}
            <Button id="notif-inspect" title="Inspect audience" icon="people-outline" disabled={busy} onPress={inspect} />
            {count && <Text testID="notif-audience-count" style={ui.text}>{count.users} users · {count.reachable_users} with a phone that can receive alerts · {count.devices} devices{'\n'}<Text style={ui.muted}>Excluded: {count.semantics?.excluded}. Everyone in the audience gets the in-app history entry.</Text></Text>}
          </View>

          <View style={ui.row}>
            <Button id="notif-save-draft" title={draft ? 'Update draft' : 'Save draft'} icon="save-outline" disabled={busy || !title.trim() || !body.trim()} onPress={saveDraft} />
            <Button id="notif-test-send" title="Test on my phone" icon="phone-portrait-outline" disabled={busy || !title.trim() || !body.trim()} onPress={testSend} />
            <Button id="notif-send" title={count ? `Send to ${count.users} users` : 'Send (inspect first)'} icon="send-outline" disabled={busy || !count || !title.trim() || !body.trim()}
              onPress={() => confirmAlert('Send this notification?', `${count?.users} users (${count?.devices} devices) will receive it. The audience is frozen at this moment; if it changed since you inspected it, the send is refused.`, send, 'Send')} />
          </View>
          {busy && <Busy />}
        </>}

        {tab === 'history' && <>
          {!campaigns && <Busy />}
          {campaigns?.provider && <Text style={ui.muted} testID="notif-provider">Provider: {campaigns.provider.provider} · access token {campaigns.provider.access_token_configured ? 'configured' : 'not configured'} · {campaigns.provider.ios_image_attachments}</Text>}
          {campaigns?.campaigns.length === 0 && <Text style={ui.muted} testID="notif-history-empty">No campaigns yet.</Text>}
          {campaigns?.campaigns.map((cp: any) => <View key={cp.id} style={ui.card} testID={`notif-campaign-${cp.id}`}>
            <Text style={ui.text}>{cp.title} · <Text style={ui.label}>{String(cp.status).toUpperCase()}</Text></Text>
            <Text style={ui.muted}>{cp.body}</Text>
            <Text style={ui.muted}>{dateText(cp.sent_at || cp.created_at)} · by {cp.created_by_name || 'admin'} · {cp.stats?.users || 0} users · {cp.stats?.devices || 0} devices · {cp.stats?.batches || 0} batches · accepted {cp.stats?.accepted || 0} · errors {cp.stats?.errors || 0} · invalid tokens {cp.stats?.invalid_tokens || 0}</Text>
            <View style={ui.row}>
              <Button id={`notif-campaign-detail-${cp.id}`} title={detail?.id === cp.id ? 'Hide batches' : 'Batches & receipts'} onPress={async () => { if (detail?.id === cp.id) { setDetail(null); return; } try { setDetail(await api.get(`/admin/notifications/campaigns/${cp.id}`)); } catch (e: any) { setError(e.message); } }} />
              {cp.status === 'draft' && <Button id={`notif-campaign-edit-${cp.id}`} title="Edit draft" onPress={() => { setDraft(cp); setTitle(cp.title); setBody(cp.body); setImageUrl(cp.image_url || ''); setDestination(cp.destination); setAudience({ ...EMPTY_AUDIENCE, ...cp.audience }); setTab('compose'); }} />}
            </View>
            {detail?.id === cp.id && <View style={{ gap: 6 }}>
              <Text style={ui.muted}>Audience now: {detail.audience_now?.users} users · {detail.audience_now?.devices} devices</Text>
              {detail.outbox?.length === 0 && <Text style={ui.muted}>No push batches (no reachable devices) — in-app history entries only.</Text>}
              {detail.outbox?.map((j: any) => <Text key={j.id} style={ui.muted} testID={`notif-batch-${j.id}`}>Batch {j.id.slice(0, 6)} · {j.status} · attempts {j.attempts} · accepted {j.accepted ?? '—'} · errors {(j.errors || []).length}{j.receipts_checked_at ? ` · receipts ${dateText(j.receipts_checked_at)}` : ' · receipts pending'}</Text>)}
            </View>}
          </View>)}
          <Text style={ui.muted}>&ldquo;Accepted&rdquo; means the push provider took the message; it is not proof the person saw it. Delivery receipts are fetched about 15 minutes after each batch and invalid device tokens are removed automatically.</Text>
        </>}
      </ScrollView>
    </KeyboardAvoidingView>
  </SafeAreaView>;
}
