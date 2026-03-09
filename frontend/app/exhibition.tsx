import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator, Image, Dimensions } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api } from '../src/api';
import { useLang } from '../src/context/LanguageContext';

const { width } = Dimensions.get('window');

export default function ExhibitionScreen() {
  const router = useRouter();
  const { language } = useLang();
  const [upcoming, setUpcoming] = useState<any[]>([]);
  const [past, setPast] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get('/exhibitions');
        setUpcoming(res.upcoming || []);
        setPast(res.past || []);
      } catch (e) { console.error(e); }
      finally { setLoading(false); }
    })();
  }, []);

  const T: Record<string, any> = {
    en: { title: 'Exhibitions', upcoming: 'Upcoming Exhibition', past: 'Previous Exhibitions', noUpcoming: 'No Upcoming Exhibition', noUpcomingDesc: 'Stay tuned! We will announce our next exhibition soon.', noPast: 'No previous exhibitions yet' },
    hi: { title: '\u092a\u094d\u0930\u0926\u0930\u094d\u0936\u0928\u0940', upcoming: '\u0906\u0917\u093e\u092e\u0940 \u092a\u094d\u0930\u0926\u0930\u094d\u0936\u0928\u0940', past: '\u092a\u093f\u091b\u0932\u0940 \u092a\u094d\u0930\u0926\u0930\u094d\u0936\u0928\u093f\u092f\u093e\u0901', noUpcoming: '\u0915\u094b\u0908 \u0906\u0917\u093e\u092e\u0940 \u092a\u094d\u0930\u0926\u0930\u094d\u0936\u0928\u0940 \u0928\u0939\u0940\u0902', noUpcomingDesc: '\u091c\u0941\u0921\u093c\u0947 \u0930\u0939\u0947\u0902! \u0939\u092e \u091c\u0932\u094d\u0926 \u0939\u0940 \u0905\u0917\u0932\u0940 \u092a\u094d\u0930\u0926\u0930\u094d\u0936\u0928\u0940 \u0915\u0940 \u0918\u094b\u0937\u0923\u093e \u0915\u0930\u0947\u0902\u0917\u0947\u0964', noPast: '\u0905\u092d\u0940 \u0924\u0915 \u0915\u094b\u0908 \u092a\u093f\u091b\u0932\u0940 \u092a\u094d\u0930\u0926\u0930\u094d\u0936\u0928\u0940 \u0928\u0939\u0940\u0902' },
    pa: { title: '\u0a2a\u0a4d\u0a30\u0a26\u0a30\u0a36\u0a28\u0a40\u0a06\u0a02', upcoming: '\u0a06\u0a17\u0a3e\u0a2e\u0a40 \u0a2a\u0a4d\u0a30\u0a26\u0a30\u0a36\u0a28\u0a40', past: '\u0a2a\u0a3f\u0a1b\u0a32\u0a40\u0a06\u0a02 \u0a2a\u0a4d\u0a30\u0a26\u0a30\u0a36\u0a28\u0a40\u0a06\u0a02', noUpcoming: '\u0a15\u0a4b\u0a08 \u0a06\u0a17\u0a3e\u0a2e\u0a40 \u0a2a\u0a4d\u0a30\u0a26\u0a30\u0a36\u0a28\u0a40 \u0a28\u0a39\u0a40\u0a02', noUpcomingDesc: '\u0a1c\u0a41\u0a5c\u0a47 \u0a30\u0a39\u0a4b!', noPast: '\u0a05\u0a1c\u0a47 \u0a15\u0a4b\u0a08 \u0a2a\u0a3f\u0a1b\u0a32\u0a40 \u0a2a\u0a4d\u0a30\u0a26\u0a30\u0a36\u0a28\u0a40 \u0a28\u0a39\u0a40\u0a02' },
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
        {/* Upcoming */}
        <Text style={st.sectionTitle}>{t.upcoming}</Text>
        {upcoming.length > 0 ? upcoming.map(e => {
          const title = e[`title_${language}`] || e.title;
          const desc = e[`description_${language}`] || e.description;
          return (
            <View key={e.id} style={st.upcomingCard} data-testid={`exhibition-${e.id}`}>
              {e.poster_url ? <Image source={{ uri: e.poster_url }} style={st.poster} resizeMode="cover" /> : (
                <View style={st.posterPlaceholder}><Ionicons name="calendar" size={48} color={Colors.gold} /></View>
              )}
              <View style={st.cardBody}>
                <Text style={st.cardTitle}>{title}</Text>
                {e.date ? <View style={st.infoRow}><Ionicons name="calendar-outline" size={14} color={Colors.gold} /><Text style={st.infoText}>{e.date}</Text></View> : null}
                {e.location ? <View style={st.infoRow}><Ionicons name="location-outline" size={14} color={Colors.gold} /><Text style={st.infoText}>{e.location}</Text></View> : null}
                {desc ? <Text style={st.cardDesc}>{desc}</Text> : null}
              </View>
            </View>
          );
        }) : (
          <View style={st.noUpcoming}>
            <Ionicons name="calendar-outline" size={48} color={Colors.textMuted} />
            <Text style={st.noUpcomingTitle}>{t.noUpcoming}</Text>
            <Text style={st.noUpcomingDesc}>{t.noUpcomingDesc}</Text>
          </View>
        )}

        {/* Past */}
        {past.length > 0 && (
          <>
            <Text style={[st.sectionTitle, { marginTop: Spacing.xl }]}>{t.past}</Text>
            {past.map(e => {
              const title = e[`title_${language}`] || e.title;
              return (
                <View key={e.id} style={st.pastCard}>
                  {e.poster_url ? <Image source={{ uri: e.poster_url }} style={st.pastPoster} resizeMode="cover" /> : null}
                  <View style={st.pastBody}>
                    <Text style={st.pastTitle}>{title}</Text>
                    {e.date ? <Text style={st.pastDate}>{e.date}</Text> : null}
                  </View>
                  {e.photos && e.photos.length > 0 && (
                    <ScrollView horizontal showsHorizontalScrollIndicator={false} style={st.pastPhotos}>
                      {e.photos.map((p: string, pi: number) => <Image key={pi} source={{ uri: p }} style={st.pastPhoto} />)}
                    </ScrollView>
                  )}
                </View>
              );
            })}
          </>
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
  sectionTitle: { fontSize: FontSize.sm, fontWeight: '700', color: Colors.gold, letterSpacing: 2, marginBottom: Spacing.md },
  upcomingCard: { backgroundColor: Colors.card, borderRadius: 16, overflow: 'hidden', borderWidth: 1, borderColor: Colors.borderGold },
  poster: { width: '100%', height: width * 0.5, backgroundColor: Colors.surface },
  posterPlaceholder: { height: 160, backgroundColor: Colors.gold + '08', alignItems: 'center', justifyContent: 'center' },
  cardBody: { padding: Spacing.md },
  cardTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text, marginBottom: Spacing.sm },
  infoRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 },
  infoText: { fontSize: FontSize.sm, color: Colors.textSecondary },
  cardDesc: { fontSize: FontSize.md, color: Colors.textSecondary, lineHeight: 20, marginTop: Spacing.sm },
  noUpcoming: { alignItems: 'center', paddingVertical: Spacing.xxl, backgroundColor: Colors.card, borderRadius: 16, borderWidth: 1, borderColor: Colors.cardBorder },
  noUpcomingTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text, marginTop: Spacing.md },
  noUpcomingDesc: { fontSize: FontSize.md, color: Colors.textMuted, marginTop: 4, textAlign: 'center', paddingHorizontal: Spacing.lg },
  pastCard: { backgroundColor: Colors.card, borderRadius: 14, overflow: 'hidden', marginBottom: Spacing.md, borderWidth: 1, borderColor: Colors.cardBorder },
  pastPoster: { width: '100%', height: 120 },
  pastBody: { padding: Spacing.md },
  pastTitle: { fontSize: FontSize.md, fontWeight: '600', color: Colors.text },
  pastDate: { fontSize: FontSize.xs, color: Colors.textMuted, marginTop: 2 },
  pastPhotos: { paddingHorizontal: Spacing.sm, paddingBottom: Spacing.sm },
  pastPhoto: { width: 100, height: 80, borderRadius: 8, marginRight: 6 },
});
