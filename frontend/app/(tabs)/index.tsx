import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, StyleSheet, FlatList, TouchableOpacity, Image, RefreshControl, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../../src/theme';
import { api, getImageUrl } from '../../src/api';
import { useAuth } from '../../src/context/AuthContext';
import { useLang } from '../../src/context/LanguageContext';
import { showAlert } from '../../src/utils/alert';
import BannerCarousel from '../../src/components/BannerCarousel';

interface Story { id: string; title: string; image_url: string; category: string; link_type: string; link_id: string; }
interface Product { id: string; title: string; images: string[]; metal_type: string; category: string; approx_weight: string; is_new_arrival: boolean; is_trending: boolean; storage_path?: string; thumbnail_path?: string; purity?: string; selling_touch?: string; selling_label?: string; }

type MetalTab = 'silver' | 'gold';
const PAGE_SIZE = 20;

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
  const [stories, setStories] = useState<Story[]>([]);
  const [silverProducts, setSilverProducts] = useState<Product[]>([]);
  const [goldProducts, setGoldProducts] = useState<Product[]>([]);
  // Silver is the default on every fresh app launch (not persisted)
  const [metal, setMetal] = useState<MetalTab>('silver');
  const [visibleCount, setVisibleCount] = useState<Record<MetalTab, number>>({ silver: PAGE_SIZE, gold: PAGE_SIZE });
  const [cartCount, setCartCount] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  const T: Record<string, any> = {
    en: { welcome: 'Welcome back,', highlights: 'HIGHLIGHTS', latest: 'LATEST COLLECTION', seeAll: 'See All', calc: 'Calculator', call: 'Request Call', video: 'Video Call', rewards: 'My Rewards', ai: 'AI Assistant', guide: 'Silver Guide', rateList: 'Rate List', schemes: 'Schemes', brands: 'Brands', showroom: 'Showroom', exhibition: 'Exhibition', silver: 'Silver', gold: 'Gold', emptySilver: 'No silver products available yet', emptyGold: 'No gold products available yet', loadFailed: 'Could not load data. Please check your connection.', retry: 'Retry', notifTitle: 'Notifications', notifEmpty: 'No new notifications yet.', addedCart: 'Added to Cart', addedCartMsg: 'Item has been added to your selection.', error: 'Error', cartFail: 'Could not add to cart. Please try again.', wishUpdated: 'Wishlist updated', wishFail: 'Could not update wishlist. Please try again.' },
    hi: { welcome: 'वापस स्वागत है,', highlights: 'हाइलाइट्स', latest: 'नवीनतम संग्रह', seeAll: 'सभी देखें', calc: 'कैलकुलेटर', call: 'कॉल अनुरोध', video: 'वीडियो कॉल', rewards: 'मेरे रिवॉर्ड्स', ai: 'AI सहायक', guide: 'चांदी गाइड', rateList: 'रेट लिस्ट', schemes: 'स्कीम्स', brands: 'ब्रांड', showroom: 'शोरूम', exhibition: 'प्रदर्शनी', silver: 'चांदी', gold: 'सोना', emptySilver: 'अभी कोई चांदी के उत्पाद उपलब्ध नहीं', emptyGold: 'अभी कोई सोने के उत्पाद उपलब्ध नहीं', loadFailed: 'डेटा लोड नहीं हो सका। कृपया कनेक्शन जांचें।', retry: 'फिर से कोशिश करें', notifTitle: 'सूचनाएं', notifEmpty: 'अभी कोई नई सूचना नहीं है।', addedCart: 'कार्ट में जोड़ा गया', addedCartMsg: 'आइटम आपके चयन में जोड़ दिया गया है।', error: 'त्रुटि', cartFail: 'कार्ट में नहीं जोड़ा जा सका। फिर से कोशिश करें।', wishUpdated: 'विशलिस्ट अपडेट हुई', wishFail: 'विशलिस्ट अपडेट नहीं हो सकी। फिर से कोशिश करें।' },
    pa: { welcome: 'ਵਾਪਸ ਸਵਾਗਤ ਹੈ,', highlights: 'ਹਾਈਲਾਈਟਸ', latest: 'ਨਵੀਨਤਮ ਸੰਗ੍ਰਹਿ', seeAll: 'ਸਭ ਵੇਖੋ', calc: 'ਕੈਲਕੁਲੇਟਰ', call: 'ਕਾਲ ਬੇਨਤੀ', video: 'ਵੀਡੀਓ ਕਾਲ', rewards: 'ਮੇਰੇ ਇਨਾਮ', ai: 'AI ਸਹਾਇਕ', guide: 'ਚਾਂਦੀ ਗਾਈਡ', rateList: 'ਰੇਟ ਲਿਸਟ', schemes: 'ਸਕੀਮਾਂ', brands: 'ਬ੍ਰਾਂਡ', showroom: 'ਸ਼ੋਅਰੂਮ', exhibition: 'ਪ੍ਰਦਰਸ਼ਨੀ', silver: 'ਚਾਂਦੀ', gold: 'ਸੋਨਾ', emptySilver: 'ਹਾਲੇ ਕੋਈ ਚਾਂਦੀ ਦੇ ਉਤਪਾਦ ਉਪਲਬਧ ਨਹੀਂ', emptyGold: 'ਹਾਲੇ ਕੋਈ ਸੋਨੇ ਦੇ ਉਤਪਾਦ ਉਪਲਬਧ ਨਹੀਂ', loadFailed: 'ਡਾਟਾ ਲੋਡ ਨਹੀਂ ਹੋ ਸਕਿਆ। ਕਿਰਪਾ ਕਰਕੇ ਕਨੈਕਸ਼ਨ ਚੈੱਕ ਕਰੋ।', retry: 'ਮੁੜ ਕੋਸ਼ਿਸ਼ ਕਰੋ', notifTitle: 'ਸੂਚਨਾਵਾਂ', notifEmpty: 'ਹਾਲੇ ਕੋਈ ਨਵੀਂ ਸੂਚਨਾ ਨਹੀਂ ਹੈ।', addedCart: 'ਕਾਰਟ ਵਿੱਚ ਜੋੜਿਆ ਗਿਆ', addedCartMsg: 'ਆਈਟਮ ਤੁਹਾਡੀ ਚੋਣ ਵਿੱਚ ਜੋੜ ਦਿੱਤੀ ਗਈ ਹੈ।', error: 'ਗਲਤੀ', cartFail: 'ਕਾਰਟ ਵਿੱਚ ਨਹੀਂ ਜੋੜਿਆ ਜਾ ਸਕਿਆ। ਮੁੜ ਕੋਸ਼ਿਸ਼ ਕਰੋ।', wishUpdated: 'ਵਿਸ਼ਲਿਸਟ ਅੱਪਡੇਟ ਹੋਈ', wishFail: 'ਵਿਸ਼ਲਿਸਟ ਅੱਪਡੇਟ ਨਹੀਂ ਹੋ ਸਕੀ। ਮੁੜ ਕੋਸ਼ਿਸ਼ ਕਰੋ।' },
  };
  const t = T[language] || T.en;

  const loadData = useCallback(async () => {
    try {
      setLoadError(false);
      const [storyRes, silverRes, goldRes, cartRes] = await Promise.all([
        api.get('/stories').catch(() => ({ stories: [] })),
        api.get('/products?metal_type=silver&limit=100'),
        api.get('/products?metal_type=gold&limit=100'),
        api.get('/cart/count').catch(() => ({ count: 0 })),
      ]);
      setStories(storyRes.stories || []);
      setSilverProducts(silverRes.products || []);
      setGoldProducts(goldRes.products || []);
      setCartCount(cartRes.count || 0);
    } catch (e) { console.error(e); setLoadError(true); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { loadData(); }, []);

  const onRefresh = () => { setRefreshing(true); loadData(); };

  const allProducts = metal === 'silver' ? silverProducts : goldProducts;
  const displayProducts = allProducts.slice(0, visibleCount[metal]);

  const loadMoreProducts = useCallback(() => {
    setVisibleCount(prev => {
      const total = metal === 'silver' ? silverProducts.length : goldProducts.length;
      if (total === 0 || prev[metal] >= total) return prev;
      return { ...prev, [metal]: Math.min(prev[metal] + PAGE_SIZE, total) };
    });
  }, [metal, silverProducts.length, goldProducts.length]);

  const handleStoryPress = (story: Story) => {
    if (story.link_type === 'category' && story.link_id) {
      router.push({ pathname: '/(tabs)/feed', params: { category: story.link_id } });
    } else if (story.link_type === 'request') {
      router.push({ pathname: '/request-call', params: { type: story.link_id || 'video_call' } });
    } else { router.push('/(tabs)/feed'); }
  };

  const addToCart = async (productId: string) => {
    try {
      await api.post('/cart/add', { product_id: productId });
      setCartCount(prev => prev + 1);
      showAlert(t.addedCart, t.addedCartMsg);
    } catch (e: any) {
      showAlert(t.error, e?.message || t.cartFail);
    }
  };

  const toggleWishlist = async (productId: string) => {
    try {
      await api.post(`/wishlist/toggle?product_id=${productId}`);
      showAlert(t.wishUpdated);
    } catch (e: any) {
      showAlert(t.error, e?.message || t.wishFail);
    }
  };

  const renderProduct = useCallback(({ item: p }: { item: Product }) => (
    <TouchableOpacity testID={`product-card-${p.id}`} style={styles.productCard} onPress={() => router.push({ pathname: '/product/[id]', params: { id: p.id } })} activeOpacity={0.8}>
      <Image source={{ uri: getImageUrl(p, false) }} style={styles.productImage} />
      <View style={styles.productInfo}>
        <View style={styles.productBadges}>
          <View style={[styles.badge, { backgroundColor: p.metal_type === 'gold' ? '#D4AF3720' : p.metal_type === 'diamond' ? '#3B82F620' : '#E0E0E020' }]}>
            <Text style={[styles.badgeText, { color: p.metal_type === 'gold' ? Colors.gold : p.metal_type === 'diamond' ? Colors.info : Colors.silver }]}>{p.metal_type?.toUpperCase()}</Text>
          </View>
          {p.is_new_arrival && <View style={[styles.badge, { backgroundColor: '#10B98120' }]}><Text style={[styles.badgeText, { color: Colors.success }]}>NEW</Text></View>}
        </View>
        <Text style={styles.productTitle} numberOfLines={2}>{p.title}</Text>
        <Text style={styles.productMeta}>{p.category?.replace(/_/g, ' ')}{p.approx_weight ? ` \u2022 ${p.approx_weight}` : ''}</Text>
        {(p.purity || p.selling_touch) && (
          <View style={styles.compactMeta}>
            {p.purity ? <Text style={styles.compactTag}>Purity: {p.purity}</Text> : null}
            {p.selling_touch ? <Text style={styles.compactTag}>Touch: {p.selling_touch}</Text> : null}
            {p.selling_label ? <Text style={styles.compactTag}>{p.selling_label}</Text> : null}
          </View>
        )}
        <View style={styles.productActions}>
          <TouchableOpacity style={styles.askPriceBtn} onPress={() => addToCart(p.id)}><Text style={styles.askPriceText}>Add to Cart</Text></TouchableOpacity>
          <TouchableOpacity style={styles.iconBtn} onPress={() => router.push({ pathname: '/request-call', params: { type: 'ask_price', productId: p.id } })}><Ionicons name="pricetag-outline" size={18} color={Colors.textSecondary} /></TouchableOpacity>
          <TouchableOpacity style={styles.iconBtn} onPress={() => toggleWishlist(p.id)}><Ionicons name="heart-outline" size={18} color={Colors.textSecondary} /></TouchableOpacity>
        </View>
      </View>
    </TouchableOpacity>
  ), [t]);

  const headerComponent = useCallback(() => (
    <>
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
          <TouchableOpacity testID="notifications-btn" style={styles.headerIcon} onPress={() => showAlert(t.notifTitle, t.notifEmpty)}>
            <Ionicons name="notifications-outline" size={22} color={Colors.text} />
          </TouchableOpacity>
        </View>
      </View>
      {/* Admin-managed banner carousel (replaces the old live-rate card) */}
      <BannerCarousel />
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
      {stories.length > 0 && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>{t.highlights}</Text>
          <FlatList horizontal data={stories} keyExtractor={s => s.id} showsHorizontalScrollIndicator={false} contentContainerStyle={styles.storiesRow}
            renderItem={({ item: s }) => (
              <TouchableOpacity testID={`story-${s.id}`} onPress={() => handleStoryPress(s)} activeOpacity={0.7}>
                <View style={styles.storyItem}><View style={styles.storyRing}><Image source={{ uri: s.image_url }} style={styles.storyImage} /></View><Text style={styles.storyTitle} numberOfLines={1}>{s.title}</Text></View>
              </TouchableOpacity>
            )}
          />
        </View>
      )}
      <View style={[styles.section, { marginBottom: 0 }]}>
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>{t.latest}</Text>
          <TouchableOpacity testID="see-all-btn" onPress={() => router.push({ pathname: '/(tabs)/feed', params: { metal } })}><Text style={styles.seeAll}>{t.seeAll}</Text></TouchableOpacity>
        </View>
        {/* Silver / Gold segmented toggle — Silver default on launch */}
        <View style={styles.metalToggle}>
          {(['silver', 'gold'] as MetalTab[]).map(m => {
            const active = metal === m;
            const activeColor = m === 'gold' ? Colors.gold : Colors.silver;
            return (
              <TouchableOpacity
                key={m}
                testID={`metal-toggle-${m}`}
                accessibilityRole="button"
                accessibilityState={{ selected: active }}
                accessibilityLabel={`Show ${m} collection`}
                style={[styles.metalToggleBtn, active && { backgroundColor: activeColor + '18', borderColor: activeColor }]}
                onPress={() => setMetal(m)}
              >
                <Ionicons name={m === 'gold' ? 'sunny' : 'ellipse'} size={13} color={active ? activeColor : Colors.textMuted} />
                <Text style={[styles.metalToggleText, active && { color: activeColor }]}>{t[m]}</Text>
              </TouchableOpacity>
            );
          })}
        </View>
        {loadError && (
          <View style={styles.errorBox} testID="home-error">
            <Ionicons name="cloud-offline-outline" size={18} color={Colors.error} />
            <Text style={styles.errorBoxText}>{t.loadFailed}</Text>
            <TouchableOpacity testID="home-retry" style={styles.retryBtn} onPress={() => { setLoading(true); loadData(); }}>
              <Text style={styles.retryBtnText}>{t.retry}</Text>
            </TouchableOpacity>
          </View>
        )}
      </View>
    </>
  ), [stories, cartCount, user, t, metal, loadError]);

  if (loading) return <View style={styles.loader}><ActivityIndicator size="large" color={Colors.gold} /></View>;

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <FlatList
        data={displayProducts}
        extraData={metal}
        keyExtractor={(item) => `${metal}-${item.id}`}
        renderItem={renderProduct}
        ListHeaderComponent={headerComponent}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={Colors.gold} />}
        onEndReached={loadMoreProducts}
        onEndReachedThreshold={0.5}
        initialNumToRender={8}
        maxToRenderPerBatch={8}
        windowSize={5}
        removeClippedSubviews={true}
        contentContainerStyle={{ paddingHorizontal: Spacing.lg, paddingBottom: 24 }}
        showsVerticalScrollIndicator={false}
        ListEmptyComponent={!loadError ? (
          <View style={styles.emptyBox} testID="home-empty">
            <Ionicons name="cube-outline" size={36} color={Colors.textMuted} />
            <Text style={styles.emptyBoxText}>{metal === 'silver' ? t.emptySilver : t.emptyGold}</Text>
          </View>
        ) : null}
        ListFooterComponent={displayProducts.length > 0 && displayProducts.length < allProducts.length ? <ActivityIndicator color={Colors.gold} style={{ paddingVertical: 20 }} /> : null}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  loader: { flex: 1, backgroundColor: Colors.background, justifyContent: 'center', alignItems: 'center' },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingTop: Spacing.md, paddingBottom: Spacing.sm },
  greeting: { fontSize: FontSize.sm, color: Colors.textSecondary },
  userName: { fontSize: FontSize.xl, fontWeight: '700', color: Colors.text },
  headerRight: { flexDirection: 'row', gap: 8 },
  headerIcon: { width: 40, height: 40, borderRadius: 20, backgroundColor: Colors.surface, alignItems: 'center', justifyContent: 'center' },
  cartBadge: { position: 'absolute', top: 2, right: 2, minWidth: 16, height: 16, borderRadius: 8, backgroundColor: Colors.error, alignItems: 'center', justifyContent: 'center' },
  cartBadgeText: { fontSize: 9, color: '#fff', fontWeight: '700' },
  metalToggle: { flexDirection: 'row', gap: 8, marginBottom: Spacing.md },
  metalToggleBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, minHeight: 44, borderRadius: 10, backgroundColor: Colors.surface, borderWidth: 1, borderColor: Colors.border },
  metalToggleText: { fontSize: FontSize.sm, fontWeight: '700', color: Colors.textMuted, letterSpacing: 1 },
  errorBox: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: Colors.error + '10', borderRadius: 12, padding: Spacing.md, borderWidth: 1, borderColor: Colors.error + '30', marginBottom: Spacing.sm },
  errorBoxText: { flex: 1, fontSize: FontSize.sm, color: Colors.error },
  retryBtn: { backgroundColor: Colors.error + '20', paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8 },
  retryBtnText: { fontSize: FontSize.xs, fontWeight: '700', color: Colors.error },
  emptyBox: { alignItems: 'center', paddingVertical: 40, gap: 8 },
  emptyBoxText: { fontSize: FontSize.sm, color: Colors.textMuted, textAlign: 'center' },
  quickActions: { flexDirection: 'row', flexWrap: 'wrap', marginTop: Spacing.lg, gap: 2 },
  quickAction: { width: '24%', alignItems: 'center', paddingVertical: Spacing.sm, marginBottom: Spacing.xs },
  quickIcon: { width: 44, height: 44, borderRadius: 12, alignItems: 'center', justifyContent: 'center', marginBottom: 4 },
  quickLabel: { fontSize: 9, color: Colors.textSecondary, fontWeight: '500', textAlign: 'center' },
  section: { marginTop: Spacing.lg },
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
