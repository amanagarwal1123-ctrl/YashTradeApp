import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator, Image, Dimensions } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api } from '../src/api';
import { useLang } from '../src/context/LanguageContext';

const { width } = Dimensions.get('window');

export default function BrandsScreen() {
  const router = useRouter();
  const { language } = useLang();
  const [brands, setBrands] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get('/brands');
        setBrands(res.brands || []);
      } catch (e) { console.error(e); }
      finally { setLoading(false); }
    })();
  }, []);

  const T: Record<string, any> = {
    en: { title: 'Our Brands', subtitle: 'We are Authorized Dealers of These Premium Brands', empty: 'Brand posters coming soon. Admin can upload brand images from the panel.' },
    hi: { title: '\u0939\u092e\u093e\u0930\u0947 \u092c\u094d\u0930\u093e\u0902\u0921', subtitle: '\u0939\u092e \u0907\u0928 \u092a\u094d\u0930\u0940\u092e\u093f\u092f\u092e \u092c\u094d\u0930\u093e\u0902\u0921\u094d\u0938 \u0915\u0947 \u0905\u0927\u093f\u0915\u0943\u0924 \u0921\u0940\u0932\u0930 \u0939\u0948\u0902', empty: '\u092c\u094d\u0930\u093e\u0902\u0921 \u092a\u094b\u0938\u094d\u091f\u0930 \u091c\u0932\u094d\u0926 \u0906 \u0930\u0939\u0947 \u0939\u0948\u0902\u0964' },
    pa: { title: '\u0a38\u0a3e\u0a21\u0a47 \u0a2c\u0a4d\u0a30\u0a3e\u0a02\u0a21', subtitle: '\u0a05\u0a38\u0a40\u0a02 \u0a07\u0a28\u0a4d\u0a39\u0a3e\u0a02 \u0a2a\u0a4d\u0a30\u0a40\u0a2e\u0a40\u0a05\u0a2e \u0a2c\u0a4d\u0a30\u0a3e\u0a02\u0a21\u0a3e\u0a02 \u0a26\u0a47 \u0a05\u0a27\u0a3f\u0a15\u0a3e\u0a30\u0a24 \u0a21\u0a40\u0a32\u0a30 \u0a39\u0a3e\u0a02', empty: '\u0a2c\u0a4d\u0a30\u0a3e\u0a02\u0a21 \u0a2a\u0a4b\u0a38\u0a1f\u0a30 \u0a1c\u0a32\u0a26 \u0a06 \u0a30\u0a39\u0a47 \u0a39\u0a28\u0964' },
  };
  const t = T[language] || T.en;

  if (loading) return <View style={st.loader}><ActivityIndicator size="large" color={Colors.gold} /></View>;

  return (
    <SafeAreaView style={st.container} edges={['top']}>
      <View style={st.header}>
        <TouchableOpacity onPress={() => router.back()}><Ionicons name="arrow-back" size={22} color={Colors.text} /></TouchableOpacity>
        <Text style={st.headerTitle}>{t.title}</Text>
        <View style={{ width: 22 }} />
      </View>
      <ScrollView contentContainerStyle={st.content}>
        {/* Header banner */}
        <View style={st.bannerBox}>
          <Ionicons name="shield-checkmark" size={32} color={Colors.gold} />
          <Text style={st.bannerTitle}>{t.subtitle}</Text>
        </View>

        {/* Brand poster images - full width poster style */}
        {brands.map(b => (
          <View key={b.id} style={st.posterCard} data-testid={`brand-${b.id}`}>
            {b.logo_url ? (
              <Image source={{ uri: b.logo_url }} style={st.posterImage} resizeMode="cover" />
            ) : (
              <View style={st.posterPlaceholder}>
                <Ionicons name="star" size={40} color={Colors.gold} />
                <Text style={st.placeholderName}>{b.name}</Text>
              </View>
            )}
            {b.name && <Text style={st.posterName}>{b.name}</Text>}
            {b.description ? <Text style={st.posterDesc}>{b.description}</Text> : null}
          </View>
        ))}

        {brands.length === 0 && (
          <View style={st.emptyBox}>
            <Ionicons name="star-outline" size={48} color={Colors.textMuted} />
            <Text style={st.emptyText}>{t.empty}</Text>
            <Text style={st.emptyHint}>Admin Panel {'>'} Content {'>'} Brands {'>'} Upload brand poster images</Text>
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  loader: { flex: 1, backgroundColor: Colors.background, justifyContent: 'center', alignItems: 'center' },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md, borderBottomWidth: 1, borderBottomColor: Colors.border },
  headerTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text },
  content: { padding: Spacing.lg },
  bannerBox: { alignItems: 'center', paddingVertical: Spacing.xl, marginBottom: Spacing.lg, borderBottomWidth: 1, borderBottomColor: Colors.borderGold },
  bannerTitle: { fontSize: FontSize.base, fontWeight: '600', color: Colors.gold, textAlign: 'center', marginTop: Spacing.sm, letterSpacing: 0.5 },
  posterCard: { backgroundColor: Colors.card, borderRadius: 16, overflow: 'hidden', marginBottom: Spacing.lg, borderWidth: 1, borderColor: Colors.cardBorder },
  posterImage: { width: '100%', height: width * 0.6, backgroundColor: Colors.surface },
  posterPlaceholder: { width: '100%', height: 180, backgroundColor: Colors.gold + '08', alignItems: 'center', justifyContent: 'center', gap: 8 },
  placeholderName: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.gold },
  posterName: { fontSize: FontSize.base, fontWeight: '700', color: Colors.text, padding: Spacing.md, paddingBottom: 4 },
  posterDesc: { fontSize: FontSize.sm, color: Colors.textSecondary, paddingHorizontal: Spacing.md, paddingBottom: Spacing.md },
  emptyBox: { alignItems: 'center', marginTop: 60, gap: 12, paddingHorizontal: Spacing.lg },
  emptyText: { fontSize: FontSize.md, color: Colors.textMuted, textAlign: 'center' },
  emptyHint: { fontSize: FontSize.xs, color: Colors.textMuted, textAlign: 'center', fontStyle: 'italic' },
});
