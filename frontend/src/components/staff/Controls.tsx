import React from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Colors } from '../../theme';

export const ui = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Colors.background }, content: { padding: 20, gap: 20, paddingBottom: 44 },
  guard: { flex: 1, backgroundColor: Colors.background, padding: 24, paddingTop: 48, gap: 20 },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 20 },
  title: { color: Colors.text, fontSize: 28, fontWeight: '700', flex: 1 },
  text: { color: Colors.text, fontSize: 16, lineHeight: 24 }, muted: { color: Colors.textSecondary, fontSize: 13, lineHeight: 20 },
  label: { color: Colors.gold, fontSize: 12, fontWeight: '700', letterSpacing: 1 },
  card: { backgroundColor: Colors.card, borderRadius: 14, padding: 18, gap: 10, borderWidth: 1, borderColor: Colors.border },
  row: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 8 },
  button: { minHeight: 44, borderRadius: 10, paddingVertical: 12, paddingHorizontal: 16, backgroundColor: Colors.surface, borderWidth: 1, borderColor: Colors.border, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8 },
  active: { borderColor: Colors.gold, backgroundColor: Colors.borderGold },
  input: { color: Colors.text, borderWidth: 1, borderColor: Colors.border, backgroundColor: Colors.surface, paddingHorizontal: 14, paddingVertical: 12, borderRadius: 10, minHeight: 48, fontSize: 15 },
  error: { color: Colors.error, fontSize: 14, lineHeight: 22 }, success: { color: Colors.success },
  image: { width: '100%', aspectRatio: 1, borderRadius: 12, backgroundColor: Colors.surface },
});

export function Button({ id, title, onPress, active, disabled, icon }: { id: string; title: string; onPress: () => void; active?: boolean; disabled?: boolean; icon?: keyof typeof Ionicons.glyphMap }) {
  return <Pressable testID={id} accessibilityRole="button" accessibilityLabel={title} disabled={disabled} onPress={onPress} style={({ pressed }) => [ui.button, active && ui.active, { opacity: disabled ? 0.4 : pressed ? 0.65 : 1 }]}>
    {icon && <Ionicons name={icon} size={18} color={Colors.gold}/>}<Text style={ui.text}>{title}</Text>
  </Pressable>;
}
export function Input({ id, label, value, onChange, multiline = false }: { id: string; label: string; value: string; onChange: (s: string) => void; multiline?: boolean }) {
  return <View style={{ gap: 8 }}><Text testID={`${id}-label`} style={ui.muted}>{label}</Text><TextInput testID={id} accessibilityLabel={label} value={value} onChangeText={onChange} style={ui.input} placeholderTextColor={Colors.textMuted} multiline={multiline} /></View>;
}
export function Busy() { return <ActivityIndicator testID="staff-loading" color={Colors.gold}/>; }
export const dateText = (s?: string) => s ? new Date(s).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }) + ' IST' : 'Not recorded';
export const duration = (s?: number | null) => s == null ? 'Unknown' : `${Math.floor(s / 3600)}h ${Math.floor(s % 3600 / 60)}m`;