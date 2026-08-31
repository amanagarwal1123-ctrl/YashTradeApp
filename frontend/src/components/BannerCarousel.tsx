import React, { useEffect, useRef, useState, useCallback } from 'react';
import { View, Text, StyleSheet, FlatList, TouchableOpacity, Image, Linking, useWindowDimensions } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../theme';
import { api, resolveFileUrl } from '../api';

interface Banner {
  id: string;
  title: string;
  subtitle?: string;
  image_url?: string;
  cta_label?: string;
  cta_type?: string;
  cta_target?: string;
}

const AUTO_ROTATE_MS = 4500;
const METALS = ['silver', 'gold', 'diamond'];

export default function BannerCarousel() {
  const router = useRouter();
  const { width: windowWidth } = useWindowDimensions();
  const [banners, setBanners] = useState<Banner[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeIndex, setActiveIndex] = useState(0);
  const [failedImages, setFailedImages] = useState<Record<string, boolean>>({});
  const [containerWidth, setContainerWidth] = useState(windowWidth - Spacing.lg * 2);
  const listRef = useRef<FlatList<Banner>>(null);
  const indexRef = useRef(0);

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get('/banners');
        setBanners(res.banners || []);
      } catch {
        // Banners are non-critical decoration — fail silently and hide the section
        setBanners([]);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // Auto-rotation
  useEffect(() => {
    if (banners.length < 2) return;
    const timer = setInterval(() => {
      const next = (indexRef.current + 1) % banners.length;
      indexRef.current = next;
      setActiveIndex(next);
      listRef.current?.scrollToIndex({ index: next, animated: true });
    }, AUTO_ROTATE_MS);
    return () => clearInterval(timer);
  }, [banners.length, containerWidth]);

  const onMomentumEnd = useCallback((e: any) => {
    const idx = Math.max(0, Math.min(banners.length - 1, Math.round(e.nativeEvent.contentOffset.x / containerWidth)));
    indexRef.current = idx;
    setActiveIndex(idx);
  }, [banners.length, containerWidth]);

  const handlePress = (b: Banner) => {
    const target = (b.cta_target || '').trim();
    if (b.cta_type === 'product' && target) {
      router.push({ pathname: '/product/[id]', params: { id: target } });
    } else if (b.cta_type === 'feed') {
      if (target && METALS.includes(target.toLowerCase())) {
        router.push({ pathname: '/(tabs)/feed', params: { metal: target.toLowerCase() } });
      } else if (target) {
        router.push({ pathname: '/(tabs)/feed', params: { category: target } });
      } else {
        router.push('/(tabs)/feed');
      }
    } else if (b.cta_type === 'url' && target) {
      Linking.openURL(target).catch(() => {});
    }
  };

  if (loading) {
    return (
      <View testID="banner-loading" style={[styles.skeleton, { width: '100%' }]} />
    );
  }

  // No placeholder banners — hide the section entirely when empty
  if (banners.length === 0) return null;

  const renderBanner = ({ item }: { item: Banner }) => {
    const imageUri = resolveFileUrl(item.image_url || '');
    const imageFailed = !imageUri || failedImages[item.id];
    return (
      <TouchableOpacity
        testID={`banner-${item.id}`}
        activeOpacity={item.cta_type && item.cta_type !== 'none' ? 0.85 : 1}
        onPress={() => handlePress(item)}
        style={[styles.bannerItem, { width: containerWidth }]}
      >
        {imageFailed ? (
          <View style={styles.imageFallback}>
            <Ionicons name="image-outline" size={32} color={Colors.textMuted} />
          </View>
        ) : (
          <Image
            source={{ uri: imageUri }}
            style={styles.bannerImage}
            resizeMode="cover"
            onError={() => setFailedImages(prev => ({ ...prev, [item.id]: true }))}
          />
        )}
        <View style={styles.overlay}>
          <Text style={styles.bannerTitle} numberOfLines={1}>{item.title}</Text>
          {item.subtitle ? <Text style={styles.bannerSubtitle} numberOfLines={1}>{item.subtitle}</Text> : null}
          {item.cta_label ? (
            <View style={styles.ctaChip}>
              <Text style={styles.ctaChipText}>{item.cta_label}</Text>
              <Ionicons name="chevron-forward" size={12} color="#000" />
            </View>
          ) : null}
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <View
      testID="banner-carousel"
      style={styles.container}
      onLayout={(e) => {
        const w = e.nativeEvent.layout.width;
        if (w > 0 && Math.abs(w - containerWidth) > 1) setContainerWidth(w);
      }}
    >
      <FlatList
        ref={listRef}
        data={banners}
        keyExtractor={b => b.id}
        renderItem={renderBanner}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        onMomentumScrollEnd={onMomentumEnd}
        getItemLayout={(_, index) => ({ length: containerWidth, offset: containerWidth * index, index })}
        snapToInterval={containerWidth}
        decelerationRate="fast"
        bounces={false}
      />
      {banners.length > 1 && (
        <View style={styles.dotsRow}>
          {banners.map((b, i) => (
            <View key={b.id} style={[styles.dot, i === activeIndex && styles.dotActive]} />
          ))}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { marginTop: Spacing.md },
  skeleton: { marginTop: Spacing.md, aspectRatio: 2.2, borderRadius: 16, backgroundColor: Colors.surface },
  bannerItem: { aspectRatio: 2.2, borderRadius: 16, overflow: 'hidden', backgroundColor: Colors.surface },
  bannerImage: { width: '100%', height: '100%' },
  imageFallback: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: Colors.surface },
  overlay: { position: 'absolute', left: 0, right: 0, bottom: 0, paddingHorizontal: Spacing.md, paddingVertical: 10, backgroundColor: 'rgba(0,0,0,0.45)' },
  bannerTitle: { fontSize: FontSize.md, fontWeight: '700', color: '#fff' },
  bannerSubtitle: { fontSize: FontSize.xs, color: 'rgba(255,255,255,0.85)', marginTop: 1 },
  ctaChip: { flexDirection: 'row', alignItems: 'center', gap: 2, alignSelf: 'flex-start', backgroundColor: Colors.gold, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12, marginTop: 6 },
  ctaChipText: { fontSize: FontSize.xs, fontWeight: '700', color: '#000' },
  dotsRow: { flexDirection: 'row', justifyContent: 'center', gap: 6, marginTop: 8 },
  dot: { width: 6, height: 6, borderRadius: 3, backgroundColor: Colors.border },
  dotActive: { width: 16, backgroundColor: Colors.gold },
});
