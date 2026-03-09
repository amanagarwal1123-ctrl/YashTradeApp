import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api } from '../src/api';
import { useLang } from '../src/context/LanguageContext';

const METAL_COLORS: Record<string, string> = { silver: Colors.silver, gold: Colors.gold, diamond: Colors.info };
const METAL_ICONS: Record<string, string> = { silver: 'ellipse', gold: 'sunny', diamond: 'diamond' };

export default function RateListScreen() {
  const router = useRouter();
  const { language } = useLang();
  const [slabs, setSlabs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeMetal, setActiveMetal] = useState('silver');
  const [liveRates, setLiveRates] = useState<any>(null);

  useEffect(() => {
    (async () => {
      try {
        const [slabRes, liveRes] = await Promise.all([api.get('/rate-list'), api.get('/live-rates')]);
        setSlabs(slabRes.slabs || []);
        setLiveRates(liveRes);
      } catch (e) { console.error(e); }
      finally { setLoading(false); }
    })();
  }, []);

  const T: Record<string, any> = {
    en: { title: 'Rate List', silver: 'Silver', gold: 'Gold', diamond: 'Diamond', item: 'Item', category: 'Category', purity: 'Purity', wastage: 'Wastage', labour: 'Labour/KG', liveRate: 'Live Market Rate' },
    hi: { title: '\u0930\u0947\u091f \u0932\u093f\u0938\u094d\u091f', silver: '\u091a\u093e\u0902\u0926\u0940', gold: '\u0938\u094b\u0928\u093e', diamond: '\u0939\u0940\u0930\u093e', item: '\u0906\u0907\u091f\u092e', category: '\u0915\u0948\u091f\u0947\u0917\u0930\u0940', purity: '\u0936\u0941\u0926\u094d\u0927\u0924\u093e', wastage: '\u0935\u0947\u0938\u094d\u091f\u0947\u091c', labour: '\u0932\u0947\u092c\u0930/KG', liveRate: '\u0932\u093e\u0907\u0935 \u092e\u093e\u0930\u094d\u0915\u0947\u091f \u0930\u0947\u091f' },
    pa: { title: '\u0a30\u0a47\u0a1f \u0a32\u0a3f\u0a38\u0a1f', silver: '\u0a1a\u0a3e\u0a02\u0a26\u0a40', gold: '\u0a38\u0a4b\u0a28\u0a3e', diamond: '\u0a39\u0a40\u0a30\u0a3e', item: '\u0a06\u0a08\u0a1f\u0a2e', category: '\u0a15\u0a48\u0a1f\u0a47\u0a17\u0a30\u0a40', purity: '\u0a36\u0a41\u0a71\u0a27\u0a24\u0a3e', wastage: '\u0a35\u0a47\u0a38\u0a1f\u0a47\u0a1c', labour: '\u0a32\u0a47\u0a2c\u0a30/KG', liveRate: '\u0a32\u0a3e\u0a08\u0a35 \u0a2e\u0a3e\u0a30\u0a15\u0a3f\u0a1f \u0a30\u0a47\u0a1f' },
  };
  const t = T[language] || T.en;
  const filteredSlabs = slabs.filter(s => s.metal_type === activeMetal);

  if (loading) return <View style={st.loader}><ActivityIndicator size="large" color={Colors.gold} /></View>;

  return (
    <SafeAreaView style={st.container} edges={['top']}>
      <View style={st.header}>
        <TouchableOpacity onPress={() => router.back()}><Ionicons name="arrow-back" size={22} color={Colors.text} /></TouchableOpacity>
        <Text style={st.headerTitle}>{t.title}</Text>
        <View style={{ width: 22 }} />
      </View>

      {/* Live Rates Banner */}
      {liveRates && (liveRates.silver_mcx > 0 || liveRates.gold_mcx > 0) && (
        <View style={st.liveBanner}>
          <View style={st.liveRow}>
            <Text style={st.liveLabel}>{t.liveRate}</Text>
            <View style={st.liveDot} />
            <Text style={st.liveText}>LIVE</Text>
          </View>
          <View style={st.liveRatesRow}>
            {liveRates.silver_mcx > 0 && <Text style={st.liveRate}>Silver: \u20b9{liveRates.silver_physical?.toFixed(2)}/g (MCX \u20b9{liveRates.silver_mcx?.toFixed(2)} + Premium \u20b9{liveRates.silver_premium?.toFixed(2)})</Text>}
            {liveRates.gold_mcx > 0 && <Text style={st.liveRate}>Gold: \u20b9{liveRates.gold_physical?.toFixed(0)}/g (MCX \u20b9{liveRates.gold_mcx?.toFixed(0)} + Premium \u20b9{liveRates.gold_premium?.toFixed(0)})</Text>}
          </View>
          {liveRates.fetched_at && <Text style={st.liveTime}>Updated: {new Date(liveRates.fetched_at).toLocaleTimeString()}</Text>}
        </View>
      )}

      {/* Metal Tabs */}
      <View style={st.metalTabs}>
        {['silver', 'gold', 'diamond'].map(m => (
          <TouchableOpacity key={m} style={[st.metalTab, activeMetal === m && { backgroundColor: METAL_COLORS[m] + '20', borderColor: METAL_COLORS[m] }]} onPress={() => setActiveMetal(m)} data-testid={`rate-tab-${m}`}>
            <Ionicons name={METAL_ICONS[m] as any} size={16} color={activeMetal === m ? METAL_COLORS[m] : Colors.textMuted} />
            <Text style={[st.metalTabText, activeMetal === m && { color: METAL_COLORS[m] }]}>{t[m]}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <ScrollView contentContainerStyle={st.content}>
        {filteredSlabs.map((slab) => (
          <View key={slab.id} style={st.itemCard} data-testid={`rate-item-${slab.id}`}>
            <Text style={st.itemName}>{slab.item_name}</Text>
            <Text style={st.itemCategory}>{slab.category}{slab.subcategory ? ` / ${slab.subcategory}` : ''}</Text>
            <View style={st.detailGrid}>
              <View style={st.detailCell}>
                <Text style={st.detailLabel}>{t.purity}</Text>
                <Text style={st.detailValue}>{slab.purity || '-'}</Text>
              </View>
              <View style={st.detailCell}>
                <Text style={st.detailLabel}>{t.wastage}</Text>
                <Text style={st.detailValue}>{slab.wastage || '-'}</Text>
              </View>
              <View style={st.detailCell}>
                <Text style={st.detailLabel}>{t.labour}</Text>
                <Text style={[st.detailValue, { color: Colors.gold }]}>{slab.labour_kg || '-'}</Text>
              </View>
            </View>
          </View>
        ))}
        {filteredSlabs.length === 0 && <Text style={st.emptyText}>No items listed for {t[activeMetal]}</Text>}
      </ScrollView>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  loader: { flex: 1, backgroundColor: Colors.background, justifyContent: 'center', alignItems: 'center' },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md, borderBottomWidth: 1, borderBottomColor: Colors.border },
  headerTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text },
  liveBanner: { margin: Spacing.lg, backgroundColor: Colors.card, borderRadius: 14, padding: Spacing.md, borderWidth: 1, borderColor: Colors.borderGold },
  liveRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 },
  liveLabel: { fontSize: FontSize.xs, color: Colors.textSecondary, fontWeight: '600', letterSpacing: 1 },
  liveDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: Colors.success },
  liveText: { fontSize: 9, color: Colors.success, fontWeight: '700', letterSpacing: 1 },
  liveRatesRow: { gap: 4 },
  liveRate: { fontSize: FontSize.sm, color: Colors.text, fontWeight: '500' },
  liveTime: { fontSize: 9, color: Colors.textMuted, marginTop: 6 },
  metalTabs: { flexDirection: 'row', paddingHorizontal: Spacing.lg, gap: 8, marginTop: Spacing.md },
  metalTab: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 10, borderRadius: 10, backgroundColor: Colors.surface, borderWidth: 1, borderColor: Colors.border },
  metalTabText: { fontSize: FontSize.sm, fontWeight: '600', color: Colors.textMuted },
  content: { padding: Spacing.lg },
  itemCard: { backgroundColor: Colors.card, borderRadius: 14, padding: Spacing.md, marginBottom: Spacing.sm, borderWidth: 1, borderColor: Colors.cardBorder },
  itemName: { fontSize: FontSize.base, fontWeight: '700', color: Colors.text, marginBottom: 2 },
  itemCategory: { fontSize: FontSize.xs, color: Colors.textSecondary, textTransform: 'capitalize', marginBottom: Spacing.sm },
  detailGrid: { flexDirection: 'row', gap: 8 },
  detailCell: { flex: 1, backgroundColor: Colors.surface, borderRadius: 8, padding: 8, alignItems: 'center' },
  detailLabel: { fontSize: 9, color: Colors.textMuted, fontWeight: '600', letterSpacing: 0.5, marginBottom: 2 },
  detailValue: { fontSize: FontSize.sm, color: Colors.text, fontWeight: '600' },
  emptyText: { padding: Spacing.lg, fontSize: FontSize.md, color: Colors.textMuted, textAlign: 'center' },
});
