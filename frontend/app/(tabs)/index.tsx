import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Image, RefreshControl, FlatList, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../../src/theme';
import { api } from '../../src/api';
import { useAuth } from '../../src/context/AuthContext';
import { getImageUrl } from '../../src/api';

interface Rate { silver_dollar_rate: number; silver_mcx_rate: number; silver_physical_rate: number; gold_dollar_rate: number; gold_mcx_rate: number; gold_physical_rate: number; silver_movement: string; gold_movement: string; market_summary: string; silver_physical_premium: number; gold_physical_premium: number; silver_rate?: number; gold_rate?: number; created_at?: string; }
interface Story { id: string; title: string; image_url: string; category: string; }
interface Product { id: string; title: string; images: string[]; metal_type: string; category: string; approx_weight: string; stock_status: string; is_new_arrival: boolean; is_trending: boolean; }

const QuickAction = ({ icon, label, color, onPress, testID }: any) => (
  <TouchableOpacity testID={testID} style={styles.quickAction} onPress={onPress}>
    <View style={[styles.quickIcon, { backgroundColor: color + '15' }]}>
      <Ionicons name={icon} size={22} color={color} />
    </View>
    <Text style={styles.quickLabel} numberOfLines={1}>{label}</Text>
  </TouchableOpacity>
);

const StoryItem = ({ story }: { story: Story }) => (
  <View style={styles.storyItem}>
    <View style={styles.storyRing}>
      <Image source={{ uri: story.image_url }} style={styles.storyImage} />
    </View>
    <Text style={styles.storyTitle} numberOfLines={1}>{story.title}</Text>
  </View>
);

const ProductCard = ({ item, onPress }: { item: Product; onPress: () => void }) => (
  <TouchableOpacity testID={`product-card-${item.id}`} style={styles.productCard} onPress={onPress} activeOpacity={0.8}>
    <Image source={{ uri: getImageUrl(item, true) }} style={styles.productImage} />
    <View style={styles.productInfo}>
      <View style={styles.productBadges}>
        <View style={[styles.badge, { backgroundColor: item.metal_type === 'gold' ? '#D4AF3720' : item.metal_type === 'diamond' ? '#3B82F620' : '#E0E0E020' }]}>
          <Text style={[styles.badgeText, { color: item.metal_type === 'gold' ? Colors.gold : item.metal_type === 'diamond' ? Colors.info : Colors.silver }]}>
            {item.metal_type.toUpperCase()}
          </Text>
        </View>
        {item.is_new_arrival && <View style={[styles.badge, { backgroundColor: '#10B98120' }]}><Text style={[styles.badgeText, { color: Colors.success }]}>NEW</Text></View>}
        {item.is_trending && <View style={[styles.badge, { backgroundColor: '#F59E0B20' }]}><Text style={[styles.badgeText, { color: Colors.warning }]}>TRENDING</Text></View>}
      </View>
      <Text style={styles.productTitle} numberOfLines={2}>{item.title}</Text>
      <Text style={styles.productMeta}>{item.category?.replace(/_/g, ' ')} • {item.approx_weight}</Text>
      <View style={styles.productActions}>
        <TouchableOpacity style={styles.askPriceBtn} onPress={() => router.push({ pathname: '/request-call', params: { type: 'ask_price', productId: item.id } })}><Text style={styles.askPriceText}>Ask Price</Text></TouchableOpacity>
        <TouchableOpacity style={styles.iconBtn} onPress={async () => { try { await api.post(`/wishlist/toggle?product_id=${item.id}`); } catch {} }}><Ionicons name="heart-outline" size={18} color={Colors.textSecondary} /></TouchableOpacity>
      </View>
    </View>
  </TouchableOpacity>
);

export default function HomeScreen() {
  const { user } = useAuth();
  const router = useRouter();
  const [rates, setRates] = useState<Rate | null>(null);
  const [stories, setStories] = useState<Story[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    try {
      const [rateRes, storyRes, prodRes] = await Promise.all([
        api.get('/rates/latest'),
        api.get('/stories'),
        api.get('/products?limit=10'),
      ]);
      setRates(rateRes);
      setStories(storyRes.stories || []);
      setProducts(prodRes.products || []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { loadData(); }, []);

  const onRefresh = () => { setRefreshing(true); loadData(); };
  const movementIcon = (m: string) => m === 'up' ? 'trending-up' : m === 'down' ? 'trending-down' : 'remove';
  const movementColor = (m: string) => m === 'up' ? Colors.success : m === 'down' ? Colors.error : Colors.textSecondary;

  if (loading) return <View style={styles.loader}><ActivityIndicator size="large" color={Colors.gold} /></View>;

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={Colors.gold} />} showsVerticalScrollIndicator={false}>
        {/* Header */}
        <View style={styles.header}>
          <View>
            <Text style={styles.greeting}>Welcome back,</Text>
            <Text style={styles.userName}>{user?.name || 'Jeweller'}</Text>
          </View>
          <View style={styles.headerRight}>
            <TouchableOpacity testID="notifications-btn" style={styles.headerIcon}>
              <Ionicons name="notifications-outline" size={22} color={Colors.text} />
              <View style={styles.notifDot} />
            </TouchableOpacity>
          </View>
        </View>

        {/* Rate Ticker - 3 rates each */}
        {rates && (
          <View testID="rate-ticker" style={styles.rateCard}>
            {/* Silver */}
            <View style={styles.metalSection}>
              <View style={styles.metalHeader}>
                <Text style={styles.rateLabel}>SILVER</Text>
                <Ionicons name={movementIcon(rates.silver_movement)} size={14} color={movementColor(rates.silver_movement)} />
              </View>
              <View style={styles.threeRates}>
                <View style={styles.rateCell}><Text style={styles.rateCellLabel}>Dollar</Text><Text style={styles.rateCellValue}>${rates.silver_dollar_rate?.toFixed(2)}</Text></View>
                <View style={styles.rateCellDivider} />
                <View style={styles.rateCell}><Text style={styles.rateCellLabel}>MCX</Text><Text style={styles.rateCellValue}>₹{rates.silver_mcx_rate?.toFixed(2)}</Text></View>
                <View style={styles.rateCellDivider} />
                <View style={styles.rateCell}><Text style={[styles.rateCellLabel, { color: Colors.gold }]}>Physical</Text><Text style={[styles.rateCellValue, { color: Colors.gold }]}>₹{rates.silver_physical_rate?.toFixed(2)}</Text></View>
              </View>
            </View>
            <View style={styles.metalDivider} />
            {/* Gold */}
            <View style={styles.metalSection}>
              <View style={styles.metalHeader}>
                <Text style={styles.rateLabel}>GOLD</Text>
                <Ionicons name={movementIcon(rates.gold_movement)} size={14} color={movementColor(rates.gold_movement)} />
              </View>
              <View style={styles.threeRates}>
                <View style={styles.rateCell}><Text style={styles.rateCellLabel}>Dollar</Text><Text style={styles.rateCellValue}>${rates.gold_dollar_rate?.toFixed(0)}</Text></View>
                <View style={styles.rateCellDivider} />
                <View style={styles.rateCell}><Text style={styles.rateCellLabel}>MCX</Text><Text style={styles.rateCellValue}>₹{rates.gold_mcx_rate?.toFixed(0)}</Text></View>
                <View style={styles.rateCellDivider} />
                <View style={styles.rateCell}><Text style={[styles.rateCellLabel, { color: Colors.gold }]}>Physical</Text><Text style={[styles.rateCellValue, { color: Colors.gold }]}>₹{rates.gold_physical_rate?.toFixed(0)}</Text></View>
              </View>
            </View>
            {rates.market_summary ? <Text style={styles.marketSummary}>{rates.market_summary}</Text> : null}
            {rates.created_at ? <Text style={styles.rateTime}>Updated: {new Date(rates.created_at).toLocaleTimeString()}</Text> : null}
          </View>
        )}

        {/* Quick Actions */}
        <View style={styles.quickActions}>
          <QuickAction testID="calc-quick-btn" icon="calculator" label="Calculator" color={Colors.gold} onPress={() => router.push('/(tabs)/calculator')} />
          <QuickAction testID="call-quick-btn" icon="call" label="Request Call" color={Colors.success} onPress={() => router.push('/request-call')} />
          <QuickAction testID="video-quick-btn" icon="videocam" label="Video Call" color={Colors.info} onPress={() => router.push({ pathname: '/request-call', params: { type: 'video_call' } })} />
          <QuickAction testID="rewards-quick-btn" icon="gift" label="My Rewards" color={Colors.warning} onPress={() => router.push('/rewards')} />
          <QuickAction testID="ai-quick-btn" icon="sparkles" label="AI Assistant" color="#A855F7" onPress={() => router.push('/ai-assistant')} />
          <QuickAction testID="knowledge-quick-btn" icon="book" label="Silver Guide" color={Colors.silver} onPress={() => router.push('/knowledge')} />
        </View>

        {/* Stories */}
        {stories.length > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>HIGHLIGHTS</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.storiesRow}>
              {stories.map(s => <StoryItem key={s.id} story={s} />)}
            </ScrollView>
          </View>
        )}

        {/* Feed Preview */}
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>LATEST COLLECTION</Text>
            <TouchableOpacity testID="see-all-btn" onPress={() => router.push('/(tabs)/feed')}>
              <Text style={styles.seeAll}>See All</Text>
            </TouchableOpacity>
          </View>
          {products.map(p => (
            <ProductCard key={p.id} item={p} onPress={() => router.push({ pathname: '/product/[id]', params: { id: p.id } })} />
          ))}
        </View>

        <View style={{ height: 24 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  loader: { flex: 1, backgroundColor: Colors.background, justifyContent: 'center', alignItems: 'center' },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: Spacing.lg, paddingTop: Spacing.md, paddingBottom: Spacing.sm },
  greeting: { fontSize: FontSize.sm, color: Colors.textSecondary },
  userName: { fontSize: FontSize.xl, fontWeight: '700', color: Colors.text },
  headerRight: { flexDirection: 'row', gap: 8 },
  headerIcon: { width: 40, height: 40, borderRadius: 20, backgroundColor: Colors.surface, alignItems: 'center', justifyContent: 'center' },
  notifDot: { position: 'absolute', top: 8, right: 8, width: 8, height: 8, borderRadius: 4, backgroundColor: Colors.error },
  rateCard: { marginHorizontal: Spacing.lg, marginTop: Spacing.md, backgroundColor: Colors.card, borderRadius: 16, padding: Spacing.md, borderWidth: 1, borderColor: Colors.borderGold },
  metalSection: { paddingVertical: 8 },
  metalHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, marginBottom: 8 },
  rateLabel: { fontSize: FontSize.xs, color: Colors.textSecondary, letterSpacing: 2, fontWeight: '600' },
  threeRates: { flexDirection: 'row', alignItems: 'center' },
  rateCell: { flex: 1, alignItems: 'center' },
  rateCellLabel: { fontSize: 9, color: Colors.textMuted, letterSpacing: 1, fontWeight: '500', marginBottom: 2 },
  rateCellValue: { fontSize: FontSize.md, fontWeight: '700', color: Colors.text },
  rateCellDivider: { width: 1, height: 28, backgroundColor: Colors.border },
  metalDivider: { height: 1, backgroundColor: Colors.border, marginVertical: 4 },
  marketSummary: { fontSize: FontSize.xs, color: Colors.textSecondary, textAlign: 'center', marginTop: Spacing.sm, fontStyle: 'italic' },
  rateTime: { fontSize: 9, color: Colors.textMuted, textAlign: 'center', marginTop: 4 },
  quickActions: { flexDirection: 'row', flexWrap: 'wrap', paddingHorizontal: Spacing.md, marginTop: Spacing.lg, gap: 4 },
  quickAction: { width: '30%', alignItems: 'center', paddingVertical: Spacing.sm, marginBottom: Spacing.sm },
  quickIcon: { width: 48, height: 48, borderRadius: 14, alignItems: 'center', justifyContent: 'center', marginBottom: 6 },
  quickLabel: { fontSize: FontSize.xs, color: Colors.textSecondary, fontWeight: '500' },
  section: { marginTop: Spacing.lg, paddingHorizontal: Spacing.lg },
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: Spacing.md },
  sectionTitle: { fontSize: FontSize.xs, color: Colors.textSecondary, letterSpacing: 2, fontWeight: '700' },
  seeAll: { fontSize: FontSize.sm, color: Colors.gold, fontWeight: '600' },
  storiesRow: { gap: 16, paddingVertical: Spacing.sm },
  storyItem: { alignItems: 'center', width: 72 },
  storyRing: { width: 64, height: 64, borderRadius: 32, borderWidth: 2, borderColor: Colors.gold, padding: 2, marginBottom: 6 },
  storyImage: { width: '100%', height: '100%', borderRadius: 30 },
  storyTitle: { fontSize: 9, color: Colors.textSecondary, textAlign: 'center' },
  productCard: { backgroundColor: Colors.card, borderRadius: 16, marginBottom: Spacing.md, overflow: 'hidden', borderWidth: 1, borderColor: Colors.cardBorder },
  productImage: { width: '100%', height: 220, backgroundColor: Colors.surface },
  productInfo: { padding: Spacing.md },
  productBadges: { flexDirection: 'row', gap: 6, marginBottom: Spacing.sm },
  badge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 },
  badgeText: { fontSize: 9, fontWeight: '700', letterSpacing: 1 },
  productTitle: { fontSize: FontSize.base, fontWeight: '600', color: Colors.text, marginBottom: 4 },
  productMeta: { fontSize: FontSize.sm, color: Colors.textSecondary, marginBottom: Spacing.sm, textTransform: 'capitalize' },
  productActions: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  askPriceBtn: { backgroundColor: Colors.gold, paddingHorizontal: 16, paddingVertical: 8, borderRadius: 8 },
  askPriceText: { fontSize: FontSize.sm, fontWeight: '700', color: '#000' },
  iconBtn: { width: 36, height: 36, borderRadius: 18, backgroundColor: Colors.surface, alignItems: 'center', justifyContent: 'center' },
});
