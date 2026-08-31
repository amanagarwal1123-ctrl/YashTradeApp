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
  const [loadError, setLoadError] = useState(false);
  const [activeMetal, setActiveMetal] = useState('silver');
  const [rates, setRates] = useState<any>(null);

  const loadData = async () => {
    try {
      setLoadError(false);
      const [slabRes, rateRes] = await Promise.all([
        api.get('/rate-list'),
        api.get('/rates/latest').catch(() => null),
      ]);
      setSlabs(slabRes.slabs || []);
      setRates(rateRes);
    } catch (e) { console.error(e); setLoadError(true); }
    finally { setLoading(false); }
  };

  useEffect(() => { loadData(); }, []);

  const T: Record<string, any> = {
    en: { title: 'Rate List', silver: 'Silver', gold: 'Gold', diamond: 'Diamond', item: 'Item', category: 'Category', purity: 'Purity', wastage: 'Wastage', labour: 'Labour/KG', todayRate: "Today's Rates", error: 'Could not load rate list. Please check your connection.', retry: 'Retry' },
    hi: { title: 'रेट लिस्ट', silver: 'चांदी', gold: 'सोना', diamond: 'हीरा', item: 'आइटम', category: 'कैटेगरी', purity: 'शुद्धता', wastage: 'वेस्टेज', labour: 'लेबर/KG', todayRate: 'आज के रेट', error: 'रेट लिस्ट लोड नहीं हो सकी। कृपया कनेक्शन जांचें।', retry: 'फिर से कोशिश करें' },
    pa: { title: 'ਰੇਟ ਲਿਸਟ', silver: 'ਚਾਂਦੀ', gold: 'ਸੋਨਾ', diamond: 'ਹੀਰਾ', item: 'ਆਈਟਮ', category: 'ਕੈਟੇਗਰੀ', purity: 'ਸ਼ੁੱਧਤਾ', wastage: 'ਵੇਸਟੇਜ', labour: 'ਲੇਬਰ/KG', todayRate: 'ਅੱਜ ਦੇ ਰੇਟ', error: 'ਰੇਟ ਲਿਸਟ ਲੋਡ ਨਹੀਂ ਹੋ ਸਕੀ। ਕਿਰਪਾ ਕਰਕੇ ਕਨੈਕਸ਼ਨ ਚੈੱਕ ਕਰੋ।', retry: 'ਮੁੜ ਕੋਸ਼ਿਸ਼ ਕਰੋ' },
  };
  const t = T[language] || T.en;
  const filteredSlabs = slabs.filter(s => s.metal_type === activeMetal);
  const hasRates = rates && ((rates.silver_physical_rate || 0) > 0 || (rates.gold_physical_rate || 0) > 0);

  if (loading) return <View style={st.loader}><ActivityIndicator size="large" color={Colors.gold} /></View>;

  return (
    <SafeAreaView style={st.container} edges={['top']}>
      <View style={st.header}>
        <TouchableOpacity onPress={() => router.back()}><Ionicons name="arrow-back" size={22} color={Colors.text} /></TouchableOpacity>
        <Text style={st.headerTitle}>{t.title}</Text>
        <View style={{ width: 22 }} />
      </View>

      {loadError && (
        <View style={st.errorBox} data-testid="ratelist-error">
          <Text style={st.errorText}>{t.error}</Text>
          <TouchableOpacity style={st.retryBtn} onPress={() => { setLoading(true); loadData(); }}>
            <Text style={st.retryBtnText}>{t.retry}</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Admin-set daily rates (manual, no live feed) */}
      {hasRates && (
        <View style={st.ratesBanner} data-testid="today-rates">
          <Text style={st.ratesLabel}>{t.todayRate}</Text>
          <View style={st.ratesRow}>
            {(rates.silver_physical_rate || 0) > 0 && <Text style={st.rateText}>{`${t.silver}: ₹${rates.silver_physical_rate?.toFixed(2)}/g`}</Text>}
            {(rates.gold_physical_rate || 0) > 0 && <Text style={st.rateText}>{`${t.gold}: ₹${rates.gold_physical_rate?.toFixed(0)}/g`}</Text>}
          </View>
          {rates.market_summary ? <Text style={st.ratesSummary}>{rates.market_summary}</Text> : null}
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
  ratesBanner: { margin: Spacing.lg, marginBottom: 0, backgroundColor: Colors.card, borderRadius: 14, padding: Spacing.md, borderWidth: 1, borderColor: Colors.borderGold },
  ratesLabel: { fontSize: FontSize.xs, color: Colors.textSecondary, fontWeight: '600', letterSpacing: 1, marginBottom: 8 },
  ratesRow: { gap: 4 },
  rateText: { fontSize: FontSize.sm, color: Colors.text, fontWeight: '500' },
  ratesSummary: { fontSize: FontSize.xs, color: Colors.textMuted, marginTop: 6, fontStyle: 'italic' },
  errorBox: { marginHorizontal: Spacing.lg, marginTop: Spacing.md, backgroundColor: Colors.error + '10', borderRadius: 12, padding: Spacing.md, borderWidth: 1, borderColor: Colors.error + '30', alignItems: 'center', gap: 8 },
  errorText: { fontSize: FontSize.sm, color: Colors.error, textAlign: 'center' },
  retryBtn: { backgroundColor: Colors.error + '20', paddingHorizontal: 20, paddingVertical: 8, borderRadius: 8 },
  retryBtnText: { fontSize: FontSize.xs, fontWeight: '700', color: Colors.error },
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
