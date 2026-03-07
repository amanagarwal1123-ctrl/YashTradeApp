import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api } from '../src/api';

const STATUS_COLOR: Record<string, string> = {
  pending: Colors.warning,
  in_progress: Colors.info,
  contacted: '#A855F7',
  resolved: Colors.success,
  no_response: Colors.error,
};

export default function MyRequestsScreen() {
  const router = useRouter();
  const [requests, setRequests] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get('/requests/my');
        setRequests(res.requests || []);
      } catch {}
      finally { setLoading(false); }
    })();
  }, []);

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

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity testID="myrequests-back" onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color={Colors.text} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>My Requests</Text>
        <View style={{ width: 44 }} />
      </View>

      {loading ? (
        <ActivityIndicator color={Colors.gold} style={{ marginTop: 40 }} />
      ) : (
        <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
          {requests.length === 0 && (
            <View style={styles.empty}>
              <Ionicons name="receipt-outline" size={48} color={Colors.textMuted} />
              <Text style={styles.emptyText}>No requests yet</Text>
            </View>
          )}
          {requests.map(r => {
            const color = STATUS_COLOR[r.status] || Colors.textMuted;
            return (
              <View key={r.id} style={styles.card} testID={`request-${r.id}`}>
                <View style={styles.cardTop}>
                  <View style={[styles.iconCircle, { backgroundColor: color + '15' }]}>
                    <Ionicons name={typeIcon(r.request_type) as any} size={18} color={color} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.cardType}>{r.request_type?.replace(/_/g, ' ')}</Text>
                    <Text style={styles.cardDate}>{new Date(r.created_at).toLocaleString()}</Text>
                  </View>
                  <View style={[styles.statusBadge, { backgroundColor: color + '20' }]}>
                    <Text style={[styles.statusText, { color }]}>{r.status?.replace(/_/g, ' ')}</Text>
                  </View>
                </View>
                {r.category ? <Text style={styles.cardMeta}>Category: {r.category}</Text> : null}
                {r.notes ? <Text style={styles.cardMeta}>Note: {r.notes}</Text> : null}
                {r.admin_notes ? (
                  <View style={styles.adminNote}>
                    <Ionicons name="chatbox" size={12} color={Colors.gold} />
                    <Text style={styles.adminNoteText}>{r.admin_notes}</Text>
                  </View>
                ) : null}
              </View>
            );
          })}
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
  content: { paddingHorizontal: Spacing.lg },
  empty: { alignItems: 'center', paddingVertical: 60 },
  emptyText: { fontSize: FontSize.md, color: Colors.textMuted, marginTop: Spacing.md },
  card: { backgroundColor: Colors.card, borderRadius: 14, padding: Spacing.md, marginBottom: Spacing.sm, borderWidth: 1, borderColor: Colors.cardBorder },
  cardTop: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  iconCircle: { width: 36, height: 36, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  cardType: { fontSize: FontSize.md, fontWeight: '600', color: Colors.text, textTransform: 'capitalize' },
  cardDate: { fontSize: FontSize.xs, color: Colors.textMuted },
  statusBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6 },
  statusText: { fontSize: FontSize.xs, fontWeight: '600', textTransform: 'capitalize' },
  cardMeta: { fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: 6, textTransform: 'capitalize' },
  adminNote: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 8, backgroundColor: Colors.gold + '10', padding: 8, borderRadius: 8 },
  adminNoteText: { fontSize: FontSize.sm, color: Colors.gold, flex: 1 },
});
