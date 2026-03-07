import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, TextInput, ActivityIndicator, Alert, RefreshControl } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api } from '../src/api';
import { useLang } from '../src/context/LanguageContext';

const STATUSES = ['all', 'pending', 'in_progress', 'contacted', 'resolved', 'no_response'];
const TYPES = ['all', 'call', 'video_call', 'ask_price', 'ask_similar', 'hold_item', 'quick_reorder'];

export default function ExecutiveScreen() {
  const router = useRouter();
  const { t } = useLang();
  const [requests, setRequests] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [statusFilter, setStatusFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all');
  const [noteText, setNoteText] = useState('');
  const [editingId, setEditingId] = useState('');

  const loadRequests = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (statusFilter !== 'all') params.set('status', statusFilter);
      if (typeFilter !== 'all') params.set('request_type', typeFilter);
      const res = await api.get(`/requests?${params}`);
      setRequests(res.requests || []);
    } catch (e: any) { Alert.alert('Error', e.message); }
    finally { setLoading(false); setRefreshing(false); }
  }, [statusFilter, typeFilter]);

  useEffect(() => { setLoading(true); loadRequests(); }, [statusFilter, typeFilter]);

  const updateStatus = async (id: string, status: string) => {
    try {
      await api.patch(`/requests/${id}`, { status, assigned_to: '', notes: noteText || '' });
      setEditingId('');
      setNoteText('');
      loadRequests();
    } catch (e: any) { Alert.alert('Error', e.message); }
  };

  const statusColor = (s: string) => {
    switch (s) {
      case 'pending': return Colors.warning;
      case 'in_progress': return Colors.info;
      case 'contacted': return '#A855F7';
      case 'resolved': return Colors.success;
      case 'no_response': return Colors.error;
      default: return Colors.textMuted;
    }
  };

  const typeIcon = (t: string) => {
    switch (t) {
      case 'video_call': return 'videocam';
      case 'call': return 'call';
      case 'ask_price': return 'pricetag';
      case 'ask_similar': return 'copy';
      case 'hold_item': return 'bookmark';
      case 'quick_reorder': return 'refresh';
      default: return 'chatbox';
    }
  };

  const pendingCount = requests.filter(r => r.status === 'pending').length;
  const todayCount = requests.filter(r => new Date(r.created_at).toDateString() === new Date().toDateString()).length;

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity testID="exec-back-btn" onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color={Colors.text} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>{t('exec_panel')}</Text>
        <TouchableOpacity onPress={() => { setLoading(true); loadRequests(); }} style={styles.backBtn}>
          <Ionicons name="refresh" size={20} color={Colors.gold} />
        </TouchableOpacity>
      </View>

      {/* Stats */}
      <View style={styles.statsRow}>
        <View style={[styles.statCard, { borderColor: Colors.warning + '40' }]}>
          <Text style={[styles.statNum, { color: Colors.warning }]}>{pendingCount}</Text>
          <Text style={styles.statLabel}>{t('pending')}</Text>
        </View>
        <View style={[styles.statCard, { borderColor: Colors.info + '40' }]}>
          <Text style={[styles.statNum, { color: Colors.info }]}>{todayCount}</Text>
          <Text style={styles.statLabel}>Today</Text>
        </View>
        <View style={[styles.statCard, { borderColor: Colors.success + '40' }]}>
          <Text style={[styles.statNum, { color: Colors.success }]}>{requests.length}</Text>
          <Text style={styles.statLabel}>Total</Text>
        </View>
      </View>

      {/* Status Filter */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filterRow}>
        {STATUSES.map(s => (
          <TouchableOpacity key={s} testID={`status-filter-${s}`} style={[styles.chip, statusFilter === s && { backgroundColor: statusColor(s) + '20', borderColor: statusColor(s) }]} onPress={() => setStatusFilter(s)}>
            <Text style={[styles.chipText, statusFilter === s && { color: statusColor(s) }]}>{s.replace(/_/g, ' ')}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      {/* Type Filter */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filterRow}>
        {TYPES.map(tp => (
          <TouchableOpacity key={tp} style={[styles.chip, typeFilter === tp && styles.chipActive]} onPress={() => setTypeFilter(tp)}>
            {tp !== 'all' && <Ionicons name={typeIcon(tp) as any} size={12} color={typeFilter === tp ? Colors.gold : Colors.textMuted} />}
            <Text style={[styles.chipText, typeFilter === tp && styles.chipTextActive]}>{tp.replace(/_/g, ' ')}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      {loading ? <ActivityIndicator color={Colors.gold} style={{ marginTop: 40 }} /> : (
        <ScrollView refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); loadRequests(); }} tintColor={Colors.gold} />} showsVerticalScrollIndicator={false} contentContainerStyle={styles.listContent}>
          {requests.map(r => (
            <View key={r.id} style={styles.requestCard}>
              {/* Header */}
              <View style={styles.reqHeader}>
                <View style={styles.reqTypeRow}>
                  <View style={[styles.typeIcon, { backgroundColor: statusColor(r.status) + '15' }]}>
                    <Ionicons name={typeIcon(r.request_type) as any} size={16} color={statusColor(r.status)} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.reqType}>{r.request_type?.replace(/_/g, ' ')}</Text>
                    <Text style={styles.reqTime}>{new Date(r.created_at).toLocaleString()}</Text>
                  </View>
                  <View style={[styles.statusBadge, { backgroundColor: statusColor(r.status) + '20' }]}>
                    <Text style={[styles.statusText, { color: statusColor(r.status) }]}>{r.status?.replace(/_/g, ' ')}</Text>
                  </View>
                </View>
              </View>

              {/* Customer Info */}
              <View style={styles.customerInfo}>
                <View style={styles.infoRow}><Ionicons name="person" size={14} color={Colors.textMuted} /><Text style={styles.infoText}>{r.user_name || 'Unknown'}</Text></View>
                <View style={styles.infoRow}><Ionicons name="call" size={14} color={Colors.textMuted} /><Text style={styles.infoText}>{r.user_phone}</Text></View>
                {r.category ? <View style={styles.infoRow}><Ionicons name="grid" size={14} color={Colors.textMuted} /><Text style={styles.infoText}>{r.category}</Text></View> : null}
                {r.preferred_time ? <View style={styles.infoRow}><Ionicons name="time" size={14} color={Colors.textMuted} /><Text style={styles.infoText}>{r.preferred_time}</Text></View> : null}
                {r.notes ? <View style={styles.infoRow}><Ionicons name="document-text" size={14} color={Colors.textMuted} /><Text style={styles.infoText}>{r.notes}</Text></View> : null}
                {r.admin_notes ? <View style={styles.infoRow}><Ionicons name="chatbox" size={14} color={Colors.gold} /><Text style={[styles.infoText, { color: Colors.gold }]}>{r.admin_notes}</Text></View> : null}
              </View>

              {/* Actions */}
              {editingId === r.id ? (
                <View style={styles.noteBox}>
                  <TextInput style={styles.noteInput} placeholder="Add resolution notes..." placeholderTextColor={Colors.textMuted} value={noteText} onChangeText={setNoteText} multiline />
                </View>
              ) : null}

              <View style={styles.actionsRow}>
                {r.status === 'pending' && <>
                  <TouchableOpacity style={[styles.actionBtn, { backgroundColor: Colors.info + '15' }]} onPress={() => updateStatus(r.id, 'in_progress')}><Text style={[styles.actionText, { color: Colors.info }]}>In Progress</Text></TouchableOpacity>
                  <TouchableOpacity style={[styles.actionBtn, { backgroundColor: '#A855F715' }]} onPress={() => updateStatus(r.id, 'contacted')}><Text style={[styles.actionText, { color: '#A855F7' }]}>Contacted</Text></TouchableOpacity>
                </>}
                {(r.status === 'pending' || r.status === 'in_progress' || r.status === 'contacted' || r.status === 'assigned') && <>
                  <TouchableOpacity style={[styles.actionBtn, { backgroundColor: Colors.success + '15' }]} onPress={() => { if (editingId !== r.id) { setEditingId(r.id); } else { updateStatus(r.id, 'resolved'); } }}>
                    <Text style={[styles.actionText, { color: Colors.success }]}>{t('resolved')}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity style={[styles.actionBtn, { backgroundColor: Colors.error + '15' }]} onPress={() => updateStatus(r.id, 'no_response')}>
                    <Text style={[styles.actionText, { color: Colors.error }]}>No Response</Text>
                  </TouchableOpacity>
                </>}
                {editingId !== r.id && <TouchableOpacity style={[styles.actionBtn, { backgroundColor: Colors.gold + '15' }]} onPress={() => setEditingId(r.id)}>
                  <Ionicons name="create" size={14} color={Colors.gold} /><Text style={[styles.actionText, { color: Colors.gold }]}>Notes</Text>
                </TouchableOpacity>}
              </View>
            </View>
          ))}
          {requests.length === 0 && <Text style={styles.emptyText}>No requests found</Text>}
          <View style={{ height: 40 }} />
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md },
  backBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: Colors.surface, alignItems: 'center', justifyContent: 'center' },
  headerTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text },
  statsRow: { flexDirection: 'row', paddingHorizontal: Spacing.lg, gap: 10, marginBottom: Spacing.md },
  statCard: { flex: 1, alignItems: 'center', paddingVertical: 12, backgroundColor: Colors.card, borderRadius: 12, borderWidth: 1 },
  statNum: { fontSize: FontSize.xl, fontWeight: '700' },
  statLabel: { fontSize: FontSize.xs, color: Colors.textMuted, marginTop: 2 },
  filterRow: { paddingHorizontal: Spacing.lg, gap: 6, paddingBottom: Spacing.sm },
  chip: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 16, backgroundColor: Colors.surface, borderWidth: 1, borderColor: Colors.border },
  chipActive: { backgroundColor: Colors.gold + '15', borderColor: Colors.gold },
  chipText: { fontSize: FontSize.xs, color: Colors.textMuted, fontWeight: '500', textTransform: 'capitalize' },
  chipTextActive: { color: Colors.gold },
  listContent: { paddingHorizontal: Spacing.lg, paddingTop: Spacing.sm },
  requestCard: { backgroundColor: Colors.card, borderRadius: 14, marginBottom: Spacing.md, overflow: 'hidden', borderWidth: 1, borderColor: Colors.cardBorder },
  reqHeader: { padding: Spacing.md },
  reqTypeRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  typeIcon: { width: 36, height: 36, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  reqType: { fontSize: FontSize.md, fontWeight: '600', color: Colors.text, textTransform: 'capitalize' },
  reqTime: { fontSize: FontSize.xs, color: Colors.textMuted },
  statusBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6 },
  statusText: { fontSize: FontSize.xs, fontWeight: '600', textTransform: 'capitalize' },
  customerInfo: { paddingHorizontal: Spacing.md, paddingBottom: Spacing.sm, gap: 6 },
  infoRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  infoText: { fontSize: FontSize.sm, color: Colors.textSecondary },
  noteBox: { paddingHorizontal: Spacing.md, marginBottom: Spacing.sm },
  noteInput: { backgroundColor: Colors.surface, borderRadius: 10, padding: 12, fontSize: FontSize.sm, color: Colors.text, borderWidth: 1, borderColor: Colors.border, minHeight: 60, textAlignVertical: 'top' },
  actionsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, paddingHorizontal: Spacing.md, paddingBottom: Spacing.md },
  actionBtn: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8 },
  actionText: { fontSize: FontSize.xs, fontWeight: '600' },
  emptyText: { fontSize: FontSize.md, color: Colors.textMuted, textAlign: 'center', marginTop: 60 },
});
