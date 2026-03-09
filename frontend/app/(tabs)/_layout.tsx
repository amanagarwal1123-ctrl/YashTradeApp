import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors } from '../../src/theme';
import { useLang } from '../../src/context/LanguageContext';

const TAB_LABELS: Record<string, Record<string, string>> = {
  home: { en: 'Home', hi: 'होम', pa: 'ਹੋਮ' },
  feed: { en: 'Feed', hi: 'फीड', pa: 'ਫੀਡ' },
  calculator: { en: 'Calculator', hi: 'कैलकुलेटर', pa: 'ਕੈਲਕੁਲੇਟਰ' },
  about: { en: 'About', hi: 'हमारे बारे में', pa: 'ਸਾਡੇ ਬਾਰੇ' },
  profile: { en: 'Profile', hi: 'प्रोफाइल', pa: 'ਪ੍ਰੋਫਾਈਲ' },
};

export default function TabLayout() {
  const { language } = useLang();
  const label = (key: string) => TAB_LABELS[key]?.[language] || TAB_LABELS[key]?.en || key;

  return (
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
  );
}
