import React, { useEffect } from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';

export default function RequestSuccessScreen() {
  const router = useRouter();
  const { type, time } = useLocalSearchParams<{ type?: string; time?: string }>();

  useEffect(() => {
    const timer = setTimeout(() => router.replace('/(tabs)'), 4000);
    return () => clearTimeout(timer);
  }, []);

  const typeLabel = type?.replace(/_/g, ' ') || 'Request';
  const timeMsg = time === 'Immediately' ? 'You will receive a callback immediately.'
    : time?.includes('5') ? 'You will receive a callback within 5 minutes.'
    : time?.includes('1 hour') ? 'You will receive a callback within 1 hour.'
    : time ? `Preferred time: ${time}` : 'Our team will contact you shortly.';

  return (
    <SafeAreaView style={s.container}>
      <View style={s.content}>
        <View style={s.iconCircle}>
          <Ionicons name="checkmark" size={56} color="#000" />
        </View>
        <Text style={s.title}>Request Sent!</Text>
        <Text style={s.subtitle}>{typeLabel.charAt(0).toUpperCase() + typeLabel.slice(1)}</Text>
        <View style={s.divider} />
        <Text style={s.timeText}>{timeMsg}</Text>
        <Text style={s.thankYou}>Thank you for choosing</Text>
        <Text style={s.brand}>YASH TRADE</Text>
        <Text style={s.redirect}>Redirecting to home...</Text>
      </View>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  content: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingHorizontal: Spacing.xl },
  iconCircle: { width: 96, height: 96, borderRadius: 48, backgroundColor: Colors.gold, alignItems: 'center', justifyContent: 'center', marginBottom: Spacing.xl },
  title: { fontSize: FontSize.xxl, fontWeight: '700', color: Colors.text, marginBottom: 8 },
  subtitle: { fontSize: FontSize.lg, color: Colors.textSecondary, textTransform: 'capitalize' },
  divider: { width: 60, height: 2, backgroundColor: Colors.gold, marginVertical: Spacing.xl, borderRadius: 1 },
  timeText: { fontSize: FontSize.md, color: Colors.gold, fontWeight: '600', textAlign: 'center', marginBottom: Spacing.xl, lineHeight: 24 },
  thankYou: { fontSize: FontSize.md, color: Colors.textSecondary, marginBottom: 4 },
  brand: { fontSize: FontSize.xl, fontWeight: '700', color: Colors.gold, letterSpacing: 3 },
  redirect: { fontSize: FontSize.xs, color: Colors.textMuted, marginTop: Spacing.xl },
});
