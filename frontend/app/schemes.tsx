import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator, Image, Dimensions } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api } from '../src/api';
import { useLang } from '../src/context/LanguageContext';

const { width } = Dimensions.get('window');

export default function SchemesScreen() {
  const router = useRouter();
  const { language } = useLang();
  const [schemes, setSchemes] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get('/schemes');
        setSchemes(res.schemes || []);
      } catch (e) { console.error(e); }
      finally { setLoading(false); }
    })();
  }, []);

  const T: Record<string, any> = {
    en: { title: 'Schemes & Offers', empty: 'No schemes available right now. Check back soon!' },
    hi: { title: '\u0938\u094d\u0915\u0940\u092e \u0914\u0930 \u0911\u092b\u0930', empty: '\u0905\u092d\u0940 \u0915\u094b\u0908 \u0938\u094d\u0915\u0940\u092e \u0909\u092a\u0932\u092c\u094d\u0927 \u0928\u0939\u0940\u0902 \u0939\u0948\u0964 \u091c\u0932\u094d\u0926 \u0939\u0940 \u0926\u094b\u092c\u093e\u0930\u093e \u0926\u0947\u0916\u0947\u0902!' },
    pa: { title: '\u0a38\u0a15\u0a40\u0a2e\u0a3e\u0a02 \u0a05\u0a24\u0a47 \u0a11\u0a2b\u0a30', empty: '\u0a39\u0a41\u0a23 \u0a15\u0a4b\u0a08 \u0a38\u0a15\u0a40\u0a2e \u0a09\u0a2a\u0a32\u0a2c\u0a27 \u0a28\u0a39\u0a40\u0a02\u0964' },
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
        {schemes.map(s => {
          const title = s[`title_${language}`] || s.title;
          const desc = s[`description_${language}`] || s.description;
          return (
            <View key={s.id} style={st.card} data-testid={`scheme-${s.id}`}>
              {s.poster_url ? <Image source={{ uri: s.poster_url }} style={st.poster} resizeMode="cover" /> : (
                <View style={st.posterPlaceholder}><Ionicons name="ribbon" size={48} color={Colors.gold} /></View>
              )}
              <View style={st.cardBody}>
                <Text style={st.cardTitle}>{title}</Text>
                {desc ? <Text style={st.cardDesc}>{desc}</Text> : null}
              </View>
            </View>
          );
        })}
        {schemes.length === 0 && (
          <View style={st.emptyBox}>
            <Ionicons name="ribbon-outline" size={48} color={Colors.textMuted} />
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
  card: { backgroundColor: Colors.card, borderRadius: 16, overflow: 'hidden', marginBottom: Spacing.lg, borderWidth: 1, borderColor: Colors.cardBorder },
  poster: { width: '100%', height: width * 0.55, backgroundColor: Colors.surface },
  posterPlaceholder: { width: '100%', height: 160, backgroundColor: Colors.gold + '08', alignItems: 'center', justifyContent: 'center' },
  cardBody: { padding: Spacing.md },
  cardTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text, marginBottom: 4 },
  cardDesc: { fontSize: FontSize.md, color: Colors.textSecondary, lineHeight: 20 },
  emptyBox: { alignItems: 'center', marginTop: 60, gap: 12 },
  emptyText: { fontSize: FontSize.md, color: Colors.textMuted, textAlign: 'center' },
});
