import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { View, Text, StyleSheet, FlatList, TouchableOpacity, TextInput, ActivityIndicator, RefreshControl, Modal, ScrollView, Linking } from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api } from '../src/api';
import { useAuth } from '../src/context/AuthContext';
import { showAlert, confirmAlert } from '../src/utils/alert';

const STATUSES = [
  { key: 'new', label: 'New', color: Colors.info },
  { key: 'contacted', label: 'Contacted', color: '#A855F7' },
  { key: 'interested', label: 'Interested', color: Colors.gold },
  { key: 'follow_up_required', label: 'Follow-up', color: Colors.warning },
  { key: 'converted', label: 'Converted', color: Colors.success },
  { key: 'not_interested', label: 'Not Interested', color: Colors.error },
  { key: 'unable_to_reach', label: 'Unreachable', color: Colors.textMuted },
];
const statusMeta = (key: string) => STATUSES.find(s => s.key === key) || STATUSES[0];

interface TCCustomer {
  id: string; name: string; phone: string; shop_name?: string; location?: string; city?: string;
  lead_status?: string; follow_up_at?: string; telecaller_last_note?: string; last_login_at?: string; has_logged_in?: boolean;
}

export default function TelecallerScreen() {
  const { user, loading: authLoading, logout } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [customers, setCustomers] = useState<TCCustomer[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [loadingMore, setLoadingMore] = useState(false);

  // Detail modal
  const [selected, setSelected] = useState<TCCustomer | null>(null);
  const [activities, setActivities] = useState<any[]>([]);
  const [activityLoading, setActivityLoading] = useState(false);
  const [newStatus, setNewStatus] = useState('');
  const [notes, setNotes] = useState('');
  const [followDate, setFollowDate] = useState('');
  const [followTime, setFollowTime] = useState('');
  const [saving, setSaving] = useState(false);

  // Role guard — only executives belong here
  useEffect(() => {
    if (!authLoading) {
      if (!user) router.replace('/login');
      else if (user.role === 'customer') router.replace('/(tabs)');
      else if (user.role === 'admin' || user.role === 'billing_executive') router.replace('/panel');
    }
  }, [authLoading, user]);

  const loadData = useCallback(async (p = 1, append = false) => {
    try {
      setLoadError(false);
      if (p > 1) setLoadingMore(true);
      const qs = new URLSearchParams({ page: String(p), limit: '20' });
      if (search) qs.set('search', search);
      if (statusFilter) qs.set('lead_status', statusFilter);
      const [custRes, sumRes] = await Promise.all([
        api.get(`/telecaller/customers?${qs}`),
        p === 1 ? api.get('/telecaller/summary') : Promise.resolve(null),
      ]);
      setCustomers(prev => append ? [...prev, ...(custRes.customers || [])] : (custRes.customers || []));
      setPages(custRes.pages || 1);
      setPage(p);
      if (sumRes) setSummary(sumRes);
    } catch (e: any) {
      if (p === 1) setLoadError(true);
      console.log('telecaller load failed:', e?.message);
    } finally {
      setLoading(false); setRefreshing(false); setLoadingMore(false);
    }
  }, [search, statusFilter]);

  useEffect(() => {
    if (user?.role === 'executive') { setLoading(true); loadData(1); }
  }, [user?.role, statusFilter]);

  // Debounced search
  useEffect(() => {
    if (user?.role !== 'executive') return;
    const t = setTimeout(() => loadData(1), 400);
    return () => clearTimeout(t);
  }, [search]);

  const openCustomer = async (c: TCCustomer) => {
    setSelected(c);
    setNewStatus(c.lead_status || 'new');
    setNotes('');
    const fu = c.follow_up_at || '';
    setFollowDate(fu.slice(0, 10));
    setFollowTime(fu.length >= 16 ? fu.slice(11, 16) : '');
    setActivityLoading(true);
    try {
      const res = await api.get(`/telecaller/customers/${c.id}/activity`);
      setActivities(res.activities || []);
    } catch { setActivities([]); }
    finally { setActivityLoading(false); }
  };

  const logQuickAction = async (c: TCCustomer, action: 'call' | 'whatsapp') => {
    const phone = c.phone;
    if (action === 'call') Linking.openURL(`tel:+91${phone}`).catch(() => {});
    else Linking.openURL(`https://wa.me/91${phone}`).catch(() => {});
    try { await api.post(`/telecaller/customers/${c.id}/action`, { action }); } catch {}
  };

  const saveUpdate = async () => {
    if (!selected) return;
    if (followDate && !/^\d{4}-\d{2}-\d{2}$/.test(followDate)) { showAlert('Error', 'Follow-up date must be YYYY-MM-DD'); return; }
    if (followTime && !/^\d{2}:\d{2}$/.test(followTime)) { showAlert('Error', 'Follow-up time must be HH:MM (24h)'); return; }
    const statusChanged = newStatus !== (selected.lead_status || 'new');
    const followUpAt = followDate ? `${followDate}T${followTime || '10:00'}` : '';
    setSaving(true);
    try {
      const res = await api.post(`/telecaller/customers/${selected.id}/action`, {
        action: statusChanged ? 'status_change' : (followUpAt && followUpAt !== selected.follow_up_at ? 'follow_up' : 'note'),
        new_status: statusChanged ? newStatus : '',
        notes: notes.trim(),
        follow_up_at: followUpAt,
      });
      const updated = res.customer;
      setCustomers(prev => prev.map(c => c.id === updated.id ? { ...c, ...updated } : c));
      setSelected(prev => prev ? { ...prev, ...updated } : prev);
      setActivities(prev => [res.activity, ...prev]);
      setNotes('');
      api.get('/telecaller/summary').then(setSummary).catch(() => {});
      showAlert('Saved', 'Customer updated');
    } catch (e: any) {
      showAlert('Error', e?.message || 'Could not save. Please try again.');
    } finally { setSaving(false); }
  };

  const handleLogout = () => {
    confirmAlert('Logout', 'Are you sure?', async () => { await logout(); router.replace('/login'); }, 'Logout');
  };

  const summaryCards = useMemo(() => {
    if (!summary) return [];
    return [
      { label: 'Assigned', value: summary.total_customers, color: Colors.gold },
      { label: 'Follow-ups Due', value: summary.follow_ups_due, color: Colors.warning },
      { label: 'Actions Today', value: summary.actions_today, color: Colors.success },
      ...STATUSES.map(s => ({ label: s.label, value: summary.by_status?.[s.key] ?? 0, color: s.color })),
    ];
  }, [summary]);

  if (authLoading || !user || user.role !== 'executive') {
    return <View style={st.loader}><ActivityIndicator size="large" color={Colors.gold} /></View>;
  }

  const renderCustomer = ({ item: c }: { item: TCCustomer }) => {
    const meta = statusMeta(c.lead_status || 'new');
    return (
      <TouchableOpacity testID={`tc-customer-${c.id}`} style={st.custCard} onPress={() => openCustomer(c)} activeOpacity={0.7}>
        <View style={{ flex: 1 }}>
          <View style={st.custTopRow}>
            <Text style={st.custName} numberOfLines={1}>{c.name || c.phone}</Text>
            <View style={[st.statusBadge, { backgroundColor: meta.color + '20' }]}>
              <Text style={[st.statusBadgeText, { color: meta.color }]}>{meta.label}</Text>
            </View>
          </View>
          <Text style={st.custMeta} numberOfLines={1}>
            {c.shop_name || 'No shop name'} • {c.location || c.city || 'No location'}
          </Text>
          <Text style={st.custPhone}>+91 {c.phone}</Text>
          {c.follow_up_at ? (
            <View style={st.followRow}>
              <Ionicons name="alarm-outline" size={12} color={Colors.warning} />
              <Text style={st.followText}>{c.follow_up_at.replace('T', ' ')}</Text>
            </View>
          ) : null}
        </View>
        <View style={st.actionCol}>
          <TouchableOpacity testID={`tc-call-${c.id}`} style={[st.quickBtn, { backgroundColor: Colors.success + '18' }]} onPress={() => logQuickAction(c, 'call')}>
            <Ionicons name="call" size={18} color={Colors.success} />
          </TouchableOpacity>
          <TouchableOpacity testID={`tc-wa-${c.id}`} style={[st.quickBtn, { backgroundColor: '#25D36618' }]} onPress={() => logQuickAction(c, 'whatsapp')}>
            <Ionicons name="logo-whatsapp" size={18} color="#25D366" />
          </TouchableOpacity>
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <SafeAreaView style={st.container} edges={['top']}>
      {/* Header */}
      <View style={st.header}>
        <View>
          <Text style={st.headerTitle}>Telecaller</Text>
          <Text style={st.headerSub}>{user.name || user.phone}</Text>
        </View>
        <TouchableOpacity testID="tc-logout" style={st.logoutBtn} onPress={handleLogout}>
          <Ionicons name="log-out-outline" size={22} color={Colors.error} />
        </TouchableOpacity>
      </View>

      {/* Performance summary */}
      {summary && (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexGrow: 0 }} contentContainerStyle={st.summaryRow}>
          {summaryCards.map(card => (
            <View key={card.label} style={[st.summaryCard, { borderColor: card.color + '40' }]}>
              <Text style={[st.summaryValue, { color: card.color }]}>{card.value}</Text>
              <Text style={st.summaryLabel}>{card.label}</Text>
            </View>
          ))}
        </ScrollView>
      )}

      {/* Search + status filter */}
      <View style={st.searchRow}>
        <Ionicons name="search" size={16} color={Colors.textMuted} />
        <TextInput
          testID="tc-search"
          style={st.searchInput}
          placeholder="Search name, phone, shop..."
          placeholderTextColor={Colors.textMuted}
          value={search}
          onChangeText={setSearch}
        />
        {search ? <TouchableOpacity onPress={() => setSearch('')}><Ionicons name="close-circle" size={16} color={Colors.textMuted} /></TouchableOpacity> : null}
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexGrow: 0 }} contentContainerStyle={st.filterRow}>
        <TouchableOpacity testID="tc-filter-all" style={[st.filterChip, !statusFilter && st.filterChipActive]} onPress={() => setStatusFilter('')}>
          <Text style={[st.filterChipText, !statusFilter && st.filterChipTextActive]}>All</Text>
        </TouchableOpacity>
        {STATUSES.map(s => (
          <TouchableOpacity key={s.key} testID={`tc-filter-${s.key}`} style={[st.filterChip, statusFilter === s.key && st.filterChipActive]} onPress={() => setStatusFilter(statusFilter === s.key ? '' : s.key)}>
            <Text style={[st.filterChipText, statusFilter === s.key && st.filterChipTextActive]}>{s.label}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      {/* Customer list */}
      {loading ? (
        <ActivityIndicator color={Colors.gold} style={{ marginTop: 40 }} />
      ) : loadError ? (
        <View style={st.errorBox}>
          <Ionicons name="cloud-offline-outline" size={36} color={Colors.error} />
          <Text style={st.errorText}>Could not load customers. Please check your connection.</Text>
          <TouchableOpacity style={st.retryBtn} onPress={() => { setLoading(true); loadData(1); }}>
            <Text style={st.retryBtnText}>Retry</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <FlatList
          data={customers}
          keyExtractor={c => c.id}
          renderItem={renderCustomer}
          contentContainerStyle={{ paddingHorizontal: Spacing.lg, paddingBottom: insets.bottom + 24 }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); loadData(1); }} tintColor={Colors.gold} />}
          onEndReached={() => { if (page < pages && !loadingMore) loadData(page + 1, true); }}
          onEndReachedThreshold={0.5}
          ListEmptyComponent={
            <View style={st.emptyBox}>
              <Ionicons name="people-outline" size={40} color={Colors.textMuted} />
              <Text style={st.emptyText}>{search || statusFilter ? 'No customers match this filter' : 'No customers assigned to you yet.\nAsk the admin to assign customers.'}</Text>
            </View>
          }
          ListFooterComponent={loadingMore ? <ActivityIndicator color={Colors.gold} style={{ padding: 16 }} /> : null}
        />
      )}

      {/* Customer detail modal */}
      <Modal visible={!!selected} animationType="slide" transparent onRequestClose={() => setSelected(null)}>
        <View style={st.modalOverlay}>
          <View style={[st.modalSheet, { paddingBottom: Math.max(insets.bottom, 16) }]}>
            <View style={st.modalHandle} />
            <ScrollView showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">
              {selected && (
                <>
                  <View style={st.modalHeader}>
                    <View style={{ flex: 1 }}>
                      <Text style={st.modalName}>{selected.name || selected.phone}</Text>
                      <Text style={st.custMeta}>{selected.shop_name || 'No shop name'} • {selected.location || selected.city || 'No location'}</Text>
                      <Text style={st.custPhone}>+91 {selected.phone}</Text>
                    </View>
                    <TouchableOpacity testID="tc-modal-close" onPress={() => setSelected(null)} style={st.closeBtn}>
                      <Ionicons name="close" size={22} color={Colors.text} />
                    </TouchableOpacity>
                  </View>

                  <View style={st.modalActions}>
                    <TouchableOpacity testID="tc-modal-call" style={[st.bigActionBtn, { backgroundColor: Colors.success }]} onPress={() => logQuickAction(selected, 'call')}>
                      <Ionicons name="call" size={18} color="#fff" /><Text style={st.bigActionText}>Call</Text>
                    </TouchableOpacity>
                    <TouchableOpacity testID="tc-modal-wa" style={[st.bigActionBtn, { backgroundColor: '#25D366' }]} onPress={() => logQuickAction(selected, 'whatsapp')}>
                      <Ionicons name="logo-whatsapp" size={18} color="#fff" /><Text style={st.bigActionText}>WhatsApp</Text>
                    </TouchableOpacity>
                  </View>

                  <Text style={st.fieldLabel}>STATUS</Text>
                  <View style={st.statusGrid}>
                    {STATUSES.map(s => (
                      <TouchableOpacity key={s.key} testID={`tc-status-${s.key}`} style={[st.statusOption, newStatus === s.key && { backgroundColor: s.color + '22', borderColor: s.color }]} onPress={() => setNewStatus(s.key)}>
                        <Text style={[st.statusOptionText, newStatus === s.key && { color: s.color, fontWeight: '700' }]}>{s.label}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>

                  <Text style={st.fieldLabel}>FOLLOW-UP</Text>
                  <View style={{ flexDirection: 'row', gap: 8 }}>
                    <TextInput testID="tc-follow-date" style={[st.input, { flex: 1.4 }]} placeholder="YYYY-MM-DD" placeholderTextColor={Colors.textMuted} value={followDate} onChangeText={setFollowDate} />
                    <TextInput testID="tc-follow-time" style={[st.input, { flex: 1 }]} placeholder="HH:MM" placeholderTextColor={Colors.textMuted} value={followTime} onChangeText={setFollowTime} />
                  </View>

                  <Text style={st.fieldLabel}>NOTES</Text>
                  <TextInput
                    testID="tc-notes"
                    style={[st.input, { minHeight: 70, textAlignVertical: 'top' }]}
                    placeholder="Add a note about this call..."
                    placeholderTextColor={Colors.textMuted}
                    value={notes}
                    onChangeText={setNotes}
                    multiline
                  />

                  <TouchableOpacity testID="tc-save" style={[st.saveBtn, saving && { opacity: 0.5 }]} onPress={saveUpdate} disabled={saving}>
                    {saving ? <ActivityIndicator color="#000" /> : <Text style={st.saveBtnText}>SAVE UPDATE</Text>}
                  </TouchableOpacity>

                  <Text style={st.fieldLabel}>ACTIVITY HISTORY</Text>
                  {activityLoading ? <ActivityIndicator color={Colors.gold} style={{ marginVertical: 12 }} /> : activities.length === 0 ? (
                    <Text style={st.emptyText}>No activity yet</Text>
                  ) : activities.map(a => (
                    <View key={a.id} style={st.activityRow}>
                      <Ionicons
                        name={a.action === 'call' ? 'call' : a.action === 'whatsapp' ? 'logo-whatsapp' : a.action === 'status_change' ? 'swap-horizontal' : a.action === 'follow_up' ? 'alarm' : 'document-text'}
                        size={14} color={Colors.gold}
                      />
                      <View style={{ flex: 1 }}>
                        <Text style={st.activityText}>
                          {a.action === 'status_change'
                            ? `${statusMeta(a.previous_status).label} → ${statusMeta(a.new_status).label}`
                            : a.action.replace('_', ' ')}
                          {a.notes ? ` — ${a.notes}` : ''}
                        </Text>
                        <Text style={st.activityMeta}>{a.telecaller_name || 'Telecaller'} • {new Date(a.created_at).toLocaleString()}</Text>
                      </View>
                    </View>
                  ))}
                  <View style={{ height: 20 }} />
                </>
              )}
            </ScrollView>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  loader: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: Colors.background },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md },
  headerTitle: { fontSize: FontSize.xl, fontWeight: '700', color: Colors.gold, letterSpacing: 1 },
  headerSub: { fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: 2 },
  logoutBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: Colors.error + '15', alignItems: 'center', justifyContent: 'center' },
  summaryRow: { paddingHorizontal: Spacing.lg, gap: 8, paddingBottom: Spacing.sm },
  summaryCard: { minWidth: 86, backgroundColor: Colors.card, borderRadius: 12, borderWidth: 1, paddingVertical: 10, paddingHorizontal: 12, alignItems: 'center' },
  summaryValue: { fontSize: FontSize.lg, fontWeight: '700' },
  summaryLabel: { fontSize: 10, color: Colors.textMuted, marginTop: 2 },
  searchRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginHorizontal: Spacing.lg, marginBottom: Spacing.sm, backgroundColor: Colors.surface, borderRadius: 10, paddingHorizontal: 12, borderWidth: 1, borderColor: Colors.border },
  searchInput: { flex: 1, color: Colors.text, paddingVertical: 10, fontSize: FontSize.sm },
  filterRow: { paddingHorizontal: Spacing.lg, gap: 6, paddingBottom: Spacing.sm },
  filterChip: { paddingHorizontal: 12, paddingVertical: 7, borderRadius: 16, backgroundColor: Colors.surface, borderWidth: 1, borderColor: Colors.border },
  filterChipActive: { backgroundColor: Colors.gold + '20', borderColor: Colors.gold },
  filterChipText: { fontSize: FontSize.xs, color: Colors.textMuted, fontWeight: '600' },
  filterChipTextActive: { color: Colors.gold },
  custCard: { flexDirection: 'row', backgroundColor: Colors.card, borderRadius: 14, padding: Spacing.md, marginBottom: Spacing.sm, borderWidth: 1, borderColor: Colors.cardBorder },
  custTopRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  custName: { flex: 1, fontSize: FontSize.md, fontWeight: '700', color: Colors.text },
  custMeta: { fontSize: FontSize.xs, color: Colors.textSecondary, marginTop: 2 },
  custPhone: { fontSize: FontSize.xs, color: Colors.textMuted, marginTop: 2 },
  followRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 4 },
  followText: { fontSize: FontSize.xs, color: Colors.warning },
  statusBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 },
  statusBadgeText: { fontSize: 10, fontWeight: '700' },
  actionCol: { justifyContent: 'center', gap: 8, marginLeft: Spacing.sm },
  quickBtn: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  emptyBox: { alignItems: 'center', paddingVertical: 60, gap: 10 },
  emptyText: { fontSize: FontSize.sm, color: Colors.textMuted, textAlign: 'center' },
  errorBox: { alignItems: 'center', paddingVertical: 60, paddingHorizontal: Spacing.xl, gap: 10 },
  errorText: { fontSize: FontSize.sm, color: Colors.error, textAlign: 'center' },
  retryBtn: { backgroundColor: Colors.error + '20', paddingHorizontal: 24, paddingVertical: 10, borderRadius: 10 },
  retryBtnText: { fontSize: FontSize.sm, fontWeight: '700', color: Colors.error },
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'flex-end' },
  modalSheet: { backgroundColor: Colors.background, borderTopLeftRadius: 20, borderTopRightRadius: 20, paddingHorizontal: Spacing.lg, paddingTop: 8, maxHeight: '88%' },
  modalHandle: { width: 40, height: 4, borderRadius: 2, backgroundColor: Colors.border, alignSelf: 'center', marginBottom: 10 },
  modalHeader: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  modalName: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text },
  closeBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: Colors.surface, alignItems: 'center', justifyContent: 'center' },
  modalActions: { flexDirection: 'row', gap: 10, marginTop: Spacing.md },
  bigActionBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingVertical: 12, borderRadius: 10 },
  bigActionText: { fontSize: FontSize.sm, fontWeight: '700', color: '#fff' },
  fieldLabel: { fontSize: FontSize.xs, color: Colors.textSecondary, letterSpacing: 1.5, fontWeight: '600', marginTop: Spacing.lg, marginBottom: 6 },
  statusGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  statusOption: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, backgroundColor: Colors.surface, borderWidth: 1, borderColor: Colors.border },
  statusOptionText: { fontSize: FontSize.xs, color: Colors.textMuted },
  input: { backgroundColor: Colors.surface, borderRadius: 10, borderWidth: 1, borderColor: Colors.border, color: Colors.text, paddingHorizontal: 12, paddingVertical: 10, fontSize: FontSize.sm },
  saveBtn: { backgroundColor: Colors.gold, borderRadius: 10, paddingVertical: 14, alignItems: 'center', marginTop: Spacing.md },
  saveBtnText: { fontSize: FontSize.sm, fontWeight: '700', color: '#000', letterSpacing: 1 },
  activityRow: { flexDirection: 'row', gap: 8, alignItems: 'flex-start', paddingVertical: 8, borderBottomWidth: 0.5, borderBottomColor: Colors.border },
  activityText: { fontSize: FontSize.sm, color: Colors.text, textTransform: 'capitalize' },
  activityMeta: { fontSize: 10, color: Colors.textMuted, marginTop: 2 },
});
