import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, Image, TouchableOpacity, ActivityIndicator, Alert, Dimensions } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../../src/theme';
import { api, getImageUrl } from '../../src/api';

const { width: SCREEN_W } = Dimensions.get('window');

export default function ProductDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [product, setProduct] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [currentImage, setCurrentImage] = useState(0);
  const [wishlisted, setWishlisted] = useState(false);
  const [addedToCart, setAddedToCart] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const p = await api.get(`/products/${id}`);
        setProduct(p);
        // Check wishlist status
        try {
          const wl = await api.get('/wishlist');
          setWishlisted((wl.products || []).some((w: any) => w.id === id));
        } catch {}
      } catch {} finally { setLoading(false); }
    })();
  }, [id]);

  const toggleWishlist = async () => {
    try {
      const r = await api.post(`/wishlist/toggle?product_id=${id}`);
      setWishlisted(r.wishlisted);
    } catch {}
  };

  const addToCart = async () => {
    try {
      await api.post('/cart/add', { product_id: id });
      setAddedToCart(true);
      setTimeout(() => setAddedToCart(false), 3000);
    } catch {}
  };

  if (loading) return <View style={styles.loader}><ActivityIndicator size="large" color={Colors.gold} /></View>;
  if (!product) return <View style={styles.loader}><Text style={styles.errorText}>Product not found</Text></View>;

  const images = product.images || [];
  const hasStorageImage = !!product.storage_path;
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
          {/* POINT 9: Wishlist heart with visible color toggle */}
          <TouchableOpacity testID="wishlist-btn" style={styles.backBtn} onPress={toggleWishlist}>
            <Ionicons
              name={wishlisted ? 'heart' : 'heart-outline'}
              size={24}
              color={wishlisted ? Colors.pastelPink : Colors.text}
            />
          </TouchableOpacity>
        </View>

        {/* Zoomable Image */}
        <View style={styles.imageContainer}>
          {displayImageUri ? (
            <View style={{ width: '100%', aspectRatio: 1 }}>
              <ScrollView
                maximumZoomScale={4}
                minimumZoomScale={1}
                bouncesZoom={true}
                showsHorizontalScrollIndicator={false}
                showsVerticalScrollIndicator={false}
                contentContainerStyle={{ width: '100%', aspectRatio: 1 }}
                pinchGestureEnabled={true}
                style={{ width: '100%', aspectRatio: 1 }}
              >
                <Image source={{ uri: displayImageUri }} style={styles.mainImage} resizeMode="contain" data-testid="product-main-image" />
              </ScrollView>
              <View style={styles.zoomHint} pointerEvents="none">
                <Ionicons name="search" size={14} color="rgba(255,255,255,0.8)" />
                <Text style={styles.zoomHintText}>Pinch to zoom</Text>
              </View>
            </View>
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

        {/* POINT 4: Cart added confirmation banner */}
        {addedToCart && (
          <View style={styles.cartConfirmBanner} data-testid="cart-confirm-banner">
            <Ionicons name="checkmark-circle" size={20} color="#fff" />
            <Text style={styles.cartConfirmText}>Product added to your cart!</Text>
          </View>
        )}

        {/* Info */}
        <View style={styles.infoSection}>
          <View style={styles.badges}>
            <View style={[styles.badge, { backgroundColor: Colors.gold + '20' }]}><Text style={[styles.badgeText, { color: Colors.gold }]}>{product.metal_type?.toUpperCase()}</Text></View>
            <View style={styles.badge}><Text style={styles.badgeText}>{product.category?.replace(/_/g, ' ').toUpperCase()}</Text></View>
            {product.is_new_arrival && <View style={[styles.badge, { backgroundColor: Colors.pastelGreen + '30' }]}><Text style={[styles.badgeText, { color: Colors.pastelGreen }]}>NEW</Text></View>}
            {product.stock_status === 'limited' && <View style={[styles.badge, { backgroundColor: Colors.pastelOrange + '30' }]}><Text style={[styles.badgeText, { color: Colors.pastelOrange }]}>LIMITED</Text></View>}
          </View>

          <Text style={styles.title}>{product.title}</Text>
          {product.description ? <Text style={styles.description}>{product.description}</Text> : null}

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

        {/* POINT 1: CTAs — Add to Cart FIRST, Ask Price second */}
        <View style={styles.ctaSection}>
          <TouchableOpacity testID="add-to-cart-btn" style={styles.ctaPrimary} onPress={addToCart}>
            <Ionicons name="cart" size={18} color="#000" />
            <Text style={styles.ctaPrimaryText}>Add to Cart</Text>
          </TouchableOpacity>
          <TouchableOpacity testID="ask-price-btn" style={styles.ctaSecondary} onPress={() => router.push({ pathname: '/request-call', params: { type: 'ask_price', productId: id } })}>
            <Ionicons name="pricetag" size={18} color={Colors.gold} />
            <Text style={styles.ctaSecondaryText}>Ask Price</Text>
          </TouchableOpacity>
        </View>

        {/* AI Try-On button for wearable categories */}
        {product.category && ['payal', 'chain', 'necklace', 'bracelet', 'bangles', 'kadaa', 'ring', 'earrings', 'pendant', 'nose_ring', 'toe_rings', 'articles'].includes(product.category.toLowerCase()) && (
          <View style={styles.ctaSection}>
            <TouchableOpacity testID="try-on-btn" style={styles.tryOnBtn} onPress={() => router.push({ pathname: '/try-on', params: { productId: id } })}>
              <Ionicons name="sparkles" size={18} color="#fff" />
              <Text style={styles.tryOnBtnText}>AI Try-On Preview</Text>
            </TouchableOpacity>
          </View>
        )}

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
  zoomHint: { position: 'absolute', bottom: 12, right: 12, flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: 'rgba(0,0,0,0.55)', paddingHorizontal: 10, paddingVertical: 5, borderRadius: 16 },
  zoomHintText: { color: 'rgba(255,255,255,0.8)', fontSize: 11, fontWeight: '600' },
  thumbRow: { paddingHorizontal: Spacing.lg, paddingVertical: Spacing.sm },
  thumb: { width: 56, height: 56, borderRadius: 8, marginRight: 8, borderWidth: 2, borderColor: 'transparent' },
  thumbActive: { borderColor: Colors.gold },
  cartConfirmBanner: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, marginHorizontal: Spacing.lg, marginTop: Spacing.md, paddingVertical: 12, backgroundColor: Colors.success, borderRadius: 12 },
  cartConfirmText: { color: '#fff', fontWeight: '700', fontSize: FontSize.md },
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
  tryOnBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: Colors.pastelPurple, paddingVertical: 14, borderRadius: 12 },
  tryOnBtnText: { fontSize: FontSize.md, fontWeight: '700', color: '#fff' },
});
