import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator, RefreshControl } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api } from '../src/api';
import { useLang } from '../src/context/LanguageContext';

const T: Record<string, any> = {
  en: { title: 'My Orders', empty: 'No orders yet', emptyHint: 'Submit your cart selection to place an order', browse: 'Browse Collection', items: 'items', error: 'Could not load your orders. Please check your connection.', retry: 'Retry', notes: 'Notes' },
  hi: { title: 'मेरे ऑर्डर', empty: 'अभी कोई ऑर्डर नहीं', emptyHint: 'ऑर्डर देने के लिए अपना कार्ट चयन सबमिट करें', browse: 'संग्रह देखें', items: 'आइटम', error: 'ऑर्डर लोड नहीं हो सके। कृपया अपना कनेक्शन जांचें।', retry: 'फिर से कोशिश करें', notes: 'नोट्स' },
  pa: { title: 'ਮੇਰੇ ਆਰਡਰ', empty: 'ਹਾਲੇ ਕੋਈ ਆਰਡਰ ਨਹੀਂ', emptyHint: 'ਆਰਡਰ ਦੇਣ ਲਈ ਆਪਣੀ ਕਾਰਟ ਚੋਣ ਸਬਮਿਟ ਕਰੋ', browse: 'ਸੰਗ੍ਰਹਿ ਵੇਖੋ', items: 'ਆਈਟਮਾਂ', error: 'ਆਰਡਰ ਲੋਡ ਨਹੀਂ ਹੋ ਸਕੇ। ਕਿਰਪਾ ਕਰਕੇ ਕਨੈਕਸ਼ਨ ਚੈੱਕ ਕਰੋ।', retry: 'ਮੁੜ ਕੋਸ਼ਿਸ਼ ਕਰੋ', notes: 'ਨੋਟਸ' },
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

export default function MyOrdersScreen() {
  const router = useRouter();
  const { language } = useLang();
  const t = T[language] || T.en;
  const [orders, setOrders] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState(false);

  const loadOrders = useCallback(async () => {
    try {
      setLoadError(false);
      const res = await api.get('/cart/orders');
      setOrders(res.orders || []);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { loadOrders(); }, [loadOrders]);
  const onRefresh = () => { setRefreshing(true); loadOrders(); };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity testID="myorders-back" onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color={Colors.text} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>{t.title}</Text>
        <View style={{ width: 44 }} />
      </View>

      {loading ? (
        <ActivityIndicator color={Colors.gold} style={{ marginTop: 40 }} />
      ) : loadError ? (
        <View style={styles.empty}>
          <Ionicons name="cloud-offline-outline" size={48} color={Colors.error} />
          <Text style={[styles.emptyText, { color: Colors.error }]}>{t.error}</Text>
          <TouchableOpacity testID="myorders-retry" style={styles.browseBtn} onPress={() => { setLoading(true); loadOrders(); }}>
            <Text style={styles.browseBtnText}>{t.retry}</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={styles.content}
          showsVerticalScrollIndicator={false}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={Colors.gold} />}
        >
          {orders.length === 0 && (
            <View style={styles.empty}>
              <Ionicons name="bag-check-outline" size={48} color={Colors.textMuted} />
              <Text style={styles.emptyText}>{t.empty}</Text>
              <Text style={styles.emptyHint}>{t.emptyHint}</Text>
              <TouchableOpacity style={styles.browseBtn} onPress={() => router.push('/(tabs)/feed')}>
                <Text style={styles.browseBtnText}>{t.browse}</Text>
              </TouchableOpacity>
            </View>
          )}

          {orders.map((o: any) => (
            <View key={o.id} style={styles.orderCard} testID={`order-${o.id}`}>
              <View style={styles.orderTop}>
                <View style={styles.orderIcon}>
                  <Ionicons name="bag-check" size={18} color={Colors.gold} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.orderTitle}>{o.item_count || 0} {t.items}</Text>
                  <Text style={styles.orderDate}>
                    {new Date(o.created_at).toLocaleDateString()} {new Date(o.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </Text>
                </View>
                <View style={[styles.statusBadge, { backgroundColor: statusColor(o.status) + '20' }]}>
                  <Text style={[styles.statusText, { color: statusColor(o.status) }]}>{(o.status || 'pending').replace(/_/g, ' ')}</Text>
                </View>
              </View>
              {(o.items || []).length > 0 && (
                <View style={styles.itemsList}>
                  {o.items.map((it: any, idx: number) => (
                    <View key={`${o.id}-${idx}`} style={styles.itemRow}>
                      <Ionicons name="ellipse" size={5} color={Colors.textMuted} />
                      <Text style={styles.itemText} numberOfLines={1}>
                        {it.title || 'Product'}{it.metal_type ? ` • ${it.metal_type}` : ''} • Qty: {it.quantity || 1}
                      </Text>
                    </View>
                  ))}
                </View>
              )}
              {o.notes ? <Text style={styles.orderNotes}>{t.notes}: {o.notes}</Text> : null}
            </View>
          ))}
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
  empty: { alignItems: 'center', paddingVertical: 60, paddingHorizontal: Spacing.lg },
  emptyText: { fontSize: FontSize.md, color: Colors.textMuted, marginTop: Spacing.md, textAlign: 'center' },
  emptyHint: { fontSize: FontSize.sm, color: Colors.textMuted, marginTop: 4, textAlign: 'center' },
  browseBtn: { marginTop: Spacing.lg, backgroundColor: Colors.gold, paddingHorizontal: 24, paddingVertical: 12, borderRadius: 10 },
  browseBtnText: { fontSize: FontSize.sm, fontWeight: '700', color: '#000' },
  orderCard: { backgroundColor: Colors.card, borderRadius: 14, padding: Spacing.md, marginBottom: Spacing.sm, borderWidth: 1, borderColor: Colors.cardBorder },
  orderTop: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  orderIcon: { width: 36, height: 36, borderRadius: 10, backgroundColor: Colors.gold + '15', alignItems: 'center', justifyContent: 'center' },
  orderTitle: { fontSize: FontSize.md, fontWeight: '600', color: Colors.text },
  orderDate: { fontSize: FontSize.xs, color: Colors.textMuted, marginTop: 1 },
  statusBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6 },
  statusText: { fontSize: FontSize.xs, fontWeight: '600', textTransform: 'capitalize' },
  itemsList: { marginTop: Spacing.sm, gap: 4, paddingLeft: 4 },
  itemRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  itemText: { flex: 1, fontSize: FontSize.sm, color: Colors.textSecondary, textTransform: 'capitalize' },
  orderNotes: { fontSize: FontSize.xs, color: Colors.textMuted, marginTop: Spacing.sm, fontStyle: 'italic' },
});
