import React, { useCallback, useEffect, useState } from 'react';
import { Linking, Modal, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Image } from 'expo-image';
import { Ionicons } from '@expo/vector-icons';
import { api } from '../../api';
import { useAuth } from '../../context/AuthContext';
import { Colors } from '../../theme';
import { confirmAlert } from '../../utils/alert';
import { IMAGE_PLACEHOLDER } from '../../imagePlaceholder';
import { KeyboardAwareScreen } from '../KeyboardScreen';
import { Button, Busy, dateText, duration, Input, ui } from './Controls';
import { HEAD_COLORS, followUpOptions, itemImage, typeLabel } from './requestHelpers';

type Props = { requestId: string | null; onClose: () => void; onChanged: () => void; staff: any[]; onOpenCustomer?: (customerId: string) => void };

/**
 * Query detail + work actions. Ownership is enforced by the server (`permissions`): only the claimant or an
 * administrator may change head / notes / follow-up / complete; other staff see who holds the query. Every mutation
 * carries the version read here, so a stale screen gets 409 and reloads instead of overwriting newer work.
 */
export default function RequestDetail({ requestId, onClose, onChanged, staff, onOpenCustomer }: Props) {
  const { user } = useAuth();
  const router = useRouter();
  const [detail, setDetail] = useState<any>(null), [history, setHistory] = useState<any[]>([]);
  const [error, setError] = useState(''), [busy, setBusy] = useState(false), [info, setInfo] = useState('');
  const [note, setNote] = useState(''), [reason, setReason] = useState(''), [followUp, setFollowUp] = useState('');
  const [outcome, setOutcome] = useState('other'), [assignTo, setAssignTo] = useState('');
  const [catalog, setCatalog] = useState<any>(null);

  const load = useCallback(async () => {
    if (!requestId) return;
    try {
      const [d, h] = await Promise.all([api.get(`/requests/${requestId}`), api.get(`/requests/${requestId}/history`)]);
      setDetail(d); setHistory(h.history || []); setError('');
    } catch (e: any) { setError(e.message); }
  }, [requestId]);
  useEffect(() => { setDetail(null); setNote(''); setReason(''); setFollowUp(''); setInfo(''); load(); }, [load]);
  useEffect(() => { api.get('/requests/catalog').then(setCatalog).catch(() => {}); }, []);

  const mutate = async (body: any, successInfo = '') => {
    if (!detail) return;
    setBusy(true); setError('');
    try {
      const res = await api.patch(`/requests/${detail.id}`, { ...body, version: detail.version, idempotency_key: `${detail.id}-${Date.now()}-${Math.random()}` });
      setInfo(successInfo || (res.already_claimed ? 'Already yours' : res.already_completed ? 'Already completed' : ''));
      await load(); onChanged();
    } catch (e: any) {
      const body409 = e.body || {};
      if (e.code === 'ALREADY_ASSIGNED') setError(`${body409.assignee_name || 'Another telecaller'} took this query first`);
      else if (e.code === 'VERSION_CONFLICT') setError('This query changed on the server; the latest state is shown now');
      else setError(e.message);
      await load(); onChanged();
    } finally { setBusy(false); }
  };

  const request = detail;
  const perms = request?.permissions || {};
  const open = request && !['resolved', 'cancelled'].includes(request.status);
  const isAdmin = user?.role === 'admin';
  const isBilling = user?.role === 'billing_executive';
  const canWork = !!perms.can_work && open;
  const heldByOther = open && request?.assignee_id && request.assignee_id !== user?.id;
  const contact = request?.contact || {};
  const openTel = () => contact.tel && Linking.openURL(`tel:${contact.tel}`).catch(() => setError('No phone app available on this device'));
  const openWhatsApp = () => contact.whatsapp && Linking.openURL(`https://wa.me/${contact.whatsapp}`).catch(() => setError('WhatsApp is not available on this device'));
  const heads: string[] = catalog?.heads || ['new', 'contacted', 'interested', 'follow_up', 'unreachable'];
  const headLabels: Record<string, string> = catalog?.head_labels || {};

  return (
    <Modal visible={!!requestId} animationType="slide" onRequestClose={onClose}>
      <SafeAreaView style={ui.screen}>
        <KeyboardAwareScreen contentContainerStyle={ui.content} testID="request-detail-scroll">
            <View style={ui.row}><Button id="request-detail-close" title="Close" icon="arrow-back" onPress={onClose} /></View>
            {!request && !error && <Busy />}
            {!!error && <Text testID="request-detail-error" style={ui.error}>{error}</Text>}
            {!!info && <Text testID="request-detail-info" style={[ui.muted, ui.success]}>{info}</Text>}
            {request && <>
              <Text testID="request-detail-title" style={ui.title}>{typeLabel(request.request_type)}</Text>
              <View style={ui.row}>
                <View style={[chip, { borderColor: HEAD_COLORS[request.head] || Colors.border }]} testID="request-detail-head"><Text style={ui.muted}>{open ? (request.head_label || request.head) : request.status === 'resolved' ? 'Completed' : 'Cancelled'}</Text></View>
                <View style={chip} testID="request-detail-owner"><Text style={ui.muted}>{open ? (request.assignee_id ? `Taken by ${request.assignee_id === user?.id ? 'you' : request.assignee_name || 'a telecaller'}` : 'Unclaimed') : `Completed by ${request.resolver_name || request.completed_by_name || 'staff'}`}</Text></View>
                {!!request.reset_count && <View style={chip}><Text style={ui.muted}>Released at 03:00 ×{request.reset_count}</Text></View>}
              </View>

              {/* Customer */}
              <View style={ui.card} testID="request-detail-customer">
                <Text style={ui.label}>CUSTOMER</Text>
                <Text style={ui.text}>{request.customer_name || request.user_name || 'Customer'}</Text>
                <Text style={ui.muted}>{request.customer_shop_name || 'Shop not recorded'} · {request.customer_location || request.user_city || 'Place not recorded'}</Text>
                <Text testID="request-detail-phone" style={ui.text}>{request.customer_phone_display || request.user_phone}</Text>
                <View style={ui.row}>
                  <Button id="request-call" title="Call" icon="call" onPress={openTel} disabled={!contact.tel} />
                  <Button id="request-whatsapp" title={request.request_type === 'video_call' ? 'Open WhatsApp chat' : 'WhatsApp'} icon="logo-whatsapp" onPress={openWhatsApp} disabled={!contact.whatsapp} />
                  {onOpenCustomer && request.customer_id && <Button id="request-open-customer" title={`Customer history (${request.other_requests || 0} more)`} icon="person-outline" onPress={() => onOpenCustomer(request.customer_id)} />}
                </View>
                {request.request_type === 'video_call' && <Text style={ui.muted} testID="request-video-note">Video call requested. WhatsApp offers no direct video-call link: open the chat and use WhatsApp's own video-call button.</Text>}
                {!!request.customer?.lead_status && <Text style={ui.muted}>Customer lead state: {String(request.customer.lead_status).replace(/_/g, ' ')} (separate from this query)</Text>}
              </View>

              {/* Request */}
              <View style={ui.card}>
                <Text style={ui.label}>REQUEST</Text>
                <Text style={ui.text}>{request.notes || 'No customer note'}</Text>
                {!!request.preferred_time && <Text style={ui.muted}>Preferred time: {request.preferred_time}</Text>}
                {!!request.category && <Text style={ui.muted}>Category: {request.category}</Text>}
                <Text style={ui.muted}>Created {dateText(request.created_at)} · {open ? `Waiting ${duration(request.pending_seconds)}` : `Handled in ${duration(request.handling_seconds)}`}</Text>
                {!!request.follow_up_at && <Text testID="request-detail-follow-up" style={ui.text}>Follow-up: {dateText(request.follow_up_at)}</Text>}
              </View>

              {/* Items */}
              {request.items?.length > 0 && <View style={ui.card} testID="request-detail-items">
                <Text style={ui.label}>REQUESTED ITEMS · {request.items.length}</Text>
                {request.items.map((it: any) => {
                  const uri = itemImage(it);
                  return <View key={it.product_id} style={itemRow} testID={`request-item-${it.product_id}`}>
                    {uri ? <TouchableOpacity testID={`request-item-photo-${it.product_id}`} accessibilityRole="imagebutton" accessibilityLabel={`Open photo of ${it.title || 'item'}`}
                             onPress={() => router.push({ pathname: '/image-viewer', params: { productId: it.product_id, ids: it.product_id } } as any)}>
                             <Image source={{ uri }} placeholder={IMAGE_PLACEHOLDER} contentFit="cover" cachePolicy="memory-disk" style={itemThumb} />
                           </TouchableOpacity>
                         : <View style={[itemThumb, { alignItems: 'center', justifyContent: 'center' }]}><Ionicons name="image-outline" size={20} color={Colors.textMuted} /></View>}
                    <View style={{ flex: 1 }}>
                      <Text style={ui.text}>{it.title}</Text>
                      <Text style={ui.muted}>{[it.product_code, it.metal_type, it.weight ? `${it.weight} g` : '', it.quantity > 1 ? `× ${it.quantity}` : ''].filter(Boolean).join(' · ')}</Text>
                      {!it.available && <Text style={[ui.muted, { color: Colors.warning }]}>No longer listed — historical snapshot</Text>}
                    </View>
                  </View>;
                })}
              </View>}

              {/* Work actions */}
              {open && perms.can_claim && !isBilling && <Button id="request-claim" title="Take this query" icon="hand-left-outline" disabled={busy} onPress={() => mutate({ action: 'claim' }, 'Query is now yours')} />}
              {heldByOther && !isAdmin && <Text testID="request-held-by-other" style={ui.muted}>{request.assignee_name || 'Another telecaller'} is working on this query. You can view it, but only the claimant (or an administrator) can update or complete it.</Text>}
              {canWork && <View style={ui.card} testID="request-work-card">
                <Text style={ui.label}>HEAD</Text>
                <View style={ui.row}>{heads.map(h => <Button key={h} id={`request-head-${h}`} title={headLabels[h] || h} active={request.head === h} disabled={busy} onPress={() => mutate({ head: h })} />)}</View>
                <Text style={ui.label}>FOLLOW-UP</Text>
                <View style={ui.row}>{followUpOptions().map(o => <Button key={o.label} id={`request-follow-${o.label.replace(/\W+/g, '-').toLowerCase()}`} title={o.label} disabled={busy} onPress={() => mutate({ follow_up_at: o.iso, head: 'follow_up' })} />)}
                  {!!request.follow_up_at && <Button id="request-follow-clear" title="Clear follow-up" disabled={busy} onPress={() => mutate({ follow_up_at: '' })} />}</View>
                <Input id="request-follow-custom" label="Custom follow-up (YYYY-MM-DD HH:MM, IST)" value={followUp} onChange={setFollowUp} />
                {!!followUp && <Button id="request-follow-save" title="Save custom follow-up" disabled={busy} onPress={() => mutate({ follow_up_at: new Date(followUp.replace(' ', 'T') + '+05:30').toISOString(), head: 'follow_up' })} />}
                <Input id="request-note" label="Note (visible to staff only)" value={note} onChange={setNote} multiline />
                <Button id="request-save-note" title="Save note" disabled={busy || !note.trim()} onPress={async () => { await mutate({ notes: note }, 'Note saved'); setNote(''); }} />
                <Text style={ui.label}>MARK COMPLETE</Text>
                <View style={ui.row}>{(catalog?.outcomes || ['converted', 'not_interested', 'other']).map((o: string) => <Button key={o} id={`request-outcome-${o}`} title={o.replace(/_/g, ' ')} active={outcome === o} onPress={() => setOutcome(o)} />)}</View>
                <Button id="request-complete" title="Mark Complete" icon="checkmark-done" disabled={busy}
                  onPress={() => confirmAlert('Mark complete?', 'The query leaves the pending list and is added to your completed history. Administrators can reopen it.',
                    () => mutate({ action: 'complete', outcome, notes: note }, 'Marked complete'), 'Complete')} />
              </View>}

              {/* Admin actions */}
              {isAdmin && <View style={ui.card} testID="request-admin-card">
                <Text style={ui.label}>ADMINISTRATOR</Text>
                <Input id="request-admin-reason" label="Reason (recorded in the audit history, min 5 characters)" value={reason} onChange={setReason} />
                {open && <>
                  <Text style={ui.muted}>Assign / reassign</Text>
                  <View style={ui.row}>{staff.filter(s => ['admin', 'telecaller'].includes(s.role) && s.id !== request.assignee_id).map(s => <Button key={s.id} id={`request-assign-${s.id}`} title={s.name || 'Unnamed'} active={assignTo === s.id} onPress={() => setAssignTo(s.id)} />)}</View>
                  <View style={ui.row}>
                    <Button id="request-assign-confirm" title="Assign" disabled={busy || !assignTo || reason.trim().length < 5} onPress={() => mutate({ action: 'assign', assigned_to: assignTo, reason }, 'Reassigned')} />
                    {!!request.assignee_id && <Button id="request-release" title="Release to queue" disabled={busy || reason.trim().length < 5} onPress={() => mutate({ action: 'release', reason }, 'Released')} />}
                  </View>
                </>}
                {!open && <Button id="request-reopen" title="Reopen (back to pending)" disabled={busy || reason.trim().length < 5}
                  onPress={() => confirmAlert('Reopen this query?', 'It returns to the shared pending list as New; the earlier completion is marked superseded in the reports.', () => mutate({ action: 'reopen', status: 'pending', reason }, 'Reopened'), 'Reopen')} />}
              </View>}

              {/* Completions ledger */}
              {request.completions?.length > 0 && <View style={ui.card} testID="request-completions">
                <Text style={ui.label}>COMPLETION LEDGER</Text>
                {request.completions.map((cpl: any) => <Text key={cpl.id} style={ui.muted}>{dateText(cpl.completed_at)} · {cpl.actor_name} · {cpl.outcome}{cpl.superseded_at ? ' · superseded (reopened)' : ''}</Text>)}
              </View>}

              <Text testID="request-history-heading" style={ui.label}>TIMELINE</Text>
              {history.map((e: any) => <View testID={`request-event-${e.id}`} key={e.id} style={ui.card}>
                <Text style={ui.text}>{String(e.type).replace(/_/g, ' ')}{e.old || e.new ? ` · ${e.old || '—'} → ${e.new || '—'}` : ''}</Text>
                <Text style={ui.muted}>{e.actor_name || e.actor_role || 'System'} · {dateText(e.timestamp)}</Text>
                {!!e.notes && <Text style={ui.text}>{e.notes}</Text>}
              </View>)}
            </>}
        </KeyboardAwareScreen>
      </SafeAreaView>
    </Modal>
  );
}

const chip = { borderWidth: 1, borderColor: Colors.border, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 6 } as const;
const itemRow = { flexDirection: 'row', gap: 12, alignItems: 'center' } as const;
const itemThumb = { width: 56, height: 56, borderRadius: 8, backgroundColor: Colors.surface } as const;
