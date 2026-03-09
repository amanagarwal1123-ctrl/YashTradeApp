import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Image, ActivityIndicator, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api, getImageUrl } from '../src/api';

export default function CartScreen() {
  const router = useRouter();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const loadCart = async () => {
    try {
      const res = await api.get('/cart');
      setItems(res.items || []);
    } catch {}
    finally { setLoading(false); }
  };

  useEffect(() => { loadCart(); }, []);

  const removeItem = async (itemId: string) => {
    try {
      await api.delete(`/cart/${itemId}`);
      setItems(prev => prev.filter(i => i.id !== itemId));
    } catch {}
  };

  const submitCart = () => {
    if (items.length === 0) return;
    Alert.alert('Submit Selection', `Send ${items.length} item(s) to our team? We will prepare a bill and contact you.`, [
      { text: 'Cancel' },
      { text: 'Submit', onPress: async () => {
        setSubmitting(true);
        try {
          await api.post('/cart/submit', { notes: '' });
          setSubmitted(true);
        } catch (e: any) { Alert.alert('Error', e.message); }
        finally { setSubmitting(false); }
      }}
    ]);
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity testID="cart-back" onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color={Colors.text} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>My Selection</Text>
        <Text style={styles.headerCount}>{items.length} items</Text>
      </View>

      {/* POINT 5: Thank you screen after submit */}
      {submitted ? (
        <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', paddingHorizontal: Spacing.xl }}>
          <View style={{ width: 96, height: 96, borderRadius: 48, backgroundColor: Colors.success, alignItems: 'center', justifyContent: 'center', marginBottom: Spacing.xl }}>
            <Ionicons name="checkmark" size={56} color="#fff" />
          </View>
          <Text style={{ fontSize: FontSize.xxl, fontWeight: '700', color: Colors.text, marginBottom: 8, textAlign: 'center' }}>Thank You!</Text>
          <Text style={{ fontSize: FontSize.lg, color: Colors.gold, fontWeight: '600', textAlign: 'center', marginBottom: Spacing.md }}>Your order has been placed on Yash Trade</Text>
          <Text style={{ fontSize: FontSize.md, color: Colors.textSecondary, textAlign: 'center', lineHeight: 22, marginBottom: Spacing.xl }}>We will connect with you very soon to confirm your selection and prepare the billing.</Text>
          <View style={{ width: 60, height: 2, backgroundColor: Colors.gold, borderRadius: 1, marginBottom: Spacing.xl }} />
          <Text style={{ fontSize: FontSize.md, color: Colors.textMuted, textAlign: 'center' }}>Thank you for choosing</Text>
          <Text style={{ fontSize: FontSize.xl, fontWeight: '700', color: Colors.gold, letterSpacing: 3, marginTop: 4 }}>YASH TRADE</Text>
          <TouchableOpacity style={{ marginTop: Spacing.xl, backgroundColor: Colors.gold, paddingVertical: 14, paddingHorizontal: 40, borderRadius: 12 }} onPress={() => router.replace('/(tabs)')}>
            <Text style={{ fontSize: FontSize.md, fontWeight: '700', color: '#000' }}>Back to Home</Text>
          </TouchableOpacity>
        </View>
      ) : (
      <>
      {loading ? <ActivityIndicator color={Colors.gold} style={{ marginTop: 40 }} /> : (
        <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
          {items.length === 0 && (
            <View style={styles.empty}>
              <Ionicons name="cart-outline" size={56} color={Colors.textMuted} />
              <Text style={styles.emptyTitle}>No items selected</Text>
              <Text style={styles.emptyHint}>Browse the collection and add items you like</Text>
              <TouchableOpacity style={styles.browseBtn} onPress={() => router.push('/(tabs)/feed')}>
                <Text style={styles.browseBtnText}>Browse Collection</Text>
              </TouchableOpacity>
            </View>
          )}

          {items.map(item => {
            const p = item.product || {};
            return (
              <View key={item.id} style={styles.card} testID={`cart-item-${item.id}`}>
                <Image source={{ uri: getImageUrl(p, true) }} style={styles.cardImage} />
                <View style={styles.cardInfo}>
                  <Text style={styles.cardTitle} numberOfLines={2}>{p.title || 'Product'}</Text>
                  <Text style={styles.cardMeta}>{p.metal_type} {p.category ? `• ${p.category}` : ''}</Text>
                  {p.approx_weight ? <Text style={styles.cardWeight}>{p.approx_weight}</Text> : null}
                  {p.purity ? <Text style={styles.cardDetail}>Purity: {p.purity}</Text> : null}
                  <Text style={styles.cardQty}>Qty: {item.quantity}</Text>
                </View>
                <TouchableOpacity style={styles.removeBtn} onPress={() => removeItem(item.id)}>
                  <Ionicons name="trash-outline" size={18} color={Colors.error} />
                </TouchableOpacity>
              </View>
            );
          })}

          {items.length > 0 && (
            <View style={styles.submitSection}>
              <View style={styles.submitInfo}>
                <Ionicons name="information-circle" size={16} color={Colors.info} />
                <Text style={styles.submitInfoText}>Our team will prepare a bill and contact you after reviewing your selection.</Text>
              </View>
              <TouchableOpacity testID="submit-cart-btn" style={styles.submitBtn} onPress={submitCart} disabled={submitting}>
                {submitting ? <ActivityIndicator color="#000" /> : (
                  <>
                    <Ionicons name="send" size={18} color="#000" />
                    <Text style={styles.submitBtnText}>SUBMIT SELECTION ({items.length} items)</Text>
                  </>
                )}
              </TouchableOpacity>
            </View>
          )}

          <View style={{ height: 40 }} />
        </ScrollView>
      )}
      </>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md },
  backBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: Colors.surface, alignItems: 'center', justifyContent: 'center' },
  headerTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text },
  headerCount: { fontSize: FontSize.sm, color: Colors.textSecondary },
  content: { paddingHorizontal: Spacing.lg },
  empty: { alignItems: 'center', paddingVertical: 60 },
  emptyTitle: { fontSize: FontSize.lg, fontWeight: '600', color: Colors.textMuted, marginTop: Spacing.md },
  emptyHint: { fontSize: FontSize.sm, color: Colors.textMuted, marginTop: 4 },
  browseBtn: { marginTop: Spacing.lg, backgroundColor: Colors.gold, paddingHorizontal: 24, paddingVertical: 12, borderRadius: 10 },
  browseBtnText: { fontSize: FontSize.sm, fontWeight: '700', color: '#000' },
  card: { flexDirection: 'row', backgroundColor: Colors.card, borderRadius: 14, marginBottom: Spacing.sm, overflow: 'hidden', borderWidth: 1, borderColor: Colors.cardBorder },
  cardImage: { width: 90, height: 90, backgroundColor: Colors.surface },
  cardInfo: { flex: 1, padding: Spacing.sm },
  cardTitle: { fontSize: FontSize.sm, fontWeight: '600', color: Colors.text },
  cardMeta: { fontSize: FontSize.xs, color: Colors.textSecondary, textTransform: 'capitalize', marginTop: 2 },
  cardWeight: { fontSize: FontSize.xs, color: Colors.textMuted, marginTop: 1 },
  cardDetail: { fontSize: FontSize.xs, color: Colors.gold, marginTop: 1 },
  cardQty: { fontSize: FontSize.xs, color: Colors.textSecondary, marginTop: 2, fontWeight: '600' },
  removeBtn: { padding: Spacing.md, justifyContent: 'center' },
  submitSection: { marginTop: Spacing.lg },
  submitInfo: { flexDirection: 'row', gap: 8, backgroundColor: Colors.info + '10', padding: Spacing.md, borderRadius: 12, marginBottom: Spacing.md },
  submitInfoText: { flex: 1, fontSize: FontSize.sm, color: Colors.textSecondary, lineHeight: 20 },
  submitBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: Colors.gold, paddingVertical: 16, borderRadius: 12 },
  submitBtnText: { fontSize: FontSize.sm, fontWeight: '700', color: '#000', letterSpacing: 1 },
});
