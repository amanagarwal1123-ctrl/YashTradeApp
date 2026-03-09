import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator, Image, Dimensions } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api } from '../src/api';
import { useLang } from '../src/context/LanguageContext';

const { width } = Dimensions.get('window');

export default function ShowroomScreen() {
  const router = useRouter();
  const { language } = useLang();
  const [floors, setFloors] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get('/showroom');
        setFloors(res.floors || []);
      } catch (e) { console.error(e); }
      finally { setLoading(false); }
    })();
  }, []);

  const T: Record<string, any> = {
    en: { title: 'Showroom Photos', subtitle: 'Explore our multi-floor showroom', products: 'Products Available', empty: 'Showroom photos coming soon! Admin can add floor-wise photos from the panel.' },
    hi: { title: '\u0936\u094b\u0930\u0942\u092e \u092b\u094b\u091f\u094b', subtitle: '\u0939\u092e\u093e\u0930\u0947 \u092c\u0939\u0941-\u092e\u0902\u091c\u093f\u0932\u0947 \u0936\u094b\u0930\u0942\u092e \u0915\u094b \u0926\u0947\u0916\u0947\u0902', products: '\u0909\u092a\u0932\u092c\u094d\u0927 \u0909\u0924\u094d\u092a\u093e\u0926', empty: '\u0936\u094b\u0930\u0942\u092e \u092b\u094b\u091f\u094b \u091c\u0932\u094d\u0926 \u0906 \u0930\u0939\u0947 \u0939\u0948\u0902!' },
    pa: { title: '\u0a36\u0a4b\u0a05\u0a30\u0a42\u0a2e \u0a2b\u0a4b\u0a1f\u0a4b', subtitle: '\u0a38\u0a3e\u0a21\u0a47 \u0a2c\u0a39\u0a41-\u0a2e\u0a70\u0a1c\u0a3c\u0a3f\u0a32\u0a47 \u0a36\u0a4b\u0a05\u0a30\u0a42\u0a2e \u0a26\u0a47\u0a16\u0a4b', products: '\u0a09\u0a2a\u0a32\u0a2c\u0a27 \u0a09\u0a24\u0a2a\u0a3e\u0a26', empty: '\u0a36\u0a4b\u0a05\u0a30\u0a42\u0a2e \u0a2b\u0a4b\u0a1f\u0a4b \u0a1c\u0a32\u0a26 \u0a06 \u0a30\u0a39\u0a47 \u0a39\u0a28!' },
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
        {floors.map((f, i) => {
          const name = f[`floor_name_${language}`] || f.floor_name;
          const desc = f[`description_${language}`] || f.description;
          const products = f[`products_available_${language}`] || f.products_available;
          return (
            <View key={f.id} style={st.floorCard} data-testid={`floor-${f.id}`}>
              {f.photos && f.photos.length > 0 ? (
                <ScrollView horizontal showsHorizontalScrollIndicator={false} style={st.photoScroll}>
                  {f.photos.map((p: string, pi: number) => <Image key={pi} source={{ uri: p }} style={st.floorPhoto} />)}
                </ScrollView>
              ) : (
                <View style={st.photoPlaceholder}><Ionicons name="images" size={40} color={Colors.gold} /></View>
              )}
              <View style={st.floorBody}>
                <View style={st.floorHeader}>
                  <View style={st.floorBadge}><Text style={st.floorBadgeText}>{i + 1}</Text></View>
                  <Text style={st.floorName}>{name}</Text>
                </View>
                {desc ? <Text style={st.floorDesc}>{desc}</Text> : null}
                {products ? (
                  <View style={st.productsBox}>
                    <Text style={st.productsLabel}>{t.products}:</Text>
                    <Text style={st.productsText}>{products}</Text>
                  </View>
                ) : null}
              </View>
            </View>
          );
        })}
        {floors.length === 0 && (
          <View style={st.emptyBox}>
            <Ionicons name="images-outline" size={48} color={Colors.textMuted} />
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
  subtitle: { fontSize: FontSize.md, color: Colors.textSecondary, textAlign: 'center', marginBottom: Spacing.xl },
  floorCard: { backgroundColor: Colors.card, borderRadius: 16, overflow: 'hidden', marginBottom: Spacing.lg, borderWidth: 1, borderColor: Colors.cardBorder },
  photoScroll: { height: 200 },
  floorPhoto: { width: width * 0.7, height: 200, marginRight: 2 },
  photoPlaceholder: { height: 140, backgroundColor: Colors.gold + '08', alignItems: 'center', justifyContent: 'center' },
  floorBody: { padding: Spacing.md },
  floorHeader: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: Spacing.sm },
  floorBadge: { width: 28, height: 28, borderRadius: 14, backgroundColor: Colors.gold, alignItems: 'center', justifyContent: 'center' },
  floorBadgeText: { fontSize: FontSize.sm, fontWeight: '700', color: '#000' },
  floorName: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text },
  floorDesc: { fontSize: FontSize.md, color: Colors.textSecondary, lineHeight: 20, marginBottom: Spacing.sm },
  productsBox: { backgroundColor: Colors.gold + '08', borderRadius: 10, padding: Spacing.sm },
  productsLabel: { fontSize: FontSize.xs, color: Colors.gold, fontWeight: '700', letterSpacing: 1, marginBottom: 4 },
  productsText: { fontSize: FontSize.sm, color: Colors.text, lineHeight: 18 },
  emptyBox: { alignItems: 'center', marginTop: 60, gap: 12 },
  emptyText: { fontSize: FontSize.md, color: Colors.textMuted, textAlign: 'center' },
});
