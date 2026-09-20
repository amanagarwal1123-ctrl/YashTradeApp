import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Dimensions, ActivityIndicator, ScrollView } from 'react-native';
import { Image } from 'expo-image';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, FontSize } from '../src/theme';
import { api, getProductGallery, productThumb, sizedUrl, SessionChangedError } from '../src/api';
import { cachedGet } from '../src/dataCache';
import { IMAGE_PLACEHOLDER } from '../src/imagePlaceholder';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useAuth } from '../src/context/AuthContext';

const { width: SCREEN_W, height: SCREEN_H } = Dimensions.get('window');

export default function ImageViewerScreen() {
  const { productId, batchId, startIndex: startIndexStr, ids } = useLocalSearchParams<{
    productId?: string; batchId?: string; startIndex?: string; ids?: string;
  }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const {user} = useAuth();
  const [images, setImages] = useState<any[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [photoIndex, setPhotoIndex] = useState(0);
  useEffect(() => { setPhotoIndex(0); }, [currentIndex]);

  const loadImages = useCallback(async (p: number = 1) => {
    try {
      setLoadError(false);
      if (batchId) {
        const res = await api.get(`/batches/${batchId}/images?page=${p}&limit=50`);
        const newImgs = res.images || [];
        if (p === 1) setImages(newImgs);
        else setImages(prev => [...prev, ...newImgs]);
        setHasMore(p < (res.pages || 1));
        setPage(p);
      } else if (typeof ids === 'string' && ids.length > 0) {
        // Stable ordered list passed from the source screen — guarantees continuity (shared, de-duplicated request)
        const res = await cachedGet(`/products?ids=${encodeURIComponent(ids)}`);
        setImages(res.products || []);
        setHasMore(false);
      } else if (productId) {
        // Load the selected product directly by its ID
        const p2 = await cachedGet(`/products/${productId}`);
        setImages(p2 && p2.id ? [p2] : []);
        setHasMore(false);
      } else {
        setImages([]);
      }
    } catch (e) { if (!(e instanceof SessionChangedError)) { console.error(e); setLoadError(true); } }
    finally { setLoading(false); }
  }, [batchId, ids, productId]);

  useEffect(() => { loadImages(1); }, []);

  useEffect(() => {
    if (images.length === 0) return;
    // Prioritize productId match over startIndex
    if (productId) {
      const idx = images.findIndex(i => i.id === productId);
      if (idx >= 0) { setCurrentIndex(idx); return; }
    }
    if (startIndexStr) {
      const si = parseInt(startIndexStr);
      if (!isNaN(si) && si < images.length) setCurrentIndex(si);
    }
  }, [images, productId, startIndexStr]);

  const goNext = () => {
    if (currentIndex < images.length - 1) {
      setCurrentIndex(currentIndex + 1);
      // Batch mode only: load more when near the end
      if (batchId && currentIndex >= images.length - 5 && hasMore) loadImages(page + 1);
    }
  };

  const goPrev = () => {
    if (currentIndex > 0) setCurrentIndex(currentIndex - 1);
  };

  if (loading) {
    return <View style={styles.container}><ActivityIndicator size="large" color={Colors.gold} /></View>;
  }

  if (loadError) {
    return (
      <View style={styles.container}>
        <TouchableOpacity testID="viewer-close" style={styles.closeBtn} onPress={() => router.back()}>
          <Ionicons name="close" size={28} color="#fff" />
        </TouchableOpacity>
        <Ionicons name="cloud-offline-outline" size={40} color={Colors.error} />
        <Text style={[styles.emptyText, { marginTop: 12 }]}>Could not load the product. Please check your connection.</Text>
        <TouchableOpacity testID="viewer-retry" style={styles.retryBtn} onPress={() => { setLoading(true); loadImages(1); }}>
          <Text style={styles.retryBtnText}>Retry</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const currentItem = images[currentIndex];
  if (!currentItem) {
    return (
      <View style={styles.container}>
        <TouchableOpacity style={styles.closeBtn} onPress={() => router.back()}>
          <Ionicons name="close" size={28} color="#fff" />
        </TouchableOpacity>
        <Text style={styles.emptyText}>No images available</Text>
      </View>
    );
  }

  const productPhotos = getProductGallery(currentItem);
  const fullUri = productPhotos[photoIndex] || productPhotos[0] || '';
  // thumbnail (already cached from the list) first, full-resolution photo replaces it when ready; zoom keeps the full image
  const previewUri = photoIndex === 0 ? productThumb(currentItem) : sizedUrl(fullUri, 400);
  const title = currentItem.title || '';
  const meta = [currentItem.metal_type, currentItem.category].filter(Boolean).join(' • ');

  return (
    <View style={styles.container}>
      {/* Close */}
      <TouchableOpacity testID="viewer-close" style={styles.closeBtn} onPress={() => router.back()}>
        <Ionicons name="close" size={28} color="#fff" />
      </TouchableOpacity>

      {/* Counter */}
      <View style={styles.counter}>
        <Text style={styles.counterText}>{currentIndex + 1} / {images.length}</Text>
      </View>

      {/* Main Image — Zoomable */}
      <ScrollView
        maximumZoomScale={5}
        minimumZoomScale={1}
        bouncesZoom={true}
        showsHorizontalScrollIndicator={false}
        showsVerticalScrollIndicator={false}
        contentContainerStyle={{ width: SCREEN_W, height: SCREEN_H * 0.65, alignItems: 'center', justifyContent: 'center' }}
        centerContent={true}
        pinchGestureEnabled={true}
        style={styles.imageContainer}
        testID="viewer-zoom-scroll"
      >
        <Image source={{ uri: fullUri }} placeholder={previewUri ? { uri: previewUri } : IMAGE_PLACEHOLDER} placeholderContentFit="contain" contentFit="contain"
          transition={200} cachePolicy="memory-disk" style={styles.fullImage} testID="viewer-main-image" accessibilityLabel={title || 'Product photograph'} />
      </ScrollView>

      {/* Zoom hint */}
      <View style={styles.zoomHint} pointerEvents="none">
        <Ionicons name="search" size={12} color="rgba(255,255,255,0.7)" />
        <Text style={styles.zoomHintText}>Pinch to zoom</Text>
      </View>

      {/* Navigation Arrows */}
      {currentIndex > 0 && (
        <TouchableOpacity testID="viewer-prev" style={[styles.navBtn, styles.navLeft]} onPress={goPrev}>
          <Ionicons name="chevron-back" size={32} color="#fff" />
        </TouchableOpacity>
      )}
      {currentIndex < images.length - 1 && (
        <TouchableOpacity testID="viewer-next" style={[styles.navBtn, styles.navRight]} onPress={goNext}>
          <Ionicons name="chevron-forward" size={32} color="#fff" />
        </TouchableOpacity>
      )}

      {/* Bottom Info */}
      <View style={[styles.bottomInfo, {paddingBottom: Math.max(insets.bottom, 16)}]}>
        {productPhotos.length > 1 && <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.photoStrip}>
          {productPhotos.map((uri,index)=><TouchableOpacity key={uri} testID={`viewer-photo-${index}`} accessibilityLabel={`Product photograph ${index+1}`} onPress={()=>setPhotoIndex(index)} style={[styles.photoThumb, photoIndex===index && styles.photoSelected]}><Image source={{uri: sizedUrl(uri, 54)}} placeholder={IMAGE_PLACEHOLDER} cachePolicy="memory-disk" style={styles.fullImage} contentFit="contain"/></TouchableOpacity>)}
        </ScrollView>}
        {user?.role==='admin' && <TouchableOpacity testID="viewer-manage-photos" style={styles.photoManage} onPress={()=>router.push({pathname:'/product-photos',params:{id:currentItem.id}})}><Text style={styles.imageMeta}>Manage product photographs</Text></TouchableOpacity>}
        {title ? <Text style={styles.imageTitle} numberOfLines={1}>{title}</Text> : null}
        {meta ? <Text style={styles.imageMeta}>{meta}</Text> : null}
        <View style={styles.bottomActions}>
          <TouchableOpacity testID="viewer-ask-price" style={styles.actionBtn} onPress={() => router.push({ pathname: '/request-call', params: { type: 'ask_price', productId: currentItem.id } })}>
            <Ionicons name="pricetag" size={16} color="#000" />
            <Text style={styles.actionBtnText}>Ask Price</Text>
          </TouchableOpacity>
          <TouchableOpacity testID="viewer-video-call" style={[styles.actionBtn, { backgroundColor: 'transparent', borderWidth: 1, borderColor: Colors.gold }]} onPress={() => router.push({ pathname: '/request-call', params: { type: 'video_call', productId: currentItem.id } })}>
            <Ionicons name="videocam" size={16} color={Colors.gold} />
            <Text style={[styles.actionBtnText, { color: Colors.gold }]}>Video Call</Text>
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  photoStrip: { gap: 10, paddingBottom: 14 },
  photoThumb: { width: 54, height: 54, borderRadius: 8, borderWidth: 1, borderColor: Colors.border },
  photoSelected: { borderColor: Colors.gold, borderWidth: 2 },
  photoManage: { minHeight: 44, justifyContent: 'center' },
  container: { flex: 1, backgroundColor: '#000', justifyContent: 'center', alignItems: 'center' },
  closeBtn: { position: 'absolute', top: 50, right: 20, zIndex: 10, width: 44, height: 44, borderRadius: 22, backgroundColor: 'rgba(255,255,255,0.15)', alignItems: 'center', justifyContent: 'center' },
  counter: { position: 'absolute', top: 56, left: 0, right: 0, zIndex: 10, alignItems: 'center' },
  counterText: { fontSize: FontSize.sm, color: 'rgba(255,255,255,0.7)', fontWeight: '600' },
  imageContainer: { width: SCREEN_W, height: SCREEN_H * 0.65 },
  fullImage: { width: '100%', height: '100%' },
  navBtn: { position: 'absolute', top: '45%', zIndex: 10, width: 48, height: 48, borderRadius: 24, backgroundColor: 'rgba(255,255,255,0.1)', alignItems: 'center', justifyContent: 'center' },
  navLeft: { left: 12 },
  navRight: { right: 12 },
  bottomInfo: { position: 'absolute', bottom: 0, left: 0, right: 0, paddingHorizontal: 24, paddingBottom: 40, paddingTop: 20, backgroundColor: 'rgba(0,0,0,0.7)' },
  imageTitle: { fontSize: FontSize.base, fontWeight: '600', color: '#fff', marginBottom: 4 },
  imageMeta: { fontSize: FontSize.sm, color: 'rgba(255,255,255,0.6)', textTransform: 'capitalize', marginBottom: 12 },
  bottomActions: { flexDirection: 'row', gap: 10 },
  actionBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: Colors.gold, paddingVertical: 12, borderRadius: 10 },
  actionBtnText: { fontSize: FontSize.sm, fontWeight: '700', color: '#000' },
  emptyText: { fontSize: FontSize.md, color: '#fff', textAlign: 'center', paddingHorizontal: 32 },
  retryBtn: { marginTop: 16, backgroundColor: Colors.gold, paddingHorizontal: 24, paddingVertical: 10, borderRadius: 10 },
  retryBtnText: { fontSize: FontSize.sm, fontWeight: '700', color: '#000' },
  zoomHint: { position: 'absolute', top: SCREEN_H * 0.65 - 30, alignSelf: 'center', flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: 'rgba(0,0,0,0.55)', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12 },
  zoomHintText: { color: 'rgba(255,255,255,0.7)', fontSize: 11, fontWeight: '600' },
});
