import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors } from '../../src/theme';

export default function TabLayout() {
  return (
    <Tabs screenOptions={{
      headerShown: false,
      tabBarStyle: { backgroundColor: Colors.surface, borderTopColor: Colors.border, borderTopWidth: 0.5, height: 60, paddingBottom: 8, paddingTop: 8 },
      tabBarActiveTintColor: Colors.gold,
      tabBarInactiveTintColor: Colors.textMuted,
      tabBarLabelStyle: { fontSize: 10, fontWeight: '600', letterSpacing: 0.5 },
    }}>
      <Tabs.Screen name="index" options={{ title: 'Home', tabBarIcon: ({ color, size }) => <Ionicons name="home" size={size} color={color} /> }} />
      <Tabs.Screen name="feed" options={{ title: 'Feed', tabBarIcon: ({ color, size }) => <Ionicons name="grid" size={size} color={color} /> }} />
      <Tabs.Screen name="calculator" options={{ title: 'Calculator', tabBarIcon: ({ color, size }) => <Ionicons name="calculator" size={size} color={color} /> }} />
      <Tabs.Screen name="profile" options={{ title: 'Profile', tabBarIcon: ({ color, size }) => <Ionicons name="person" size={size} color={color} /> }} />
    </Tabs>
  );
}
