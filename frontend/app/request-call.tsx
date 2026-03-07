import React, { useState } from 'react';
import { View, Text, StyleSheet, TextInput, TouchableOpacity, ScrollView, ActivityIndicator, Alert, KeyboardAvoidingView, Platform } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api } from '../src/api';

const REQUEST_TYPES = [
  { key: 'call', label: 'Request Call', icon: 'call', color: Colors.success },
  { key: 'video_call', label: 'Video Call', icon: 'videocam', color: Colors.info },
  { key: 'ask_price', label: 'Ask Price', icon: 'pricetag', color: Colors.gold },
  { key: 'ask_similar', label: 'Ask Similar', icon: 'copy', color: '#A855F7' },
  { key: 'hold_item', label: 'Hold Item', icon: 'bookmark', color: Colors.warning },
  { key: 'quick_reorder', label: 'Quick Reorder', icon: 'refresh', color: Colors.silver },
];

const TIME_SLOTS = ['Immediately', 'Within 1 hour', 'Later today', 'Tomorrow morning', 'Tomorrow afternoon'];
const CATEGORIES = ['Silver Payal', 'Silver Chains', 'Silver Articles', 'Gold Necklace', 'Gold Bangles', 'Diamond Ring', 'Silver Gifting', 'Silver Coins', 'Other'];

export default function RequestCallScreen() {
  const params = useLocalSearchParams<{ type?: string; productId?: string }>();
  const router = useRouter();
  const [requestType, setRequestType] = useState(params.type || 'call');
  const [category, setCategory] = useState('');
  const [timeSlot, setTimeSlot] = useState('');
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    if (!requestType) { Alert.alert('Error', 'Select a request type'); return; }
    setLoading(true);
    try {
      await api.post('/requests', {
        request_type: requestType,
        category,
        preferred_time: timeSlot,
        notes,
        product_id: params.productId || '',
      });
      Alert.alert('Request Sent!', 'Our team will contact you shortly.', [{ text: 'OK', onPress: () => router.back() }]);
    } catch (e: any) {
      Alert.alert('Error', e.message || 'Failed to send request');
    } finally { setLoading(false); }
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={{ flex: 1 }}>
        <ScrollView showsVerticalScrollIndicator={false}>
          <View style={styles.header}>
            <TouchableOpacity testID="back-btn" onPress={() => router.back()} style={styles.backBtn}>
              <Ionicons name="close" size={24} color={Colors.text} />
            </TouchableOpacity>
            <Text style={styles.headerTitle}>Contact Us</Text>
            <View style={{ width: 44 }} />
          </View>

          {/* Request Type */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>REQUEST TYPE</Text>
            <View style={styles.typesGrid}>
              {REQUEST_TYPES.map(t => (
                <TouchableOpacity key={t.key} testID={`type-${t.key}`} style={[styles.typeCard, requestType === t.key && { borderColor: t.color }]} onPress={() => setRequestType(t.key)}>
                  <Ionicons name={t.icon as any} size={20} color={requestType === t.key ? t.color : Colors.textMuted} />
                  <Text style={[styles.typeLabel, requestType === t.key && { color: t.color }]}>{t.label}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>

          {/* Category */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>CATEGORY OF INTEREST</Text>
            <View style={styles.chipsRow}>
              {CATEGORIES.map(c => (
                <TouchableOpacity key={c} style={[styles.chip, category === c && styles.chipActive]} onPress={() => setCategory(c)}>
                  <Text style={[styles.chipText, category === c && styles.chipTextActive]}>{c}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>

          {/* Time Slot */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>PREFERRED TIME</Text>
            {TIME_SLOTS.map(t => (
              <TouchableOpacity key={t} testID={`time-${t}`} style={[styles.slotItem, timeSlot === t && styles.slotActive]} onPress={() => setTimeSlot(t)}>
                <Text style={[styles.slotText, timeSlot === t && styles.slotTextActive]}>{t}</Text>
                {timeSlot === t && <Ionicons name="checkmark-circle" size={18} color={Colors.gold} />}
              </TouchableOpacity>
            ))}
          </View>

          {/* Notes */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>NOTES (OPTIONAL)</Text>
            <TextInput testID="notes-input" style={styles.notesInput} placeholder="What would you like to see or discuss?" placeholderTextColor={Colors.textMuted} value={notes} onChangeText={setNotes} multiline numberOfLines={3} />
          </View>

          {/* Submit */}
          <TouchableOpacity testID="submit-request-btn" style={styles.submitBtn} onPress={handleSubmit} disabled={loading}>
            {loading ? <ActivityIndicator color="#000" /> : <Text style={styles.submitBtnText}>SEND REQUEST</Text>}
          </TouchableOpacity>

          <View style={{ height: 40 }} />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md },
  backBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: Colors.surface, alignItems: 'center', justifyContent: 'center' },
  headerTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text },
  section: { paddingHorizontal: Spacing.lg, marginBottom: Spacing.lg },
  sectionTitle: { fontSize: FontSize.xs, color: Colors.textSecondary, letterSpacing: 2, fontWeight: '700', marginBottom: Spacing.md },
  typesGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  typeCard: { width: '31%', alignItems: 'center', paddingVertical: 14, borderRadius: 12, backgroundColor: Colors.card, borderWidth: 1.5, borderColor: Colors.border, gap: 6 },
  typeLabel: { fontSize: FontSize.xs, color: Colors.textSecondary, fontWeight: '500', textAlign: 'center' },
  chipsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 20, backgroundColor: Colors.surface, borderWidth: 1, borderColor: Colors.border },
  chipActive: { backgroundColor: Colors.gold + '20', borderColor: Colors.gold },
  chipText: { fontSize: FontSize.sm, color: Colors.textSecondary },
  chipTextActive: { color: Colors.gold, fontWeight: '600' },
  slotItem: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 14, paddingHorizontal: Spacing.md, marginBottom: 6, borderRadius: 10, backgroundColor: Colors.surface, borderWidth: 1, borderColor: Colors.border },
  slotActive: { borderColor: Colors.gold, backgroundColor: Colors.gold + '10' },
  slotText: { fontSize: FontSize.md, color: Colors.textSecondary },
  slotTextActive: { color: Colors.gold, fontWeight: '600' },
  notesInput: { backgroundColor: Colors.surface, borderRadius: 12, padding: Spacing.md, fontSize: FontSize.md, color: Colors.text, borderWidth: 1, borderColor: Colors.border, minHeight: 80, textAlignVertical: 'top' },
  submitBtn: { marginHorizontal: Spacing.lg, backgroundColor: Colors.gold, paddingVertical: 16, borderRadius: 12, alignItems: 'center', marginTop: Spacing.sm },
  submitBtnText: { fontSize: FontSize.md, fontWeight: '700', color: '#000', letterSpacing: 2 },
});
