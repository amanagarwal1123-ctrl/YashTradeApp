import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Image, Dimensions, ActivityIndicator, FlatList, ScrollView } from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, FontSize } from '../src/theme';
import { api, getImageUrl } from '../src/api';

const { width: SCREEN_W, height: SCREEN_H } = Dimensions.get('window');

export default function ImageViewerScreen() {
  const { productId, batchId, startIndex: startIndexStr } = useLocalSearchParams<{
    productId?: string; batchId?: string; startIndex?: string;
  }>();
  const router = useRouter();
  const [images, setImages] = useState<any[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);

  const loadImages = useCallback(async (p: number = 1) => {
    try {
      let res;
      if (batchId) {
        res = await api.get(`/batches/${batchId}/images?page=${p}&limit=50`);
        const newImgs = res.images || [];
        if (p === 1) setImages(newImgs);
        else setImages(prev => [...prev, ...newImgs]);
        setHasMore(p < (res.pages || 1));
      } else {
        res = await api.get(`/products?page=${p}&limit=50`);
        const newImgs = res.products || [];
        if (p === 1) setImages(newImgs);
        else setImages(prev => [...prev, ...newImgs]);
        setHasMore(p < (res.pages || 1));
      }
      setPage(p);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [batchId]);

  useEffect(() => { loadImages(1); }, []);

  useEffect(() => {
    if (images.length === 0) return;
    // Fix #4: prioritize productId match over startIndex
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
      // Load more when near the end
      if (currentIndex >= images.length - 5 && hasMore) loadImages(page + 1);
    }
  };

  const goPrev = () => {
    if (currentIndex > 0) setCurrentIndex(currentIndex - 1);
  };

  if (loading) {
    return <View style={styles.container}><ActivityIndicator size="large" color={Colors.gold} /></View>;
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

  const fullUri = getImageUrl(currentItem, false);
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
        data-testid="viewer-zoom-scroll"
      >
        <Image source={{ uri: fullUri }} style={styles.fullImage} resizeMode="contain" data-testid="viewer-main-image" />
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
      <View style={styles.bottomInfo}>
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
  emptyText: { fontSize: FontSize.md, color: '#fff' },
  zoomHint: { position: 'absolute', top: SCREEN_H * 0.65 - 30, alignSelf: 'center', flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: 'rgba(0,0,0,0.55)', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12 },
  zoomHintText: { color: 'rgba(255,255,255,0.7)', fontSize: 11, fontWeight: '600' },
});
