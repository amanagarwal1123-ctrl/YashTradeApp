import { Tabs, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { TouchableOpacity, Linking, View, StyleSheet, ActivityIndicator, Platform } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as NavigationBar from 'expo-navigation-bar';
import { Colors } from '../../src/theme';
import { useLang } from '../../src/context/LanguageContext';
import { useAuth } from '../../src/context/AuthContext';
import { useEffect } from 'react';

const TAB_LABELS: Record<string, Record<string, string>> = {
  home: { en: 'Home', hi: 'होम', pa: 'ਹੋਮ' },
  feed: { en: 'Feed', hi: 'फीड', pa: 'ਫੀਡ' },
  calculator: { en: 'Calculator', hi: 'कैलकुलेटर', pa: 'ਕੈਲਕੁਲੇਟਰ' },
  about: { en: 'About', hi: 'हमारे बारे में', pa: 'ਸਾਡੇ ਬਾਰੇ' },
  profile: { en: 'Profile', hi: 'प्रोफाइल', pa: 'ਪ੍ਰੋਫਾਈਲ' },
};

const openWhatsApp = () => {
  const phone = '919999813334';
  const message = encodeURIComponent('Hi, I am interested in silver jewellery from Yash Trade. Please share your latest collection and prices.');
  Linking.openURL(`https://wa.me/${phone}?text=${message}`);
};

export default function TabLayout() {
  const { language } = useLang();
  const { user, loading } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const label = (key: string) => TAB_LABELS[key]?.[language] || TAB_LABELS[key]?.en || key;

  // Tab bar sizing: content height + actual device bottom inset.
  // Works with Android 3-button nav, Android gesture nav (edge-to-edge) and the iOS home indicator.
  const TAB_CONTENT_HEIGHT = 56;
  const bottomInset = insets.bottom;
  const tabBarHeight = TAB_CONTENT_HEIGHT + bottomInset;

  useEffect(() => {
    if (!loading) {
      if (!user) router.replace('/login');
      else if (user.role === 'executive') router.replace('/telecaller');
      else if (user.role === 'admin' || user.role === 'billing_executive') router.replace('/panel');
    }
  }, [loading, user]);

  // Match Android navigation bar buttons to the dark theme (edge-to-edge safe)
  useEffect(() => {
    if (Platform.OS === 'android') {
      NavigationBar.setButtonStyleAsync('light').catch(() => {});
    }
  }, []);

  if (loading) {
    return <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: Colors.background }}><ActivityIndicator size="large" color={Colors.gold} /></View>;
  }

  // Customer-only area — other roles are redirected above
  if (!user || user.role !== 'customer') return null;

  return (
    <View style={{ flex: 1 }}>
      <Tabs screenOptions={{
        headerShown: false,
        tabBarHideOnKeyboard: true,
        tabBarStyle: {
          backgroundColor: Colors.surface,
          borderTopColor: Colors.border,
          borderTopWidth: 0.5,
          height: tabBarHeight,
          paddingBottom: Math.max(bottomInset, 6),
          paddingTop: 6,
        },
        tabBarActiveTintColor: Colors.gold,
        tabBarInactiveTintColor: Colors.textMuted,
        tabBarLabelStyle: { fontSize: 10, fontWeight: '600' },
        tabBarItemStyle: { minHeight: 44, paddingVertical: 2 },
        tabBarAllowFontScaling: false,
      }}>
        <Tabs.Screen name="index" options={{ title: label('home'), tabBarIcon: ({ color, size }) => <Ionicons name="home" size={size} color={color} /> }} />
        <Tabs.Screen name="feed" options={{ title: label('feed'), tabBarIcon: ({ color, size }) => <Ionicons name="grid" size={size} color={color} /> }} />
        <Tabs.Screen name="calculator" options={{ title: label('calculator'), tabBarIcon: ({ color, size }) => <Ionicons name="calculator" size={size} color={color} /> }} />
        <Tabs.Screen name="about" options={{ title: label('about'), tabBarIcon: ({ color, size }) => <Ionicons name="information-circle" size={size} color={color} /> }} />
        <Tabs.Screen name="profile" options={{ title: label('profile'), tabBarIcon: ({ color, size }) => <Ionicons name="person" size={size} color={color} /> }} />
      </Tabs>

      {/* Permanent floating WhatsApp icon — positioned above tab bar + system nav */}
      <TouchableOpacity
        data-testid="whatsapp-fab"
        style={[fabStyles.whatsappFab, { bottom: tabBarHeight + 16 }]}
        onPress={openWhatsApp}
        activeOpacity={0.8}
      >
        <Ionicons name="logo-whatsapp" size={28} color="#fff" />
      </TouchableOpacity>
    </View>
  );
}

const fabStyles = StyleSheet.create({
  whatsappFab: {
    position: 'absolute',
    right: 16,
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: '#25D366',
    alignItems: 'center',
    justifyContent: 'center',
    elevation: 8,
    shadowColor: '#25D366',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.4,
    shadowRadius: 8,
    zIndex: 999,
  },
});
