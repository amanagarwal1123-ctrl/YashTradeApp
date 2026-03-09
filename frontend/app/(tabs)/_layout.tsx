import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { TouchableOpacity, Linking, View, StyleSheet } from 'react-native';
import { Colors } from '../../src/theme';
import { useLang } from '../../src/context/LanguageContext';

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
  const label = (key: string) => TAB_LABELS[key]?.[language] || TAB_LABELS[key]?.en || key;

  return (
    <View style={{ flex: 1 }}>
      <Tabs screenOptions={{
        headerShown: false,
        tabBarStyle: { backgroundColor: Colors.surface, borderTopColor: Colors.border, borderTopWidth: 0.5, height: 60, paddingBottom: 8, paddingTop: 8 },
        tabBarActiveTintColor: Colors.gold,
        tabBarInactiveTintColor: Colors.textMuted,
        tabBarLabelStyle: { fontSize: 9, fontWeight: '600', letterSpacing: 0.3 },
      }}>
        <Tabs.Screen name="index" options={{ title: label('home'), tabBarIcon: ({ color, size }) => <Ionicons name="home" size={size} color={color} /> }} />
        <Tabs.Screen name="feed" options={{ title: label('feed'), tabBarIcon: ({ color, size }) => <Ionicons name="grid" size={size} color={color} /> }} />
        <Tabs.Screen name="calculator" options={{ title: label('calculator'), tabBarIcon: ({ color, size }) => <Ionicons name="calculator" size={size} color={color} /> }} />
        <Tabs.Screen name="about" options={{ title: label('about'), tabBarIcon: ({ color, size }) => <Ionicons name="information-circle" size={size} color={color} /> }} />
        <Tabs.Screen name="profile" options={{ title: label('profile'), tabBarIcon: ({ color, size }) => <Ionicons name="person" size={size} color={color} /> }} />
      </Tabs>

      {/* POINT 6: Permanent floating WhatsApp icon */}
      <TouchableOpacity
        data-testid="whatsapp-fab"
        style={fabStyles.whatsappFab}
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
    bottom: 75,
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
