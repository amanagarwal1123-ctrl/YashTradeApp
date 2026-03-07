import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Image, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api, getImageUrl } from '../src/api';

export default function WishlistScreen() {
  const router = useRouter();
  const [products, setProducts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get('/wishlist');
        setProducts(res.products || []);
      } catch {}
      finally { setLoading(false); }
    })();
  }, []);

  const removeItem = async (productId: string) => {
    try {
      await api.post(`/wishlist/toggle?product_id=${productId}`);
      setProducts(prev => prev.filter(p => p.id !== productId));
    } catch {}
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity testID="wishlist-back" onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color={Colors.text} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Wishlist</Text>
        <View style={{ width: 44 }} />
      </View>

      {loading ? (
        <ActivityIndicator color={Colors.gold} style={{ marginTop: 40 }} />
      ) : (
        <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
          {products.length === 0 && (
            <View style={styles.empty}>
              <Ionicons name="heart-outline" size={48} color={Colors.textMuted} />
              <Text style={styles.emptyText}>No wishlisted items</Text>
              <TouchableOpacity style={styles.browseBtn} onPress={() => router.push('/(tabs)/feed')}>
                <Text style={styles.browseBtnText}>Browse Collection</Text>
              </TouchableOpacity>
            </View>
          )}
          {products.map(p => (
            <TouchableOpacity
              key={p.id}
              testID={`wishlist-item-${p.id}`}
              style={styles.card}
              onPress={() => router.push({ pathname: '/product/[id]', params: { id: p.id } })}
            >
              <Image source={{ uri: getImageUrl(p, true) }} style={styles.cardImage} />
              <View style={styles.cardInfo}>
                <Text style={styles.cardTitle} numberOfLines={2}>{p.title}</Text>
                <Text style={styles.cardMeta}>{p.metal_type} {p.category ? `• ${p.category}` : ''}</Text>
                {p.approx_weight ? <Text style={styles.cardWeight}>{p.approx_weight}</Text> : null}
              </View>
              <TouchableOpacity style={styles.removeBtn} onPress={() => removeItem(p.id)}>
                <Ionicons name="heart-dislike" size={18} color={Colors.error} />
              </TouchableOpacity>
            </TouchableOpacity>
          ))}
          <View style={{ height: 40 }} />
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md },
  backBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: Colors.surface, alignItems: 'center', justifyContent: 'center' },
  headerTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text },
  content: { paddingHorizontal: Spacing.lg },
  empty: { alignItems: 'center', paddingVertical: 60 },
  emptyText: { fontSize: FontSize.md, color: Colors.textMuted, marginTop: Spacing.md },
  browseBtn: { marginTop: Spacing.md, backgroundColor: Colors.gold, paddingHorizontal: 24, paddingVertical: 12, borderRadius: 10 },
  browseBtnText: { fontSize: FontSize.sm, fontWeight: '700', color: '#000' },
  card: { flexDirection: 'row', alignItems: 'center', backgroundColor: Colors.card, borderRadius: 14, marginBottom: Spacing.sm, overflow: 'hidden', borderWidth: 1, borderColor: Colors.cardBorder },
  cardImage: { width: 80, height: 80, backgroundColor: Colors.surface },
  cardInfo: { flex: 1, padding: Spacing.sm },
  cardTitle: { fontSize: FontSize.sm, fontWeight: '600', color: Colors.text, marginBottom: 2 },
  cardMeta: { fontSize: FontSize.xs, color: Colors.textSecondary, textTransform: 'capitalize' },
  cardWeight: { fontSize: FontSize.xs, color: Colors.textMuted, marginTop: 2 },
  removeBtn: { padding: Spacing.md },
});
