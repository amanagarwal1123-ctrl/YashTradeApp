import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, Image, TouchableOpacity, ActivityIndicator, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../../src/theme';
import { api } from '../../src/api';
import { getImageUrl } from '../../src/api';

export default function ProductDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [product, setProduct] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [currentImage, setCurrentImage] = useState(0);

  useEffect(() => {
    (async () => {
      try {
        const p = await api.get(`/products/${id}`);
        setProduct(p);
      } catch {} finally { setLoading(false); }
    })();
  }, [id]);

  if (loading) return <View style={styles.loader}><ActivityIndicator size="large" color={Colors.gold} /></View>;
  if (!product) return <View style={styles.loader}><Text style={styles.errorText}>Product not found</Text></View>;

  const images = product.images || [];
  const hasStorageImage = !!product.storage_path;
  // Fix #3: Gallery selection respects currentImage for URL-based, storage for uploaded
  const displayImageUri = hasStorageImage
    ? getImageUrl(product, false)
    : images[currentImage] || getImageUrl(product, false);

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView showsVerticalScrollIndicator={false}>
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity testID="back-btn" onPress={() => router.back()} style={styles.backBtn}>
            <Ionicons name="arrow-back" size={24} color={Colors.text} />
          </TouchableOpacity>
          <TouchableOpacity testID="wishlist-btn" style={styles.backBtn} onPress={async () => {
            try { const r = await api.post(`/wishlist/toggle?product_id=${id}`); Alert.alert(r.wishlisted ? 'Added to Wishlist' : 'Removed from Wishlist'); } catch {}
          }}>
            <Ionicons name="heart-outline" size={24} color={Colors.text} />
          </TouchableOpacity>
        </View>

        {/* Image */}
        <View style={styles.imageContainer}>
          {displayImageUri ? (
            <Image source={{ uri: displayImageUri }} style={styles.mainImage} />
          ) : (
            <View style={[styles.mainImage, { backgroundColor: Colors.surface, justifyContent: 'center', alignItems: 'center' }]}>
              <Ionicons name="image-outline" size={48} color={Colors.textMuted} />
            </View>
          )}
          {images.length > 1 && (
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.thumbRow}>
              {images.map((img: string, i: number) => (
                <TouchableOpacity key={i} onPress={() => setCurrentImage(i)}>
                  <Image source={{ uri: img }} style={[styles.thumb, currentImage === i && styles.thumbActive]} />
                </TouchableOpacity>
              ))}
            </ScrollView>
          )}
        </View>

        {/* Info */}
        <View style={styles.infoSection}>
          <View style={styles.badges}>
            <View style={[styles.badge, { backgroundColor: Colors.gold + '20' }]}><Text style={[styles.badgeText, { color: Colors.gold }]}>{product.metal_type?.toUpperCase()}</Text></View>
            <View style={styles.badge}><Text style={styles.badgeText}>{product.category?.replace(/_/g, ' ').toUpperCase()}</Text></View>
            {product.is_new_arrival && <View style={[styles.badge, { backgroundColor: Colors.success + '20' }]}><Text style={[styles.badgeText, { color: Colors.success }]}>NEW</Text></View>}
            {product.stock_status === 'limited' && <View style={[styles.badge, { backgroundColor: Colors.warning + '20' }]}><Text style={[styles.badgeText, { color: Colors.warning }]}>LIMITED</Text></View>}
          </View>

          <Text style={styles.title}>{product.title}</Text>
          <Text style={styles.description}>{product.description}</Text>

          {product.approx_weight && (
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>Approx Weight</Text>
              <Text style={styles.detailValue}>{product.approx_weight}</Text>
            </View>
          )}
          {product.purity && (
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>Purity</Text>
              <Text style={styles.detailValue}>{product.purity}</Text>
            </View>
          )}
          {product.selling_touch && (
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>Touch</Text>
              <Text style={styles.detailValue}>{product.selling_touch}</Text>
            </View>
          )}
          {product.selling_label && (
            <View style={[styles.badge, { backgroundColor: Colors.gold + '20', alignSelf: 'flex-start', marginBottom: Spacing.sm }]}>
              <Text style={[styles.badgeText, { color: Colors.gold }]}>{product.selling_label}</Text>
            </View>
          )}

          {product.tags?.length > 0 && (
            <View style={styles.tagsRow}>
              {product.tags.map((t: string) => <View key={t} style={styles.tag}><Text style={styles.tagText}>#{t}</Text></View>)}
            </View>
          )}
        </View>

        {/* CTAs */}
        <View style={styles.ctaSection}>
          <TouchableOpacity testID="add-to-cart-btn" style={styles.ctaPrimary} onPress={async () => {
            try { await api.post('/cart/add', { product_id: id }); Alert.alert('Added', 'Item added to your selection'); } catch {}
          }}>
            <Ionicons name="cart" size={18} color="#000" />
            <Text style={styles.ctaPrimaryText}>Add to Selection</Text>
          </TouchableOpacity>
          <TouchableOpacity testID="ask-price-btn" style={styles.ctaSecondary} onPress={() => router.push({ pathname: '/request-call', params: { type: 'ask_price', productId: id } })}>
            <Ionicons name="pricetag" size={18} color={Colors.gold} />
            <Text style={styles.ctaSecondaryText}>Ask Price</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.ctaSection}>
          <TouchableOpacity testID="video-call-btn" style={styles.ctaOutline} onPress={() => router.push({ pathname: '/request-call', params: { type: 'video_call', productId: id } })}>
            <Text style={styles.ctaOutlineText}>Video Call</Text>
          </TouchableOpacity>
          <TouchableOpacity testID="hold-item-btn" style={styles.ctaOutline} onPress={() => router.push({ pathname: '/request-call', params: { type: 'hold_item', productId: id } })}>
            <Text style={styles.ctaOutlineText}>Hold Item</Text>
          </TouchableOpacity>
          <TouchableOpacity testID="reorder-btn" style={styles.ctaOutline} onPress={() => router.push({ pathname: '/request-call', params: { type: 'quick_reorder', productId: id } })}>
            <Text style={styles.ctaOutlineText}>Reorder</Text>
          </TouchableOpacity>
        </View>

        <View style={{ height: 40 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  loader: { flex: 1, backgroundColor: Colors.background, justifyContent: 'center', alignItems: 'center' },
  errorText: { fontSize: FontSize.md, color: Colors.textMuted },
  header: { flexDirection: 'row', justifyContent: 'space-between', paddingHorizontal: Spacing.lg, paddingTop: Spacing.sm },
  backBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: Colors.surface, alignItems: 'center', justifyContent: 'center' },
  imageContainer: { marginTop: Spacing.md },
  mainImage: { width: '100%', aspectRatio: 1, backgroundColor: Colors.surface },
  thumbRow: { paddingHorizontal: Spacing.lg, paddingVertical: Spacing.sm },
  thumb: { width: 56, height: 56, borderRadius: 8, marginRight: 8, borderWidth: 2, borderColor: 'transparent' },
  thumbActive: { borderColor: Colors.gold },
  infoSection: { paddingHorizontal: Spacing.lg, paddingTop: Spacing.lg },
  badges: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: Spacing.md },
  badge: { backgroundColor: Colors.surface, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6 },
  badgeText: { fontSize: 9, fontWeight: '700', color: Colors.textSecondary, letterSpacing: 1 },
  title: { fontSize: FontSize.xl, fontWeight: '700', color: Colors.text, marginBottom: Spacing.sm },
  description: { fontSize: FontSize.md, color: Colors.textSecondary, lineHeight: 22, marginBottom: Spacing.md },
  detailRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 12, borderTopWidth: 1, borderTopColor: Colors.border },
  detailLabel: { fontSize: FontSize.sm, color: Colors.textMuted },
  detailValue: { fontSize: FontSize.sm, color: Colors.text, fontWeight: '600' },
  tagsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: Spacing.sm },
  tag: { backgroundColor: Colors.surface, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12 },
  tagText: { fontSize: FontSize.xs, color: Colors.textMuted },
  ctaSection: { flexDirection: 'row', gap: 10, paddingHorizontal: Spacing.lg, marginTop: Spacing.md },
  ctaPrimary: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: Colors.gold, paddingVertical: 14, borderRadius: 12 },
  ctaPrimaryText: { fontSize: FontSize.md, fontWeight: '700', color: '#000' },
  ctaSecondary: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: Colors.gold + '15', paddingVertical: 14, borderRadius: 12, borderWidth: 1, borderColor: Colors.gold },
  ctaSecondaryText: { fontSize: FontSize.md, fontWeight: '600', color: Colors.gold },
  ctaOutline: { flex: 1, alignItems: 'center', paddingVertical: 12, borderRadius: 10, borderWidth: 1, borderColor: Colors.border },
  ctaOutlineText: { fontSize: FontSize.xs, fontWeight: '600', color: Colors.textSecondary },
});
