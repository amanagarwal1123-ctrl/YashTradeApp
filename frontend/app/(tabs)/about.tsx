import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator } from 'react-native';
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

// Detailed descriptions for each "Why Buy" point
const WHY_BUY_DETAILS: Record<string, Record<string, string>> = {
  'One Stop Shop': {
    en: 'Everything under one roof \u2014 Silver, Gold, Diamond, Articles, Gifting items, Coins, Chains, Payals, Bangles, and more. No need to visit multiple shops. Complete your entire purchase requirement at Yash Ornaments.',
    hi: '\u090f\u0915 \u0939\u0940 \u091b\u0924 \u0915\u0947 \u0928\u0940\u091a\u0947 \u0938\u092c \u0915\u0941\u091b \u2014 \u091a\u093e\u0902\u0926\u0940, \u0938\u094b\u0928\u093e, \u0939\u0940\u0930\u093e, \u0906\u0930\u094d\u091f\u093f\u0915\u0932\u094d\u0938, \u0917\u093f\u092b\u094d\u091f\u093f\u0902\u0917, \u0938\u093f\u0915\u094d\u0915\u0947, \u091a\u0947\u0928, \u092a\u093e\u092f\u0932, \u091a\u0942\u0921\u093c\u093f\u092f\u093e\u0902 \u0914\u0930 \u092c\u0939\u0941\u0924 \u0915\u0941\u091b\u0964',
    pa: '\u0a07\u0a71\u0a15 \u0a39\u0a40 \u0a1b\u0a71\u0a24 \u0a39\u0a47\u0a20 \u0a38\u0a2d \u0a15\u0a41\u0a1d \u2014 \u0a1a\u0a3e\u0a02\u0a26\u0a40, \u0a38\u0a4b\u0a28\u0a3e, \u0a39\u0a40\u0a30\u0a3e\u0964',
  },
  'Accuracy in Purity': {
    en: 'We guarantee hallmarked purity in every product. 92.5% silver, 22K/18K gold \u2014 verified and certified. You can trust every gram you buy from us.',
    hi: '\u0939\u092e \u0939\u0930 \u0909\u0924\u094d\u092a\u093e\u0926 \u092e\u0947\u0902 \u0939\u0949\u0932\u092e\u093e\u0930\u094d\u0915\u0921 \u0936\u0941\u0926\u094d\u0927\u0924\u093e \u0915\u0940 \u0917\u093e\u0930\u0902\u091f\u0940 \u0926\u0947\u0924\u0947 \u0939\u0948\u0902\u0964',
    pa: '\u0a05\u0a38\u0a40\u0a02 \u0a39\u0a30 \u0a09\u0a24\u0a2a\u0a3e\u0a26 \u0a35\u0a3f\u0a71\u0a1a \u0a39\u0a3e\u0a32\u0a2e\u0a3e\u0a30\u0a15\u0a21 \u0a36\u0a41\u0a71\u0a27\u0a24\u0a3e \u0a26\u0a40 \u0a17\u0a3e\u0a30\u0a70\u0a1f\u0a40 \u0a26\u0a3f\u0a70\u0a26\u0a47 \u0a39\u0a3e\u0a02\u0964',
  },
  'Fast Billing': {
    en: 'Quick and efficient billing process. We value your time \u2014 get your invoice ready in minutes, not hours. Professional computerized billing system.',
    hi: '\u0924\u0947\u091c \u0914\u0930 \u0915\u0941\u0936\u0932 \u092c\u093f\u0932\u093f\u0902\u0917\u0964 \u092e\u093f\u0928\u091f\u094b\u0902 \u092e\u0947\u0902 \u0907\u0928\u094d\u0935\u0949\u0907\u0938 \u0924\u0948\u092f\u093e\u0930\u0964',
    pa: '\u0a24\u0a47\u0a1c\u0a3c \u0a05\u0a24\u0a47 \u0a15\u0a41\u0a36\u0a32 \u0a2c\u0a3f\u0a32\u0a3f\u0a70\u0a17\u0964',
  },
  'Online Live Video Calling': {
    en: 'Cannot visit our showroom? No problem! Use our Live Video Calling facility to see products in real-time. Our executive will show you items live on video call.',
    hi: '\u0936\u094b\u0930\u0942\u092e \u0928\u0939\u0940\u0902 \u0906 \u0938\u0915\u0924\u0947? \u0932\u093e\u0907\u0935 \u0935\u0940\u0921\u093f\u092f\u094b \u0915\u0949\u0932 \u092a\u0930 \u0909\u0924\u094d\u092a\u093e\u0926 \u0926\u0947\u0916\u0947\u0902\u0964',
    pa: '\u0a36\u0a4b\u0a05\u0a30\u0a42\u0a2e \u0a28\u0a39\u0a40\u0a02 \u0a06 \u0a38\u0a15\u0a26\u0a47? \u0a32\u0a3e\u0a08\u0a35 \u0a35\u0a40\u0a21\u0a40\u0a13 \u0a15\u0a3e\u0a32 \u0a24\u0a47 \u0a09\u0a24\u0a2a\u0a3e\u0a26 \u0a26\u0a47\u0a16\u0a4b\u0964',
  },
  "India's Biggest Online Jewellery Catalogue": {
    en: 'Browse through thousands of jewellery designs online. Our digital catalogue is one of the largest in India with 10,000+ product images updated regularly.',
    hi: '\u0939\u091c\u093c\u093e\u0930\u094b\u0902 \u091c\u094d\u0935\u0947\u0932\u0930\u0940 \u0921\u093f\u091c\u093c\u093e\u0907\u0928 \u0911\u0928\u0932\u093e\u0907\u0928 \u0926\u0947\u0916\u0947\u0902\u0964 10,000+ \u092a\u094d\u0930\u094b\u0921\u0915\u094d\u091f \u0907\u092e\u0947\u091c \u0928\u093f\u092f\u092e\u093f\u0924 \u0905\u092a\u0921\u0947\u091f\u0964',
    pa: '\u0a39\u0a1c\u0a3c\u0a3e\u0a30\u0a3e\u0a02 \u0a17\u0a39\u0a3f\u0a23\u0a3f\u0a06\u0a02 \u0a26\u0a47 \u0a21\u0a3f\u0a1c\u0a3c\u0a3e\u0a07\u0a28 \u0a14\u0a28\u0a32\u0a3e\u0a07\u0a28 \u0a26\u0a47\u0a16\u0a4b\u0964',
  },
  'Cheapest Rate Guaranteed': {
    en: 'We offer the most competitive wholesale rates in the market. Our direct sourcing and high volume ensures you get the best deal every time.',
    hi: '\u092c\u093e\u091c\u093e\u0930 \u092e\u0947\u0902 \u0938\u092c\u0938\u0947 \u0938\u0938\u094d\u0924\u0940 \u0926\u0930\u0964 \u0938\u0940\u0927\u0947 \u0938\u094b\u0930\u094d\u0938\u093f\u0902\u0917 \u0914\u0930 \u092c\u0921\u093c\u0947 \u0935\u0949\u0932\u094d\u092f\u0942\u092e \u0938\u0947 \u0938\u092c\u0938\u0947 \u0905\u091a\u094d\u091b\u0940 \u0921\u0940\u0932\u0964',
    pa: '\u0a2e\u0a3e\u0a30\u0a15\u0a3f\u0a1f \u0a35\u0a3f\u0a71\u0a1a \u0a38\u0a2d \u0a24\u0a4b\u0a02 \u0a38\u0a38\u0a24\u0a40 \u0a26\u0a30\u0964',
  },
  'Compulsory Gift': {
    en: 'Every customer who visits our showroom or makes a purchase receives a complimentary gift. It\u2019s our way of saying thank you for your trust and business.',
    hi: '\u0939\u0930 \u0917\u094d\u0930\u093e\u0939\u0915 \u0915\u094b \u0909\u092a\u0939\u093e\u0930 \u092e\u093f\u0932\u0924\u093e \u0939\u0948\u0964 \u092f\u0939 \u0906\u092a\u0915\u0947 \u092d\u0930\u094b\u0938\u0947 \u0915\u0947 \u0932\u093f\u090f \u0939\u092e\u093e\u0930\u093e \u0927\u0928\u094d\u092f\u0935\u093e\u0926 \u0939\u0948\u0964',
    pa: '\u0a39\u0a30 \u0a17\u0a3e\u0a39\u0a15 \u0a28\u0a42\u0a70 \u0a24\u0a4b\u0a39\u0a2b\u0a3c\u0a3e \u0a2e\u0a3f\u0a32\u0a26\u0a3e \u0a39\u0a48\u0964',
  },
  'Original Brand Guaranteed': {
    en: 'We deal only in genuine, original branded jewellery. No duplicates, no compromises. Every piece comes with brand authentication and warranty.',
    hi: '\u0915\u0947\u0935\u0932 \u0905\u0938\u0932\u0940, \u0913\u0930\u093f\u091c\u0928\u0932 \u092c\u094d\u0930\u093e\u0902\u0921\u0947\u0921 \u091c\u094d\u0935\u0947\u0932\u0930\u0940\u0964 \u0915\u094b\u0908 \u0921\u0941\u092a\u094d\u0932\u0940\u0915\u0947\u091f \u0928\u0939\u0940\u0902\u0964',
    pa: '\u0a15\u0a47\u0a35\u0a32 \u0a05\u0a38\u0a32\u0a40, \u0a13\u0a30\u0a3f\u0a1c\u0a28\u0a32 \u0a2c\u0a4d\u0a30\u0a3e\u0a02\u0a21\u0a47\u0a21 \u0a17\u0a39\u0a3f\u0a23\u0a47\u0964',
  },
  'Sunday Open': {
    en: 'Unlike most wholesale markets, we are OPEN on Sundays! Visit us any day of the week. Sunday hours: 11:00 AM to 6:00 PM.',
    hi: '\u0930\u0935\u093f\u0935\u093e\u0930 \u0915\u094b \u092d\u0940 \u0916\u0941\u0932\u0947 \u0939\u0948\u0902! \u0938\u092e\u092f: \u0938\u0941\u092c\u0939 11:00 \u0938\u0947 \u0936\u093e\u092e 6:00 \u092c\u091c\u0947\u0964',
    pa: '\u0a10\u0a24\u0a35\u0a3e\u0a30 \u0a28\u0a42\u0a70 \u0a35\u0a40 \u0a16\u0a41\u0a71\u0a32\u0a4d\u0a39\u0a47 \u0a39\u0a3e\u0a02! \u0a38\u0a2e\u0a3e\u0a02: \u0a38\u0a35\u0a47\u0a30\u0a47 11:00 \u0a24\u0a4b\u0a02 \u0a36\u0a3e\u0a2e 6:00\u0964',
  },
};

export default function AboutScreen() {
  const router = useRouter();
  const { language } = useLang();
  const [sections, setSections] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedPoints, setExpandedPoints] = useState<Record<string, boolean>>({});

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

  const togglePoint = (key: string) => {
    setExpandedPoints(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const renderClickableBullets = (content: string, sectionKey: string) => {
    if (!content) return null;
    return content.split('|').map((item, i) => {
      const trimmed = item.trim();
      const icon = ICONS[trimmed] || 'checkmark-circle';
      const detail = WHY_BUY_DETAILS[trimmed];
      const detailText = detail ? (detail[language] || detail.en) : '';
      const isExpanded = expandedPoints[`${sectionKey}-${i}`];
      return (
        <TouchableOpacity key={i} style={st.pointCard} onPress={() => togglePoint(`${sectionKey}-${i}`)} activeOpacity={0.7} data-testid={`about-point-${sectionKey}-${i}`}>
          <View style={st.pointHeader}>
            <Ionicons name={icon as any} size={20} color={Colors.gold} />
            <Text style={st.pointTitle}>{trimmed}</Text>
            {detailText ? <Ionicons name={isExpanded ? 'chevron-up' : 'chevron-down'} size={16} color={Colors.textMuted} /> : null}
          </View>
          {isExpanded && detailText ? (
            <Text style={st.pointDetail}>{detailText}</Text>
          ) : null}
        </TouchableOpacity>
      );
    });
  };

  const renderBullets = (content: string) => {
    if (!content) return null;
    return content.split('|').map((item, i) => (
      <View key={i} style={st.bulletRow}>
        <Ionicons name="checkmark-circle" size={18} color={Colors.gold} />
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
        {details.map((d: string, i: number) => (
          <Text key={i} style={st.locationDetail}>{d.trim()}</Text>
        ))}
      </View>
    );
  };

  if (loading) return <View style={st.loader}><ActivityIndicator size="large" color={Colors.gold} /></View>;

  const T = {
    en: { title: 'About Yash Ornaments', whyBuy: 'Why Buy From Us', newBenefits: 'New Shop Extra Benefits', b2b: 'B2B Wholesale Benefits', locations: 'Our Locations', quickLinks: 'Explore More', subtitle: 'Premium Silver \u2022 Gold \u2022 Diamond Wholesale', ratelist: 'Rate List', schemes: 'Schemes', brands: 'Our Brands', showroom: 'Showroom Photos', exhibition: 'Exhibition', tapToExpand: 'Tap any point to see details' },
    hi: { title: '\u092f\u0936 \u0911\u0930\u094d\u0928\u093e\u092e\u0947\u0902\u091f\u094d\u0938 \u0915\u0947 \u092c\u093e\u0930\u0947 \u092e\u0947\u0902', whyBuy: '\u0939\u092e\u0938\u0947 \u0915\u094d\u092f\u094b\u0902 \u0916\u0930\u0940\u0926\u0947\u0902', newBenefits: '\u0928\u0908 \u0926\u0941\u0915\u093e\u0928 \u0915\u0947 \u0935\u093f\u0936\u0947\u0937 \u0932\u093e\u092d', b2b: 'B2B \u0925\u094b\u0915 \u0932\u093e\u092d', locations: '\u0939\u092e\u093e\u0930\u0947 \u0938\u094d\u0925\u093e\u0928', quickLinks: '\u0914\u0930 \u0926\u0947\u0916\u0947\u0902', subtitle: '\u092a\u094d\u0930\u0940\u092e\u093f\u092f\u092e \u091a\u093e\u0902\u0926\u0940 \u2022 \u0938\u094b\u0928\u093e \u2022 \u0939\u0940\u0930\u093e \u0925\u094b\u0915', ratelist: '\u0930\u0947\u091f \u0932\u093f\u0938\u094d\u091f', schemes: '\u0938\u094d\u0915\u0940\u092e\u094d\u0938', brands: '\u0939\u092e\u093e\u0930\u0947 \u092c\u094d\u0930\u093e\u0902\u0921', showroom: '\u0936\u094b\u0930\u0942\u092e \u092b\u094b\u091f\u094b', exhibition: '\u092a\u094d\u0930\u0926\u0930\u094d\u0936\u0928\u0940', tapToExpand: '\u0935\u093f\u0938\u094d\u0924\u093e\u0930 \u0926\u0947\u0916\u0928\u0947 \u0915\u0947 \u0932\u093f\u090f \u0915\u093f\u0938\u0940 \u092d\u0940 \u092a\u0949\u0907\u0902\u091f \u092a\u0930 \u091f\u0948\u092a \u0915\u0930\u0947\u0902' },
    pa: { title: '\u0a2f\u0a36 \u0a14\u0a30\u0a28\u0a3e\u0a2e\u0a48\u0a02\u0a1f\u0a38 \u0a2c\u0a3e\u0a30\u0a47', whyBuy: '\u0a38\u0a3e\u0a21\u0a47 \u0a15\u0a4b\u0a32\u0a4b\u0a02 \u0a16\u0a30\u0a40\u0a26\u0a4b', newBenefits: '\u0a28\u0a35\u0a40\u0a02 \u0a26\u0a41\u0a15\u0a3e\u0a28 \u0a26\u0a47 \u0a32\u0a3e\u0a2d', b2b: 'B2B \u0a25\u0a4b\u0a15 \u0a32\u0a3e\u0a2d', locations: '\u0a38\u0a3e\u0a21\u0a47 \u0a1f\u0a3f\u0a15\u0a3e\u0a23\u0a47', quickLinks: '\u0a39\u0a4b\u0a30 \u0a35\u0a47\u0a16\u0a4b', subtitle: '\u0a2a\u0a4d\u0a30\u0a40\u0a2e\u0a40\u0a05\u0a2e \u0a1a\u0a3e\u0a02\u0a26\u0a40 \u2022 \u0a38\u0a4b\u0a28\u0a3e \u2022 \u0a39\u0a40\u0a30\u0a3e \u0a25\u0a4b\u0a15', ratelist: '\u0a30\u0a47\u0a1f \u0a32\u0a3f\u0a38\u0a1f', schemes: '\u0a38\u0a15\u0a40\u0a2e\u0a3e\u0a02', brands: '\u0a38\u0a3e\u0a21\u0a47 \u0a2c\u0a4d\u0a30\u0a3e\u0a02\u0a21', showroom: '\u0a36\u0a4b\u0a05\u0a30\u0a42\u0a2e \u0a2b\u0a4b\u0a1f\u0a4b', exhibition: '\u0a2a\u0a4d\u0a30\u0a26\u0a30\u0a36\u0a28\u0a40', tapToExpand: '\u0a35\u0a47\u0a30\u0a35\u0a47 \u0a26\u0a47\u0a16\u0a23 \u0a32\u0a08 \u0a15\u0a3f\u0a38\u0a47 \u0a35\u0a40 \u0a2a\u0a41\u0a06\u0a07\u0a02\u0a1f \u0a24\u0a47 \u0a1f\u0a48\u0a2a \u0a15\u0a30\u0a4b' },
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

        {/* Why Buy - Clickable expandable points */}
        <View style={st.section}>
          <Text style={st.sectionTitle}>{t.whyBuy}</Text>
          <Text style={st.tapHint}>{t.tapToExpand}</Text>
          {renderClickableBullets(getContent('why_buy'), 'why_buy')}
        </View>

        {/* New Shop Benefits */}
        <View style={st.section}>
          <Text style={st.sectionTitle}>{t.newBenefits}</Text>
          <View style={st.bulletList}>
            {renderBullets(getContent('new_shop_benefits'))}
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
  sectionTitle: { fontSize: FontSize.sm, fontWeight: '700', color: Colors.gold, letterSpacing: 2, marginBottom: Spacing.sm, textTransform: 'uppercase' },
  tapHint: { fontSize: FontSize.xs, color: Colors.textMuted, fontStyle: 'italic', marginBottom: Spacing.sm },
  introText: { fontSize: FontSize.md, color: Colors.textSecondary, lineHeight: 22 },
  bulletList: { gap: 10 },
  bulletRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
  bulletText: { flex: 1, fontSize: FontSize.md, color: Colors.text, lineHeight: 20 },
  pointCard: { backgroundColor: Colors.card, borderRadius: 12, padding: Spacing.md, marginBottom: 8, borderWidth: 1, borderColor: Colors.cardBorder },
  pointHeader: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  pointTitle: { flex: 1, fontSize: FontSize.md, color: Colors.text, fontWeight: '600' },
  pointDetail: { fontSize: FontSize.sm, color: Colors.textSecondary, lineHeight: 20, marginTop: Spacing.sm, paddingLeft: 30 },
  locationCard: { backgroundColor: Colors.card, borderRadius: 14, padding: Spacing.md, marginBottom: Spacing.md, borderWidth: 1, borderColor: Colors.cardBorder },
  locationHeader: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: Spacing.sm },
  locationTitle: { fontSize: FontSize.base, fontWeight: '700', color: Colors.text },
  locationDetail: { fontSize: FontSize.sm, color: Colors.textSecondary, lineHeight: 20, paddingLeft: 32 },
  linksGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  linkCard: { width: '30%', backgroundColor: Colors.card, borderRadius: 14, padding: Spacing.md, alignItems: 'center', gap: 8, borderWidth: 1, borderColor: Colors.cardBorder },
  linkLabel: { fontSize: FontSize.xs, color: Colors.textSecondary, textAlign: 'center', fontWeight: '500' },
});
