import React, { useEffect, useState, useCallback, useRef } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Image, RefreshControl, ActivityIndicator, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../../src/theme';
import { api, getImageUrl } from '../../src/api';
import { useAuth } from '../../src/context/AuthContext';
import { useLang } from '../../src/context/LanguageContext';

interface Rate { silver_dollar_rate: number; silver_mcx_rate: number; silver_physical_rate: number; gold_dollar_rate: number; gold_mcx_rate: number; gold_physical_rate: number; silver_movement: string; gold_movement: string; market_summary: string; created_at?: string; }
interface Story { id: string; title: string; image_url: string; category: string; link_type: string; link_id: string; }
interface Product { id: string; title: string; images: string[]; metal_type: string; category: string; approx_weight: string; is_new_arrival: boolean; is_trending: boolean; storage_path?: string; thumbnail_path?: string; }

const QuickAction = ({ icon, label, color, onPress, testID }: any) => (
  <TouchableOpacity testID={testID} style={styles.quickAction} onPress={onPress}>
    <View style={[styles.quickIcon, { backgroundColor: color + '15' }]}>
      <Ionicons name={icon} size={20} color={color} />
    </View>
    <Text style={styles.quickLabel} numberOfLines={1}>{label}</Text>
  </TouchableOpacity>
);

export default function HomeScreen() {
  const { user } = useAuth();
  const { language } = useLang();
  const router = useRouter();
  const [rates, setRates] = useState<Rate | null>(null);
  const [liveRates, setLiveRates] = useState<any>(null);
  const [stories, setStories] = useState<Story[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [allProducts, setAllProducts] = useState<Product[]>([]);
  const [displayProducts, setDisplayProducts] = useState<Product[]>([]);
  const [cartCount, setCartCount] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [feedPage, setFeedPage] = useState(1);
  const rateTimer = useRef<NodeJS.Timeout | null>(null);

  const T: Record<string, any> = {
    en: { welcome: 'Welcome back,', highlights: 'HIGHLIGHTS', latest: 'LATEST COLLECTION', seeAll: 'See All', askPrice: 'Ask Price', calc: 'Calculator', call: 'Request Call', video: 'Video Call', rewards: 'My Rewards', ai: 'AI Assistant', guide: 'Silver Guide', rateList: 'Rate List', schemes: 'Schemes', brands: 'Brands', showroom: 'Showroom', exhibition: 'Exhibition', live: 'LIVE' },
    hi: { welcome: 'वापस स्वागत है,', highlights: 'हाइलाइट्स', latest: 'नवीनतम संग्रह', seeAll: 'सभी देखें', askPrice: 'कीमत पूछें', calc: 'कैलकुलेटर', call: 'कॉल अनुरोध', video: 'वीडियो कॉल', rewards: 'मेरे रिवॉर्ड्स', ai: 'AI सहायक', guide: 'चांदी गाइड', rateList: 'रेट लिस्ट', schemes: 'स्कीम्स', brands: 'ब्रांड', showroom: 'शोरूम', exhibition: 'प्रदर्शनी', live: 'लाइव' },
    pa: { welcome: 'ਵਾਪਸ ਸਵਾਗਤ ਹੈ,', highlights: 'ਹਾਈਲਾਈਟਸ', latest: 'ਨਵੀਨਤਮ ਸੰਗ੍ਰਹਿ', seeAll: 'ਸਭ ਵੇਖੋ', askPrice: 'ਕੀਮਤ ਪੁੱਛੋ', calc: 'ਕੈਲਕੁਲੇਟਰ', call: 'ਕਾਲ ਬੇਨਤੀ', video: 'ਵੀਡੀਓ ਕਾਲ', rewards: 'ਮੇਰੇ ਇਨਾਮ', ai: 'AI ਸਹਾਇਕ', guide: 'ਚਾਂਦੀ ਗਾਈਡ', rateList: 'ਰੇਟ ਲਿਸਟ', schemes: 'ਸਕੀਮਾਂ', brands: 'ਬ੍ਰਾਂਡ', showroom: 'ਸ਼ੋਅਰੂਮ', exhibition: 'ਪ੍ਰਦਰਸ਼ਨੀ', live: 'ਲਾਈਵ' },
  };
  const t = T[language] || T.en;

  const loadData = useCallback(async () => {
    try {
      const [rateRes, storyRes, prodRes, cartRes, liveRes] = await Promise.all([
        api.get('/rates/latest'),
        api.get('/stories'),
        api.get('/products?limit=100000'),
        api.get('/cart/count').catch(() => ({ count: 0 })),
        api.get('/live-rates').catch(() => null),
      ]);
      setRates(rateRes);
      setStories(storyRes.stories || []);
      const prods = prodRes.products || [];
      setAllProducts(prods);
      setProducts(prods.slice(0, 10));
      setDisplayProducts(prods.slice(0, 10));
      setCartCount(cartRes.count || 0);
      if (liveRes) setLiveRates(liveRes);
      setFeedPage(1);
    } catch (e) { console.error(e); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  // Auto-refresh live rates every 60 seconds
  useEffect(() => {
    loadData();
    rateTimer.current = setInterval(async () => {
      try {
        const [rateRes, liveRes] = await Promise.all([
          api.get('/rates/latest'),
          api.get('/live-rates').catch(() => null),
        ]);
        setRates(rateRes);
        if (liveRes) setLiveRates(liveRes);
      } catch {}
    }, 60000);
    return () => { if (rateTimer.current) clearInterval(rateTimer.current); };
  }, []);

  const onRefresh = () => { setRefreshing(true); loadData(); };
  const movementIcon = (m: string) => m === 'up' ? 'trending-up' : m === 'down' ? 'trending-down' : 'remove';
  const movementColor = (m: string) => m === 'up' ? Colors.success : m === 'down' ? Colors.error : Colors.textSecondary;

  // Endless feed: when user scrolls near bottom, load more (cycling through products)
  const loadMoreProducts = () => {
    if (allProducts.length === 0) return;
    const nextPage = feedPage + 1;
    const startIdx = (nextPage - 1) * 10;
    // Cycle through products endlessly
    const newItems = [];
    for (let i = 0; i < 10; i++) {
      const idx = (startIdx + i) % allProducts.length;
      newItems.push({ ...allProducts[idx], _key: `${nextPage}-${i}-${allProducts[idx].id}` });
    }
    setDisplayProducts(prev => [...prev, ...newItems]);
    setFeedPage(nextPage);
  };

  const handleStoryPress = (story: Story) => {
    if (story.link_type === 'category' && story.link_id) {
      router.push({ pathname: '/(tabs)/feed', params: { category: story.link_id } });
    } else if (story.link_type === 'request') {
      router.push({ pathname: '/request-call', params: { type: story.link_id || 'video_call' } });
    } else {
      router.push('/(tabs)/feed');
    }
  };

  const addToCart = async (productId: string) => {
    try {
      await api.post('/cart/add', { product_id: productId });
      setCartCount(prev => prev + 1);
    } catch {}
  };

  const handleScroll = (event: any) => {
    const { layoutMeasurement, contentOffset, contentSize } = event.nativeEvent;
    const isCloseToBottom = layoutMeasurement.height + contentOffset.y >= contentSize.height - 400;
    if (isCloseToBottom) {
      loadMoreProducts();
    }
  };

  if (loading) return <View style={styles.loader}><ActivityIndicator size="large" color={Colors.gold} /></View>;

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={Colors.gold} />}
        showsVerticalScrollIndicator={false}
        onScroll={handleScroll}
        scrollEventThrottle={400}
      >
        {/* Header */}
        <View style={styles.header}>
          <View>
            <Text style={styles.greeting}>{t.welcome}</Text>
            <Text style={styles.userName}>{user?.name || 'Jeweller'}</Text>
          </View>
          <View style={styles.headerRight}>
            <TouchableOpacity testID="cart-btn" onPress={() => router.push('/cart')} style={styles.headerIcon}>
              <Ionicons name="cart-outline" size={22} color={Colors.text} />
              {cartCount > 0 && <View style={styles.cartBadge}><Text style={styles.cartBadgeText}>{cartCount}</Text></View>}
            </TouchableOpacity>
            <TouchableOpacity testID="notifications-btn" style={styles.headerIcon}>
              <Ionicons name="notifications-outline" size={22} color={Colors.text} />
            </TouchableOpacity>
          </View>
        </View>

        {/* Rate Ticker */}
        {rates && (
          <View testID="rate-ticker" style={styles.rateCard}>
            {/* Live indicator */}
            {liveRates && liveRates.fetched_at && (
              <View style={styles.liveIndicator}>
                <View style={styles.liveDot} />
                <Text style={styles.liveText}>{t.live}</Text>
              </View>
            )}
            <View style={styles.metalSection}>
              <View style={styles.metalHeader}><Text style={styles.rateLabel}>SILVER</Text><Ionicons name={movementIcon(rates.silver_movement)} size={14} color={movementColor(rates.silver_movement)} /></View>
              <View style={styles.threeRates}>
                <View style={styles.rateCell}><Text style={styles.rateCellLabel}>Dollar</Text><Text style={styles.rateCellValue}>${rates.silver_dollar_rate?.toFixed(2)}</Text></View>
                <View style={styles.rateCellDivider} />
                <View style={styles.rateCell}><Text style={styles.rateCellLabel}>MCX</Text><Text style={styles.rateCellValue}>₹{rates.silver_mcx_rate?.toFixed(2)}</Text></View>
                <View style={styles.rateCellDivider} />
                <View style={styles.rateCell}><Text style={[styles.rateCellLabel, { color: Colors.gold }]}>Physical</Text><Text style={[styles.rateCellValue, { color: Colors.gold }]}>₹{rates.silver_physical_rate?.toFixed(2)}</Text></View>
              </View>
            </View>
            <View style={styles.metalDivider} />
            <View style={styles.metalSection}>
              <View style={styles.metalHeader}><Text style={styles.rateLabel}>GOLD</Text><Ionicons name={movementIcon(rates.gold_movement)} size={14} color={movementColor(rates.gold_movement)} /></View>
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
          <QuickAction testID="calc-quick-btn" icon="calculator" label={t.calc} color={Colors.gold} onPress={() => router.push('/(tabs)/calculator')} />
          <QuickAction testID="call-quick-btn" icon="call" label={t.call} color={Colors.success} onPress={() => router.push('/request-call')} />
          <QuickAction testID="video-quick-btn" icon="videocam" label={t.video} color={Colors.info} onPress={() => router.push({ pathname: '/request-call', params: { type: 'video_call' } })} />
          <QuickAction testID="ratelist-quick-btn" icon="list" label={t.rateList} color="#E91E63" onPress={() => router.push('/rate-list')} />
          <QuickAction testID="schemes-quick-btn" icon="ribbon" label={t.schemes} color="#FF9800" onPress={() => router.push('/schemes')} />
          <QuickAction testID="brands-quick-btn" icon="star" label={t.brands} color="#9C27B0" onPress={() => router.push('/brands')} />
          <QuickAction testID="showroom-quick-btn" icon="images" label={t.showroom} color="#00BCD4" onPress={() => router.push('/showroom')} />
          <QuickAction testID="exhibition-quick-btn" icon="calendar" label={t.exhibition} color="#795548" onPress={() => router.push('/exhibition')} />
          <QuickAction testID="rewards-quick-btn" icon="gift" label={t.rewards} color={Colors.warning} onPress={() => router.push('/rewards')} />
          <QuickAction testID="ai-quick-btn" icon="sparkles" label={t.ai} color="#A855F7" onPress={() => router.push('/ai-assistant')} />
          <QuickAction testID="knowledge-quick-btn" icon="book" label={t.guide} color={Colors.silver} onPress={() => router.push('/knowledge')} />
        </View>

        {/* Stories */}
        {stories.length > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>{t.highlights}</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.storiesRow}>
              {stories.map(s => (
                <TouchableOpacity key={s.id} testID={`story-${s.id}`} onPress={() => handleStoryPress(s)} activeOpacity={0.7}>
                  <View style={styles.storyItem}>
                    <View style={styles.storyRing}><Image source={{ uri: s.image_url }} style={styles.storyImage} /></View>
                    <Text style={styles.storyTitle} numberOfLines={1}>{s.title}</Text>
                  </View>
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>
        )}

        {/* Endless Feed */}
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>{t.latest}</Text>
            <TouchableOpacity testID="see-all-btn" onPress={() => router.push('/(tabs)/feed')}><Text style={styles.seeAll}>{t.seeAll}</Text></TouchableOpacity>
          </View>
          {displayProducts.map((p: any, index) => (
            <TouchableOpacity key={p._key || p.id + '-' + index} testID={`product-card-${index}`} style={styles.productCard} onPress={() => router.push({ pathname: '/product/[id]', params: { id: p.id } })} activeOpacity={0.8}>
              <Image source={{ uri: getImageUrl(p, false) }} style={styles.productImage} />
              <View style={styles.productInfo}>
                <View style={styles.productBadges}>
                  <View style={[styles.badge, { backgroundColor: p.metal_type === 'gold' ? '#D4AF3720' : p.metal_type === 'diamond' ? '#3B82F620' : '#E0E0E020' }]}>
                    <Text style={[styles.badgeText, { color: p.metal_type === 'gold' ? Colors.gold : p.metal_type === 'diamond' ? Colors.info : Colors.silver }]}>{p.metal_type?.toUpperCase()}</Text>
                  </View>
                  {p.is_new_arrival && <View style={[styles.badge, { backgroundColor: '#10B98120' }]}><Text style={[styles.badgeText, { color: Colors.success }]}>NEW</Text></View>}
                </View>
                <Text style={styles.productTitle} numberOfLines={2}>{p.title}</Text>
                <Text style={styles.productMeta}>{p.category?.replace(/_/g, ' ')}{p.approx_weight ? ` • ${p.approx_weight}` : ''}</Text>
                {(p.purity || p.selling_touch) && (
                  <View style={styles.compactMeta}>
                    {p.purity ? <Text style={styles.compactTag}>Purity: {p.purity}</Text> : null}
                    {p.selling_touch ? <Text style={styles.compactTag}>Touch: {p.selling_touch}</Text> : null}
                    {p.selling_label ? <Text style={styles.compactTag}>{p.selling_label}</Text> : null}
                  </View>
                )}
                <View style={styles.productActions}>
                  <TouchableOpacity style={styles.askPriceBtn} onPress={() => { addToCart(p.id); Alert.alert('Product added to the cart', 'Item has been added to your selection.'); }}><Text style={styles.askPriceText}>Add to Cart</Text></TouchableOpacity>
                  <TouchableOpacity style={styles.iconBtn} onPress={() => router.push({ pathname: '/request-call', params: { type: 'ask_price', productId: p.id } })}><Ionicons name="pricetag-outline" size={18} color={Colors.textSecondary} /></TouchableOpacity>
                  <TouchableOpacity style={styles.iconBtn} onPress={async () => { try { await api.post(`/wishlist/toggle?product_id=${p.id}`); } catch {} }}><Ionicons name="heart-outline" size={18} color={Colors.textSecondary} /></TouchableOpacity>
                </View>
              </View>
            </TouchableOpacity>
          ))}
          {/* Loading indicator for endless scroll */}
          <ActivityIndicator color={Colors.gold} style={{ paddingVertical: 20 }} />
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
  cartBadge: { position: 'absolute', top: 2, right: 2, minWidth: 16, height: 16, borderRadius: 8, backgroundColor: Colors.error, alignItems: 'center', justifyContent: 'center' },
  cartBadgeText: { fontSize: 9, color: '#fff', fontWeight: '700' },
  rateCard: { marginHorizontal: Spacing.lg, marginTop: Spacing.md, backgroundColor: Colors.card, borderRadius: 16, padding: Spacing.md, borderWidth: 1, borderColor: Colors.borderGold },
  liveIndicator: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, marginBottom: 6 },
  liveDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: Colors.success },
  liveText: { fontSize: 9, color: Colors.success, fontWeight: '700', letterSpacing: 1 },
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
  quickActions: { flexDirection: 'row', flexWrap: 'wrap', paddingHorizontal: Spacing.md, marginTop: Spacing.lg, gap: 2 },
  quickAction: { width: '24%', alignItems: 'center', paddingVertical: Spacing.sm, marginBottom: Spacing.xs },
  quickIcon: { width: 44, height: 44, borderRadius: 12, alignItems: 'center', justifyContent: 'center', marginBottom: 4 },
  quickLabel: { fontSize: 9, color: Colors.textSecondary, fontWeight: '500', textAlign: 'center' },
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
  productImage: { width: '100%', height: 260, backgroundColor: Colors.surface },
  productInfo: { padding: Spacing.md },
  productBadges: { flexDirection: 'row', gap: 6, marginBottom: Spacing.sm },
  badge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 },
  badgeText: { fontSize: 9, fontWeight: '700', letterSpacing: 1 },
  productTitle: { fontSize: FontSize.base, fontWeight: '600', color: Colors.text, marginBottom: 4 },
  productMeta: { fontSize: FontSize.sm, color: Colors.textSecondary, marginBottom: 4, textTransform: 'capitalize' },
  compactMeta: { flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginBottom: Spacing.sm },
  compactTag: { fontSize: 9, color: Colors.gold, fontWeight: '500', backgroundColor: Colors.gold + '10', paddingHorizontal: 5, paddingVertical: 1, borderRadius: 4 },
  productActions: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  askPriceBtn: { backgroundColor: Colors.gold, paddingHorizontal: 16, paddingVertical: 8, borderRadius: 8 },
  askPriceText: { fontSize: FontSize.sm, fontWeight: '700', color: '#000' },
  iconBtn: { width: 36, height: 36, borderRadius: 18, backgroundColor: Colors.surface, alignItems: 'center', justifyContent: 'center' },
});
