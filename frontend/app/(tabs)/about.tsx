import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator, Linking } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../../src/theme';
import { api } from '../../src/api';
import { useLang } from '../../src/context/LanguageContext';

const ICONS: Record<string, string> = {
  'One Stop Shop': 'storefront', 'Accuracy in Purity': 'checkmark-done-circle', 'Fast Billing': 'flash',
  'Online Live Video Calling': 'videocam', "India's Biggest Online Jewellery Catalogue": 'globe',
  'Cheapest Rate Guaranteed': 'pricetag', 'Compulsory Gift': 'gift', 'Original Brand Guaranteed': 'shield-checkmark',
  'Sunday Open': 'calendar', 'Full Range ki Guarantee': 'layers', 'Latest Running Range ki Guarantee': 'trending-up',
  '0% Dead Stock': 'close-circle', 'Market ki Knowledge': 'bar-chart',
};

export default function AboutScreen() {
  const router = useRouter();
  const { language } = useLang();
  const [sections, setSections] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get(`/about?lang=${language}`);
        setSections(res.raw || []);
      } catch (e) { console.error(e); }
      finally { setLoading(false); }
    })();
  }, [language]);

  const getContent = (section: string) => {
    const s = sections.find(x => x.section === section);
    if (!s) return '';
    return s[`content_${language}`] || s.content_en || '';
  };

  const renderBullets = (content: string, iconMap?: boolean) => {
    if (!content) return null;
    return content.split('|').map((item, i) => (
      <View key={i} style={st.bulletRow}>
        <Ionicons name={(iconMap && ICONS[item.trim()]) ? ICONS[item.trim()] as any : 'checkmark-circle'} size={18} color={Colors.gold} />
        <Text style={st.bulletText}>{item.trim()}</Text>
      </View>
    ));
  };

  const renderLocationCard = (section: string, icon: string) => {
    const content = getContent(section);
    if (!content) return null;
    const parts = content.split('|');
    const title = parts[0] || '';
    const details = parts.slice(1);
    return (
      <View style={st.locationCard}>
        <View style={st.locationHeader}>
          <Ionicons name={icon as any} size={22} color={Colors.gold} />
          <Text style={st.locationTitle}>{title}</Text>
        </View>
        {details.map((d, i) => (
          <Text key={i} style={st.locationDetail}>{d.trim()}</Text>
        ))}
      </View>
    );
  };

  if (loading) return <View style={st.loader}><ActivityIndicator size="large" color={Colors.gold} /></View>;

  const T = {
    en: { title: 'About Yash Ornaments', whyBuy: 'Why Buy From Us', newBenefits: 'New Shop Extra Benefits', b2b: 'B2B Wholesale Benefits', locations: 'Our Locations', quickLinks: 'Explore More', subtitle: 'Premium Silver \u2022 Gold \u2022 Diamond Wholesale', ratelist: 'Rate List', schemes: 'Schemes', brands: 'Our Brands', showroom: 'Showroom', exhibition: 'Exhibition' },
    hi: { title: '\u092f\u0936 \u0911\u0930\u094d\u0928\u093e\u092e\u0947\u0902\u091f\u094d\u0938 \u0915\u0947 \u092c\u093e\u0930\u0947 \u092e\u0947\u0902', whyBuy: '\u0939\u092e\u0938\u0947 \u0915\u094d\u092f\u094b\u0902 \u0916\u0930\u0940\u0926\u0947\u0902', newBenefits: '\u0928\u0908 \u0926\u0941\u0915\u093e\u0928 \u0915\u0947 \u0935\u093f\u0936\u0947\u0937 \u0932\u093e\u092d', b2b: 'B2B \u0925\u094b\u0915 \u0932\u093e\u092d', locations: '\u0939\u092e\u093e\u0930\u0947 \u0938\u094d\u0925\u093e\u0928', quickLinks: '\u0914\u0930 \u0926\u0947\u0916\u0947\u0902', subtitle: '\u092a\u094d\u0930\u0940\u092e\u093f\u092f\u092e \u091a\u093e\u0902\u0926\u0940 \u2022 \u0938\u094b\u0928\u093e \u2022 \u0939\u0940\u0930\u093e \u0925\u094b\u0915', ratelist: '\u0930\u0947\u091f \u0932\u093f\u0938\u094d\u091f', schemes: '\u0938\u094d\u0915\u0940\u092e\u094d\u0938', brands: '\u0939\u092e\u093e\u0930\u0947 \u092c\u094d\u0930\u093e\u0902\u0921', showroom: '\u0936\u094b\u0930\u0942\u092e', exhibition: '\u092a\u094d\u0930\u0926\u0930\u094d\u0936\u0928\u0940' },
    pa: { title: '\u0a2f\u0a36 \u0a14\u0a30\u0a28\u0a3e\u0a2e\u0a48\u0a02\u0a1f\u0a38 \u0a2c\u0a3e\u0a30\u0a47', whyBuy: '\u0a38\u0a3e\u0a21\u0a47 \u0a15\u0a4b\u0a32\u0a4b\u0a02 \u0a16\u0a30\u0a40\u0a26\u0a4b', newBenefits: '\u0a28\u0a35\u0a40\u0a02 \u0a26\u0a41\u0a15\u0a3e\u0a28 \u0a26\u0a47 \u0a32\u0a3e\u0a2d', b2b: 'B2B \u0a25\u0a4b\u0a15 \u0a32\u0a3e\u0a2d', locations: '\u0a38\u0a3e\u0a21\u0a47 \u0a1f\u0a3f\u0a15\u0a3e\u0a23\u0a47', quickLinks: '\u0a39\u0a4b\u0a30 \u0a35\u0a47\u0a16\u0a4b', subtitle: '\u0a2a\u0a4d\u0a30\u0a40\u0a2e\u0a40\u0a05\u0a2e \u0a1a\u0a3e\u0a02\u0a26\u0a40 \u2022 \u0a38\u0a4b\u0a28\u0a3e \u2022 \u0a39\u0a40\u0a30\u0a3e \u0a25\u0a4b\u0a15', ratelist: '\u0a30\u0a47\u0a1f \u0a32\u0a3f\u0a38\u0a1f', schemes: '\u0a38\u0a15\u0a40\u0a2e\u0a3e\u0a02', brands: '\u0a38\u0a3e\u0a21\u0a47 \u0a2c\u0a4d\u0a30\u0a3e\u0a02\u0a21', showroom: '\u0a36\u0a4b\u0a05\u0a30\u0a42\u0a2e', exhibition: '\u0a2a\u0a4d\u0a30\u0a26\u0a30\u0a36\u0a28\u0a40' },
  };
  const t = T[language as keyof typeof T] || T.en;

  return (
    <SafeAreaView style={st.container} edges={['top']}>
      <ScrollView showsVerticalScrollIndicator={false}>
        {/* Hero */}
        <View style={st.hero}>
          <Ionicons name="diamond" size={40} color={Colors.gold} />
          <Text style={st.heroTitle} data-testid="about-title">{t.title}</Text>
          <Text style={st.heroSub}>{t.subtitle}</Text>
        </View>

        {/* Brand Intro */}
        <View style={st.section}>
          <Text style={st.introText}>{getContent('brand_intro')}</Text>
        </View>

        {/* Why Buy */}
        <View style={st.section}>
          <Text style={st.sectionTitle}>{t.whyBuy}</Text>
          <View style={st.bulletList}>
            {renderBullets(getContent('why_buy'), true)}
          </View>
        </View>

        {/* New Shop Benefits */}
        <View style={st.section}>
          <Text style={st.sectionTitle}>{t.newBenefits}</Text>
          <View style={st.bulletList}>
            {renderBullets(getContent('new_shop_benefits'), true)}
          </View>
        </View>

        {/* B2B Benefits */}
        <View style={st.section}>
          <Text style={st.sectionTitle}>{t.b2b}</Text>
          <View style={st.bulletList}>
            {renderBullets(getContent('b2b_benefits'))}
          </View>
        </View>

        {/* Locations */}
        <View style={st.section}>
          <Text style={st.sectionTitle}>{t.locations}</Text>
          {renderLocationCard('location_chandni_chowk', 'location')}
          {renderLocationCard('location_karol_bagh', 'business')}
        </View>

        {/* Quick Links */}
        <View style={st.section}>
          <Text style={st.sectionTitle}>{t.quickLinks}</Text>
          <View style={st.linksGrid}>
            {[
              { icon: 'list', label: t.ratelist, route: '/rate-list' },
              { icon: 'ribbon', label: t.schemes, route: '/schemes' },
              { icon: 'star', label: t.brands, route: '/brands' },
              { icon: 'images', label: t.showroom, route: '/showroom' },
              { icon: 'calendar', label: t.exhibition, route: '/exhibition' },
            ].map((lnk, i) => (
              <TouchableOpacity key={i} style={st.linkCard} onPress={() => router.push(lnk.route as any)} data-testid={`about-link-${i}`}>
                <Ionicons name={lnk.icon as any} size={24} color={Colors.gold} />
                <Text style={st.linkLabel}>{lnk.label}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        <View style={{ height: 40 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  loader: { flex: 1, backgroundColor: Colors.background, justifyContent: 'center', alignItems: 'center' },
  hero: { alignItems: 'center', paddingVertical: Spacing.xl, paddingHorizontal: Spacing.lg, borderBottomWidth: 1, borderBottomColor: Colors.borderGold },
  heroTitle: { fontSize: FontSize.xl, fontWeight: '700', color: Colors.gold, marginTop: Spacing.sm, letterSpacing: 1 },
  heroSub: { fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: 4 },
  section: { paddingHorizontal: Spacing.lg, marginTop: Spacing.lg },
  sectionTitle: { fontSize: FontSize.sm, fontWeight: '700', color: Colors.gold, letterSpacing: 2, marginBottom: Spacing.md, textTransform: 'uppercase' },
  introText: { fontSize: FontSize.md, color: Colors.textSecondary, lineHeight: 22 },
  bulletList: { gap: 10 },
  bulletRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
  bulletText: { flex: 1, fontSize: FontSize.md, color: Colors.text, lineHeight: 20 },
  locationCard: { backgroundColor: Colors.card, borderRadius: 14, padding: Spacing.md, marginBottom: Spacing.md, borderWidth: 1, borderColor: Colors.cardBorder },
  locationHeader: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: Spacing.sm },
  locationTitle: { fontSize: FontSize.base, fontWeight: '700', color: Colors.text },
  locationDetail: { fontSize: FontSize.sm, color: Colors.textSecondary, lineHeight: 20, paddingLeft: 32 },
  linksGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  linkCard: { width: '30%', backgroundColor: Colors.card, borderRadius: 14, padding: Spacing.md, alignItems: 'center', gap: 8, borderWidth: 1, borderColor: Colors.cardBorder },
  linkLabel: { fontSize: FontSize.xs, color: Colors.textSecondary, textAlign: 'center', fontWeight: '500' },
});
