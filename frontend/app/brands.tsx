import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator, Image } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api } from '../src/api';
import { useLang } from '../src/context/LanguageContext';

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
    en: { title: 'Our Brands', subtitle: 'We are authorized dealers of these premium brands', empty: 'Brand logos coming soon. Admin can add brands from the panel.' },
    hi: { title: '\u0939\u092e\u093e\u0930\u0947 \u092c\u094d\u0930\u093e\u0902\u0921', subtitle: '\u0939\u092e \u0907\u0928 \u092a\u094d\u0930\u0940\u092e\u093f\u092f\u092e \u092c\u094d\u0930\u093e\u0902\u0921\u094d\u0938 \u0915\u0947 \u0905\u0927\u093f\u0915\u0943\u0924 \u0921\u0940\u0932\u0930 \u0939\u0948\u0902', empty: '\u092c\u094d\u0930\u093e\u0902\u0921 \u0932\u094b\u0917\u094b \u091c\u0932\u094d\u0926 \u0906 \u0930\u0939\u0947 \u0939\u0948\u0902\u0964' },
    pa: { title: '\u0a38\u0a3e\u0a21\u0a47 \u0a2c\u0a4d\u0a30\u0a3e\u0a02\u0a21', subtitle: '\u0a05\u0a38\u0a40\u0a02 \u0a07\u0a28\u0a4d\u0a39\u0a3e\u0a02 \u0a2a\u0a4d\u0a30\u0a40\u0a2e\u0a40\u0a05\u0a2e \u0a2c\u0a4d\u0a30\u0a3e\u0a02\u0a21\u0a3e\u0a02 \u0a26\u0a47 \u0a05\u0a27\u0a3f\u0a15\u0a3e\u0a30\u0a24 \u0a21\u0a40\u0a32\u0a30 \u0a39\u0a3e\u0a02', empty: '\u0a2c\u0a4d\u0a30\u0a3e\u0a02\u0a21 \u0a32\u0a4b\u0a17\u0a4b \u0a1c\u0a32\u0a26 \u0a06 \u0a30\u0a39\u0a47 \u0a39\u0a28\u0964' },
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
        <Text style={st.subtitle}>{t.subtitle}</Text>
        <View style={st.grid}>
          {brands.map(b => (
            <View key={b.id} style={st.brandCard} data-testid={`brand-${b.id}`}>
              {b.logo_url ? <Image source={{ uri: b.logo_url }} style={st.logo} resizeMode="contain" /> : (
                <View style={st.logoPlaceholder}><Ionicons name="star" size={32} color={Colors.gold} /></View>
              )}
              <Text style={st.brandName}>{b.name}</Text>
              {b.description ? <Text style={st.brandDesc}>{b.description}</Text> : null}
            </View>
          ))}
        </View>
        {brands.length === 0 && (
          <View style={st.emptyBox}>
            <Ionicons name="star-outline" size={48} color={Colors.textMuted} />
            <Text style={st.emptyText}>{t.empty}</Text>
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
  subtitle: { fontSize: FontSize.md, color: Colors.textSecondary, textAlign: 'center', marginBottom: Spacing.xl, lineHeight: 20 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  brandCard: { width: '47%', backgroundColor: Colors.card, borderRadius: 14, padding: Spacing.md, alignItems: 'center', borderWidth: 1, borderColor: Colors.cardBorder },
  logo: { width: 80, height: 80, marginBottom: Spacing.sm },
  logoPlaceholder: { width: 80, height: 80, borderRadius: 40, backgroundColor: Colors.gold + '10', alignItems: 'center', justifyContent: 'center', marginBottom: Spacing.sm },
  brandName: { fontSize: FontSize.md, fontWeight: '700', color: Colors.text, textAlign: 'center' },
  brandDesc: { fontSize: FontSize.xs, color: Colors.textMuted, textAlign: 'center', marginTop: 4 },
  emptyBox: { alignItems: 'center', marginTop: 60, gap: 12 },
  emptyText: { fontSize: FontSize.md, color: Colors.textMuted, textAlign: 'center' },
});
