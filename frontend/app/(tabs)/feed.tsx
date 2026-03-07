import React, { useEffect, useState, useCallback, useRef } from 'react';
import { View, Text, StyleSheet, FlatList, TouchableOpacity, Image, RefreshControl, ActivityIndicator, TextInput } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../../src/theme';
import { api, getImageUrl } from '../../src/api';
import { useLang } from '../../src/context/LanguageContext';

interface Product { id: string; title: string; images: string[]; metal_type: string; category: string; approx_weight: string; stock_status: string; is_new_arrival: boolean; is_trending: boolean; storage_path?: string; thumbnail_path?: string; }
const CATEGORIES = ['All', 'payal', 'chain', 'articles', 'necklace', 'ring', 'bangles', 'bracelet', 'gifting', 'coins', 'kadaa', 'pendant', 'kids', 'toe_rings', 'earrings', 'mens', 'nose_ring', 'waist_belt'];
const METALS = ['All', 'silver', 'gold', 'diamond'];

export default function FeedScreen() {
  const router = useRouter();
  const { t } = useLang();
  const [products, setProducts] = useState<Product[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [category, setCategory] = useState('');
  const [metal, setMetal] = useState('');
  const [search, setSearch] = useState('');
  const [hasMore, setHasMore] = useState(true);
  const flatListRef = useRef<FlatList>(null);

  const fetchProducts = useCallback(async (p: number = 1, refresh: boolean = false) => {
    if (loadingMore && p > 1) return;
    try {
      if (p === 1) setLoading(true); else setLoadingMore(true);
      const params = new URLSearchParams({ page: String(p), limit: '20' });
      if (category) params.set('category', category);
      if (metal) params.set('metal_type', metal);
      if (search) params.set('search', search);
      const res = await api.get(`/products?${params}`);
      const newProducts = res.products || [];
      if (refresh || p === 1) {
        setProducts(newProducts);
      } else {
        setProducts(prev => [...prev, ...newProducts]);
      }
      setTotalPages(res.pages || 1);
      setPage(p);
      setHasMore(p < (res.pages || 1));
    } catch (e) { console.error(e); }
    finally { setLoading(false); setLoadingMore(false); setRefreshing(false); }
  }, [category, metal, search, loadingMore]);

  useEffect(() => { fetchProducts(1, true); }, [category, metal]);

  const onRefresh = () => { setRefreshing(true); setHasMore(true); fetchProducts(1, true); };
  const loadMore = () => { if (!loadingMore && hasMore && page < totalPages) fetchProducts(page + 1); };
  const doSearch = () => fetchProducts(1, true);

  const openViewer = (index: number) => {
    const item = products[index];
    if (item) {
      router.push({ pathname: '/image-viewer', params: { productId: item.id, startIndex: String(index) } });
    }
  };

  const renderItem = ({ item, index }: { item: Product; index: number }) => {
    const thumbUri = getImageUrl(item, true);
    return (
      <TouchableOpacity testID={`feed-item-${item.id}`} style={styles.card} onPress={() => openViewer(index)} activeOpacity={0.85}>
        <Image source={{ uri: thumbUri }} style={styles.cardImage} />
        <View style={styles.cardOverlay}>
          <View style={styles.cardBadge}>
            <Text style={styles.cardBadgeText}>{item.metal_type?.toUpperCase()}</Text>
          </View>
          {item.is_trending && <View style={[styles.cardBadge, { backgroundColor: Colors.warning + '30' }]}><Ionicons name="flame" size={10} color={Colors.warning} /></View>}
        </View>
        <View style={styles.cardBody}>
          <Text style={styles.cardTitle} numberOfLines={1}>{item.title}</Text>
          <Text style={styles.cardMeta}>{item.category?.replace(/_/g, ' ')}{item.approx_weight ? ` • ${item.approx_weight}` : ''}</Text>
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Collection</Text>
      </View>

      {/* Search */}
      <View style={styles.searchRow}>
        <View style={styles.searchBox}>
          <Ionicons name="search" size={18} color={Colors.textMuted} />
          <TextInput testID="feed-search" style={styles.searchInput} placeholder="Search products..." placeholderTextColor={Colors.textMuted} value={search} onChangeText={setSearch} onSubmitEditing={doSearch} returnKeyType="search" />
        </View>
      </View>

      {/* Metal Filter */}
      <View style={styles.filterRow}>
        {METALS.map(m => (
          <TouchableOpacity key={m} testID={`metal-filter-${m}`} style={[styles.filterChip, (m === 'All' ? !metal : metal === m) && styles.filterChipActive]} onPress={() => setMetal(m === 'All' ? '' : m)}>
            <Text style={[styles.filterChipText, (m === 'All' ? !metal : metal === m) && styles.filterChipTextActive]}>{m.toUpperCase()}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Category Filter */}
      <FlatList horizontal data={CATEGORIES} keyExtractor={i => i} showsHorizontalScrollIndicator={false} contentContainerStyle={styles.catRow}
        renderItem={({ item: c }) => (
          <TouchableOpacity testID={`cat-filter-${c}`} style={[styles.catChip, (c === 'All' ? !category : category === c) && styles.catChipActive]} onPress={() => setCategory(c === 'All' ? '' : c)}>
            <Text style={[styles.catChipText, (c === 'All' ? !category : category === c) && styles.catChipTextActive]}>{c.replace(/_/g, ' ')}</Text>
          </TouchableOpacity>
        )}
      />

      {loading ? <ActivityIndicator color={Colors.gold} style={{ marginTop: 40 }} /> : (
        <FlatList
          ref={flatListRef}
          testID="feed-list"
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
          removeClippedSubviews={true}
          ListFooterComponent={loadingMore ? <ActivityIndicator color={Colors.gold} style={{ padding: 20 }} /> : hasMore ? null : products.length > 0 ? <Text style={styles.endText}>You've seen all products</Text> : null}
          ListEmptyComponent={<Text style={styles.emptyText}>{t('no_products')}</Text>}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: { paddingHorizontal: Spacing.lg, paddingTop: Spacing.md, paddingBottom: Spacing.sm },
  headerTitle: { fontSize: FontSize.xl, fontWeight: '700', color: Colors.text },
  searchRow: { paddingHorizontal: Spacing.lg, marginBottom: Spacing.sm },
  searchBox: { flexDirection: 'row', alignItems: 'center', backgroundColor: Colors.surface, borderRadius: 12, paddingHorizontal: Spacing.md, gap: 8 },
  searchInput: { flex: 1, fontSize: FontSize.md, color: Colors.text, paddingVertical: 12 },
  filterRow: { flexDirection: 'row', paddingHorizontal: Spacing.lg, gap: 8, marginBottom: Spacing.sm },
  filterChip: { paddingHorizontal: 14, paddingVertical: 6, borderRadius: 8, backgroundColor: Colors.surface, borderWidth: 1, borderColor: Colors.border },
  filterChipActive: { backgroundColor: Colors.gold + '20', borderColor: Colors.gold },
  filterChipText: { fontSize: FontSize.xs, color: Colors.textSecondary, fontWeight: '600', letterSpacing: 1 },
  filterChipTextActive: { color: Colors.gold },
  catRow: { paddingHorizontal: Spacing.lg, gap: 8, paddingBottom: Spacing.sm },
  catChip: { paddingHorizontal: 14, paddingVertical: 6, borderRadius: 8, backgroundColor: Colors.surface },
  catChipActive: { backgroundColor: Colors.gold + '15' },
  catChipText: { fontSize: FontSize.xs, color: Colors.textMuted, fontWeight: '500', textTransform: 'capitalize' },
  catChipTextActive: { color: Colors.gold },
  row: { gap: Spacing.sm, paddingHorizontal: Spacing.lg },
  listContent: { paddingTop: Spacing.sm, paddingBottom: 24 },
  card: { flex: 1, backgroundColor: Colors.card, borderRadius: 14, overflow: 'hidden', marginBottom: Spacing.sm, maxWidth: '48.5%' },
  cardImage: { width: '100%', aspectRatio: 0.85, backgroundColor: Colors.surface },
  cardOverlay: { position: 'absolute', top: 8, left: 8, flexDirection: 'row', gap: 4 },
  cardBadge: { backgroundColor: 'rgba(0,0,0,0.6)', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  cardBadgeText: { fontSize: 8, color: Colors.text, fontWeight: '700', letterSpacing: 1 },
  cardBody: { padding: 10 },
  cardTitle: { fontSize: FontSize.sm, fontWeight: '600', color: Colors.text, marginBottom: 2 },
  cardMeta: { fontSize: FontSize.xs, color: Colors.textMuted, textTransform: 'capitalize' },
  emptyText: { fontSize: FontSize.md, color: Colors.textMuted, textAlign: 'center', marginTop: 40 },
  endText: { fontSize: FontSize.xs, color: Colors.textMuted, textAlign: 'center', paddingVertical: 20 },
});
