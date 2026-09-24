import React, { useCallback, useEffect, useRef, useState } from 'react';
import { View, Text, StyleSheet, FlatList, TouchableOpacity, RefreshControl, ActivityIndicator, useWindowDimensions } from 'react-native';
import { Image } from 'expo-image';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api, productImage } from '../src/api';
import { IMAGE_PLACEHOLDER } from '../src/imagePlaceholder';
import { useAuth } from '../src/context/AuthContext';
import { useLang } from '../src/context/LanguageContext';
import { homeRouteFor } from '../src/navigation';

/**
 * Signed-out catalogue preview (iOS entry point, App Store guideline 5.1.1(v)): the latest products from the public
 * catalogue, read-only and capped at PREVIEW_LIMIT items. No prices are shown anywhere in the app; cart, wishlist,
 * enquiries, rewards, notifications and the profile still require the mobile-OTP sign-in. Android/web are never routed
 * here (see `guestHomeRoute`), so their login-first flow is untouched.
 */
const PREVIEW_LIMIT = 100;
const PAGE = 20;

interface Product { id: string; title: string; metal_type: string; category: string; approx_weight?: string; purity?: string; selling_touch?: string; is_new_arrival?: boolean; storage_path?: string; thumbnail_path?: string; images?: string[]; }

export default function GuestPreviewScreen() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const { language } = useLang();
  const { width: windowWidth } = useWindowDimensions();
  const cardWidth = (windowWidth - Spacing.lg * 2) * 0.485;
  const [products, setProducts] = useState<Product[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [pages, setPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const generation = useRef(0);

  const T: Record<string, any> = {
    en: { brand: 'YASH TRADE', tagline: 'Wholesale silver & gold jewellery', signIn: 'Sign in', title: 'LATEST COLLECTION · PREVIEW', note: `Browse up to ${PREVIEW_LIMIT} products without an account. Sign in to see the full collection, ask prices and save your selection.`, endTitle: 'End of preview', endBody: (n: number) => n > PREVIEW_LIMIT ? `Sign in with your mobile number to browse all ${n} products, ask prices, add to cart and save wishlists.` : 'Sign in with your mobile number to ask prices, add to cart and save wishlists.', endBtn: 'SIGN IN TO SEE THE FULL COLLECTION', loadFailed: 'Could not load products. Please check your connection.', retry: 'Retry', empty: 'No products available yet', help: 'Help' },
    hi: { brand: 'YASH TRADE', tagline: 'थोक चांदी और सोने के आभूषण', signIn: 'साइन इन', title: 'नवीनतम संग्रह · पूर्वावलोकन', note: `बिना खाते के ${PREVIEW_LIMIT} उत्पाद तक देखें। पूरा संग्रह देखने, कीमत पूछने और चयन सहेजने के लिए साइन इन करें।`, endTitle: 'पूर्वावलोकन समाप्त', endBody: (n: number) => n > PREVIEW_LIMIT ? `सभी ${n} उत्पाद देखने, कीमत पूछने, कार्ट में जोड़ने और विशलिस्ट सहेजने के लिए मोबाइल नंबर से साइन इन करें।` : 'कीमत पूछने, कार्ट में जोड़ने और विशलिस्ट सहेजने के लिए मोबाइल नंबर से साइन इन करें।', endBtn: 'पूरा संग्रह देखने के लिए साइन इन करें', loadFailed: 'उत्पाद लोड नहीं हो सके। कृपया कनेक्शन जांचें।', retry: 'फिर से कोशिश करें', empty: 'अभी कोई उत्पाद उपलब्ध नहीं', help: 'सहायता' },
    pa: { brand: 'YASH TRADE', tagline: 'ਥੋਕ ਚਾਂਦੀ ਅਤੇ ਸੋਨੇ ਦੇ ਗਹਿਣੇ', signIn: 'ਸਾਈਨ ਇਨ', title: 'ਨਵੀਨਤਮ ਸੰਗ੍ਰਹਿ · ਪੂਰਵਦਰਸ਼ਨ', note: `ਬਿਨਾਂ ਖਾਤੇ ${PREVIEW_LIMIT} ਉਤਪਾਦ ਤੱਕ ਵੇਖੋ। ਪੂਰਾ ਸੰਗ੍ਰਹਿ ਵੇਖਣ, ਕੀਮਤ ਪੁੱਛਣ ਅਤੇ ਚੋਣ ਸੰਭਾਲਣ ਲਈ ਸਾਈਨ ਇਨ ਕਰੋ।`, endTitle: 'ਪੂਰਵਦਰਸ਼ਨ ਸਮਾਪਤ', endBody: (n: number) => n > PREVIEW_LIMIT ? `ਸਾਰੇ ${n} ਉਤਪਾਦ ਵੇਖਣ, ਕੀਮਤ ਪੁੱਛਣ, ਕਾਰਟ ਵਿੱਚ ਜੋੜਨ ਅਤੇ ਵਿਸ਼ਲਿਸਟ ਸੰਭਾਲਣ ਲਈ ਮੋਬਾਈਲ ਨੰਬਰ ਨਾਲ ਸਾਈਨ ਇਨ ਕਰੋ।` : 'ਕੀਮਤ ਪੁੱਛਣ, ਕਾਰਟ ਵਿੱਚ ਜੋੜਨ ਅਤੇ ਵਿਸ਼ਲਿਸਟ ਸੰਭਾਲਣ ਲਈ ਮੋਬਾਈਲ ਨੰਬਰ ਨਾਲ ਸਾਈਨ ਇਨ ਕਰੋ।', endBtn: 'ਪੂਰਾ ਸੰਗ੍ਰਹਿ ਵੇਖਣ ਲਈ ਸਾਈਨ ਇਨ ਕਰੋ', loadFailed: 'ਉਤਪਾਦ ਲੋਡ ਨਹੀਂ ਹੋ ਸਕੇ। ਕਿਰਪਾ ਕਰਕੇ ਕਨੈਕਸ਼ਨ ਚੈੱਕ ਕਰੋ।', retry: 'ਮੁੜ ਕੋਸ਼ਿਸ਼ ਕਰੋ', empty: 'ਹਾਲੇ ਕੋਈ ਉਤਪਾਦ ਉਪਲਬਧ ਨਹੀਂ', help: 'ਮਦਦ' },
  };
  const t = T[language] || T.en;

  // A signed-in account never sees the preview: straight to its own home.
  useEffect(() => { if (!authLoading && user) router.replace(homeRouteFor(user.role) as any); }, [authLoading, user]);

  const fetchPage = useCallback(async (p: number) => {
    const gen = generation.current;
    if (p === 1) { generation.current += 1; setLoading(products.length === 0); setLoadError(false); }
    else setLoadingMore(true);
    try {
      const res = await api.get(`/products?page=${p}&limit=${PAGE}`);
      if (p > 1 && gen !== generation.current) return;
      const incoming: Product[] = res.products || [];
      setProducts(prev => {
        const merged = p === 1 ? incoming : Array.from(new Map([...prev, ...incoming].map(x => [x.id, x])).values());
        return merged.slice(0, PREVIEW_LIMIT);
      });
      setTotal(res.total || 0);
      setPages(res.pages || 1);
      setPage(p);
    } catch {
      if (p === 1) setLoadError(true);
    } finally { setLoading(false); setLoadingMore(false); setRefreshing(false); }
  }, [products.length]);

  useEffect(() => { fetchPage(1); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const capped = products.length >= PREVIEW_LIMIT;
  const hasMore = !capped && page < pages;
  const loadMore = () => { if (!loading && !loadingMore && hasMore) fetchPage(page + 1); };
  const onRefresh = () => { setRefreshing(true); fetchPage(1); };
  const signIn = () => router.push('/login');

  const renderItem = ({ item }: { item: Product }) => (
    <TouchableOpacity testID={`guest-item-${item.id}`} style={styles.card} activeOpacity={0.85}
      onPress={() => router.push({ pathname: '/product/[id]', params: { id: item.id } })}>
      <Image source={{ uri: productImage(item, cardWidth) }} placeholder={IMAGE_PLACEHOLDER} placeholderContentFit="cover" contentFit="cover" transition={150}
        cachePolicy="memory-disk" recyclingKey={item.id} style={styles.cardImage} accessibilityLabel={item.title} />
      <View style={styles.cardOverlay}>
        <View style={styles.cardBadge}><Text style={styles.cardBadgeText}>{item.metal_type?.toUpperCase()}</Text></View>
        {item.is_new_arrival && <View style={[styles.cardBadge, { backgroundColor: Colors.success + '40' }]}><Text style={styles.cardBadgeText}>NEW</Text></View>}
      </View>
      <View style={styles.cardBody}>
        <Text style={styles.cardTitle} numberOfLines={1}>{item.title}</Text>
        <Text style={styles.cardMeta}>{item.category?.replace(/_/g, ' ')}{item.approx_weight ? ` \u2022 ${item.approx_weight}` : ''}</Text>
        {(item.purity || item.selling_touch) && (
          <View style={styles.cardDetails}>
            {item.purity ? <Text style={styles.cardDetail}>Purity: {item.purity}</Text> : null}
            {item.selling_touch ? <Text style={styles.cardDetail}>Touch: {item.selling_touch}</Text> : null}
          </View>
        )}
      </View>
    </TouchableOpacity>
  );

  const footer = loadingMore ? <ActivityIndicator color={Colors.gold} style={{ padding: 20 }} testID="guest-loading-more" />
    : (!hasMore && products.length > 0) ? (
      <View style={styles.endCard} testID="guest-preview-end">
        <Ionicons name="lock-closed-outline" size={26} color={Colors.gold} />
        <Text style={styles.endTitle}>{t.endTitle}</Text>
        <Text style={styles.endBody}>{t.endBody(total)}</Text>
        <TouchableOpacity testID="guest-end-sign-in" style={styles.endBtn} onPress={signIn} accessibilityRole="button">
          <Text style={styles.endBtnText}>{t.endBtn}</Text>
        </TouchableOpacity>
      </View>
    ) : null;

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <View style={styles.headerText}>
          <Text style={styles.brand}>{t.brand}</Text>
          <Text style={styles.tagline} numberOfLines={1}>{t.tagline}</Text>
        </View>
        <TouchableOpacity testID="guest-sign-in" style={styles.signInBtn} onPress={signIn} accessibilityRole="button" accessibilityLabel={t.signIn}>
          <Ionicons name="person-circle-outline" size={18} color="#000" />
          <Text style={styles.signInText}>{t.signIn}</Text>
        </TouchableOpacity>
      </View>
      <View style={styles.noteBox} testID="guest-preview-note">
        <Text style={styles.sectionTitle}>{t.title}</Text>
        <Text style={styles.noteText}>{t.note}</Text>
      </View>

      {loading ? <ActivityIndicator color={Colors.gold} style={{ marginTop: 40 }} testID="guest-loading" /> : loadError && products.length === 0 ? (
        <View style={styles.errorBox} testID="guest-error">
          <Ionicons name="cloud-offline-outline" size={36} color={Colors.error} />
          <Text style={styles.errorText}>{t.loadFailed}</Text>
          <TouchableOpacity testID="guest-retry" style={styles.retryBtn} onPress={() => { setLoading(true); fetchPage(1); }}>
            <Text style={styles.retryBtnText}>{t.retry}</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <FlatList
          testID="guest-list"
          data={products}
          keyExtractor={item => item.id}
          renderItem={renderItem}
          numColumns={2}
          columnWrapperStyle={styles.row}
          contentContainerStyle={styles.listContent}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={Colors.gold} />}
          onEndReached={loadMore}
          onEndReachedThreshold={0.5}
          initialNumToRender={10}
          maxToRenderPerBatch={10}
          windowSize={7}
          removeClippedSubviews
          ListFooterComponent={footer}
          ListEmptyComponent={<Text style={styles.emptyText} testID="guest-empty">{t.empty}</Text>}
        />
      )}

      <TouchableOpacity testID="guest-help-link" onPress={() => router.push('/help')} style={styles.helpLink} accessibilityRole="button">
        <Ionicons name="help-circle-outline" size={16} color={Colors.textSecondary} />
        <Text style={styles.helpLinkText}>{t.help}</Text>
      </TouchableOpacity>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: Spacing.lg, paddingTop: Spacing.md, paddingBottom: Spacing.sm, gap: Spacing.sm },
  headerText: { flex: 1, minWidth: 0 },
  brand: { fontSize: FontSize.xl, fontWeight: '700', color: Colors.gold, letterSpacing: 3 },
  tagline: { fontSize: FontSize.xs, color: Colors.textSecondary, letterSpacing: 0.5, marginTop: 2 },
  signInBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: Colors.gold, borderRadius: 22, paddingHorizontal: 16, minHeight: 44, justifyContent: 'center' },
  signInText: { fontSize: FontSize.sm, fontWeight: '700', color: '#000', letterSpacing: 0.5 },
  noteBox: { marginHorizontal: Spacing.lg, marginBottom: Spacing.sm, padding: Spacing.md, backgroundColor: Colors.card, borderRadius: 12, borderWidth: 1, borderColor: Colors.borderGold },
  sectionTitle: { fontSize: FontSize.xs, color: Colors.textSecondary, letterSpacing: 2, fontWeight: '700', marginBottom: 4 },
  noteText: { fontSize: FontSize.xs, color: Colors.textSecondary, lineHeight: 17 },
  row: { gap: Spacing.sm, paddingHorizontal: Spacing.lg },
  listContent: { paddingTop: Spacing.sm, paddingBottom: 72 },
  card: { flex: 1, backgroundColor: Colors.card, borderRadius: 14, overflow: 'hidden', marginBottom: Spacing.sm, maxWidth: '48.5%' },
  cardImage: { width: '100%', aspectRatio: 0.85, backgroundColor: Colors.surface },
  cardOverlay: { position: 'absolute', top: 8, left: 8, flexDirection: 'row', gap: 4 },
  cardBadge: { backgroundColor: 'rgba(0,0,0,0.6)', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  cardBadgeText: { fontSize: 8, color: Colors.text, fontWeight: '700', letterSpacing: 1 },
  cardBody: { padding: 10 },
  cardTitle: { fontSize: FontSize.sm, fontWeight: '600', color: Colors.text, marginBottom: 2 },
  cardMeta: { fontSize: FontSize.xs, color: Colors.textMuted, textTransform: 'capitalize' },
  cardDetails: { flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginTop: 3 },
  cardDetail: { fontSize: 8, color: Colors.gold, fontWeight: '500', backgroundColor: Colors.gold + '10', paddingHorizontal: 4, paddingVertical: 1, borderRadius: 3 },
  endCard: { marginHorizontal: Spacing.lg, marginTop: Spacing.md, padding: Spacing.lg, backgroundColor: Colors.card, borderRadius: 16, borderWidth: 1, borderColor: Colors.borderGold, alignItems: 'center', gap: 8 },
  endTitle: { fontSize: FontSize.md, fontWeight: '700', color: Colors.text },
  endBody: { fontSize: FontSize.sm, color: Colors.textSecondary, textAlign: 'center', lineHeight: 20 },
  endBtn: { marginTop: Spacing.sm, backgroundColor: Colors.gold, borderRadius: 12, paddingVertical: 14, paddingHorizontal: Spacing.lg, alignSelf: 'stretch', alignItems: 'center', minHeight: 48 },
  endBtnText: { fontSize: FontSize.sm, fontWeight: '700', color: '#000', letterSpacing: 1 },
  emptyText: { fontSize: FontSize.md, color: Colors.textMuted, textAlign: 'center', marginTop: 40 },
  errorBox: { alignItems: 'center', paddingVertical: 60, paddingHorizontal: Spacing.xl, gap: 10 },
  errorText: { fontSize: FontSize.sm, color: Colors.error, textAlign: 'center' },
  retryBtn: { backgroundColor: Colors.error + '20', paddingHorizontal: 24, paddingVertical: 10, borderRadius: 10 },
  retryBtnText: { fontSize: FontSize.sm, fontWeight: '700', color: Colors.error },
  helpLink: { position: 'absolute', bottom: 16, right: Spacing.lg, flexDirection: 'row', alignItems: 'center', gap: 6, minHeight: 44, paddingHorizontal: Spacing.md, backgroundColor: Colors.surface, borderRadius: 22 },
  helpLinkText: { fontSize: FontSize.sm, color: Colors.textSecondary, letterSpacing: 0.5 },
});
