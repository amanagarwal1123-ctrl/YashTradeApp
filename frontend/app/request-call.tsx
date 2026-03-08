import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet, TextInput, TouchableOpacity, ScrollView, ActivityIndicator, KeyboardAvoidingView, Platform, Image, FlatList, Modal } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api, getImageUrl } from '../src/api';

const REQUEST_TYPES = [
  { key: 'call', label: 'Request Call', icon: 'call', color: Colors.success },
  { key: 'video_call', label: 'Video Call', icon: 'videocam', color: Colors.info },
  { key: 'ask_price', label: 'Ask Price', icon: 'pricetag', color: Colors.gold },
  { key: 'ask_similar', label: 'Ask Similar', icon: 'copy', color: '#A855F7' },
  { key: 'hold_item', label: 'Hold Item', icon: 'bookmark', color: Colors.warning },
  { key: 'quick_reorder', label: 'Reorder', icon: 'refresh', color: Colors.silver },
];
const TIME_SLOTS = ['Immediately', 'Within 5 minutes', 'Within 1 hour', 'Later today', 'Tomorrow morning'];
const CATEGORY_SHORTCUTS = ['Silver Payal', 'Silver Chain', 'Silver Bichiya', 'Silver Articles', 'Silver Coins', 'Gold Necklace', 'Gold Bangles', 'Diamond Ring', 'Other'];

export default function RequestCallScreen() {
  const params = useLocalSearchParams<{ type?: string; productId?: string }>();
  const router = useRouter();
  const [requestType, setRequestType] = useState(params.type || 'call');
  const [timeSlot, setTimeSlot] = useState('');
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);

  // Multi-product selection
  const [selectedProducts, setSelectedProducts] = useState<any[]>([]);
  const [showProductPicker, setShowProductPicker] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [searching, setSearching] = useState(false);
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);

  // Load initial product if passed via params
  useEffect(() => {
    if (params.productId) {
      (async () => {
        try {
          const p = await api.get(`/products/${params.productId}`);
          if (p && p.id) setSelectedProducts([p]);
        } catch {}
      })();
    }
  }, [params.productId]);

  const searchProducts = async (q: string) => {
    setSearchQuery(q);
    if (q.length < 2) { setSearchResults([]); return; }
    setSearching(true);
    try {
      const res = await api.get(`/products?search=${encodeURIComponent(q)}&limit=20`);
      setSearchResults(res.products || []);
    } catch {}
    finally { setSearching(false); }
  };

  const toggleProduct = (product: any) => {
    setSelectedProducts(prev => {
      const exists = prev.find(p => p.id === product.id);
      if (exists) return prev.filter(p => p.id !== product.id);
      return [...prev, product];
    });
  };

  const toggleCategory = (cat: string) => {
    setSelectedCategories(prev => prev.includes(cat) ? prev.filter(c => c !== cat) : [...prev, cat]);
  };

  const handleSubmit = async () => {
    if (!requestType) return;
    setLoading(true);
    try {
      const productIds = selectedProducts.map(p => p.id);
      const categoryStr = selectedCategories.join(', ');
      await api.post('/requests', {
        request_type: requestType,
        category: categoryStr,
        preferred_time: timeSlot,
        notes,
        product_id: productIds[0] || '',
        product_ids: productIds,
      });
      router.replace({ pathname: '/request-success', params: { type: requestType, time: timeSlot || 'soon' } });
    } catch (e: any) {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={st.container} edges={['top']}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={{ flex: 1 }}>
        <ScrollView showsVerticalScrollIndicator={false}>
          <View style={st.header}>
            <TouchableOpacity testID="back-btn" onPress={() => router.back()} style={st.backBtn}><Ionicons name="close" size={24} color={Colors.text} /></TouchableOpacity>
            <Text style={st.headerTitle}>Contact Us</Text>
            <View style={{ width: 44 }} />
          </View>

          {/* Request Type */}
          <View style={st.section}>
            <Text style={st.sectionTitle}>REQUEST TYPE</Text>
            <View style={st.typesGrid}>
              {REQUEST_TYPES.map(t => (
                <TouchableOpacity key={t.key} testID={`type-${t.key}`} style={[st.typeCard, requestType === t.key && { borderColor: t.color }]} onPress={() => setRequestType(t.key)}>
                  <Ionicons name={t.icon as any} size={20} color={requestType === t.key ? t.color : Colors.textMuted} />
                  <Text style={[st.typeLabel, requestType === t.key && { color: t.color }]}>{t.label}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>

          {/* Selected Products */}
          {selectedProducts.length > 0 && (
            <View style={st.section}>
              <Text style={st.sectionTitle}>SELECTED ITEMS ({selectedProducts.length})</Text>
              {selectedProducts.map(p => (
                <View key={p.id} style={st.selectedItem}>
                  <Image source={{ uri: getImageUrl(p, true) }} style={st.selectedImg} />
                  <View style={{ flex: 1 }}>
                    <Text style={st.selectedTitle} numberOfLines={1}>{p.title}</Text>
                    <Text style={st.selectedMeta}>{p.metal_type} {p.category ? `• ${p.category}` : ''}</Text>
                  </View>
                  <TouchableOpacity onPress={() => toggleProduct(p)}><Ionicons name="close-circle" size={20} color={Colors.error} /></TouchableOpacity>
                </View>
              ))}
            </View>
          )}

          {/* Add Products Button */}
          <View style={st.section}>
            <TouchableOpacity testID="add-products-btn" style={st.addItemBtn} onPress={() => setShowProductPicker(true)}>
              <Ionicons name="add-circle" size={20} color={Colors.gold} />
              <Text style={st.addItemText}>Add items from catalog</Text>
            </TouchableOpacity>
          </View>

          {/* Category Shortcuts */}
          <View style={st.section}>
            <Text style={st.sectionTitle}>CATEGORY INTEREST</Text>
            <View style={st.chipsRow}>
              {CATEGORY_SHORTCUTS.map(c => (
                <TouchableOpacity key={c} style={[st.chip, selectedCategories.includes(c) && st.chipActive]} onPress={() => toggleCategory(c)}>
                  <Text style={[st.chipText, selectedCategories.includes(c) && st.chipTextActive]}>{c}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>

          {/* Time Slot */}
          <View style={st.section}>
            <Text style={st.sectionTitle}>PREFERRED TIME</Text>
            {TIME_SLOTS.map(t => (
              <TouchableOpacity key={t} style={[st.slotItem, timeSlot === t && st.slotActive]} onPress={() => setTimeSlot(t)}>
                <Text style={[st.slotText, timeSlot === t && st.slotTextActive]}>{t}</Text>
                {timeSlot === t && <Ionicons name="checkmark-circle" size={18} color={Colors.gold} />}
              </TouchableOpacity>
            ))}
          </View>

          {/* Notes / Custom Requirement */}
          <View style={st.section}>
            <Text style={st.sectionTitle}>NOTES / CUSTOM REQUIREMENT</Text>
            <TextInput testID="notes-input" style={st.notesInput} placeholder="Describe what you need. e.g., Looking for heavy silver payal in 92.5 purity, budget 5000-8000" placeholderTextColor={Colors.textMuted} value={notes} onChangeText={setNotes} multiline numberOfLines={4} />
          </View>

          <TouchableOpacity testID="submit-request-btn" style={st.submitBtn} onPress={handleSubmit} disabled={loading}>
            {loading ? <ActivityIndicator color="#000" /> : <Text style={st.submitBtnText}>SEND REQUEST</Text>}
          </TouchableOpacity>

          <View style={{ height: 40 }} />
        </ScrollView>
      </KeyboardAvoidingView>

      {/* Product Picker Modal */}
      <Modal visible={showProductPicker} transparent animationType="slide">
        <View style={st.modalOverlay}>
          <View style={st.modalContent}>
            <View style={st.modalHeader}>
              <Text style={st.modalTitle}>Select Products</Text>
              <TouchableOpacity onPress={() => { setShowProductPicker(false); setSearchQuery(''); setSearchResults([]); }}><Ionicons name="close" size={24} color={Colors.text} /></TouchableOpacity>
            </View>
            <TextInput style={st.modalSearch} placeholder="Search by name, category..." placeholderTextColor={Colors.textMuted} value={searchQuery} onChangeText={searchProducts} autoFocus />
            {searching && <ActivityIndicator color={Colors.gold} style={{ padding: 10 }} />}
            <FlatList data={searchResults} keyExtractor={i => i.id} renderItem={({ item }) => {
              const isSelected = selectedProducts.some(p => p.id === item.id);
              return (
                <TouchableOpacity style={[st.pickerItem, isSelected && st.pickerItemSelected]} onPress={() => toggleProduct(item)}>
                  <Image source={{ uri: getImageUrl(item, true) }} style={st.pickerImg} />
                  <View style={{ flex: 1 }}>
                    <Text style={st.pickerTitle} numberOfLines={1}>{item.title}</Text>
                    <Text style={st.pickerMeta}>{item.metal_type} • {item.category}</Text>
                  </View>
                  <Ionicons name={isSelected ? 'checkmark-circle' : 'add-circle-outline'} size={22} color={isSelected ? Colors.gold : Colors.textMuted} />
                </TouchableOpacity>
              );
            }} ListEmptyComponent={searchQuery.length >= 2 && !searching ? <Text style={st.emptyText}>No products found</Text> : <Text style={st.emptyText}>Type to search...</Text>} />
            {selectedProducts.length > 0 && (
              <TouchableOpacity style={st.modalDone} onPress={() => { setShowProductPicker(false); setSearchQuery(''); setSearchResults([]); }}>
                <Text style={st.modalDoneText}>DONE ({selectedProducts.length} selected)</Text>
              </TouchableOpacity>
            )}
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md },
  backBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: Colors.surface, alignItems: 'center', justifyContent: 'center' },
  headerTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text },
  section: { paddingHorizontal: Spacing.lg, marginBottom: Spacing.lg },
  sectionTitle: { fontSize: FontSize.xs, color: Colors.textSecondary, letterSpacing: 2, fontWeight: '700', marginBottom: Spacing.md },
  typesGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  typeCard: { width: '31%', alignItems: 'center', paddingVertical: 14, borderRadius: 12, backgroundColor: Colors.card, borderWidth: 1.5, borderColor: Colors.border, gap: 6 },
  typeLabel: { fontSize: FontSize.xs, color: Colors.textSecondary, fontWeight: '500', textAlign: 'center' },
  selectedItem: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: Colors.card, borderRadius: 12, padding: 10, marginBottom: 8, borderWidth: 1, borderColor: Colors.borderGold },
  selectedImg: { width: 48, height: 48, borderRadius: 8, backgroundColor: Colors.surface },
  selectedTitle: { fontSize: FontSize.sm, fontWeight: '600', color: Colors.text },
  selectedMeta: { fontSize: FontSize.xs, color: Colors.textMuted, textTransform: 'capitalize' },
  addItemBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingVertical: 14, borderRadius: 12, borderWidth: 1.5, borderStyle: 'dashed', borderColor: Colors.gold + '40' },
  addItemText: { fontSize: FontSize.sm, color: Colors.gold, fontWeight: '600' },
  chipsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 20, backgroundColor: Colors.surface, borderWidth: 1, borderColor: Colors.border },
  chipActive: { backgroundColor: Colors.gold + '20', borderColor: Colors.gold },
  chipText: { fontSize: FontSize.sm, color: Colors.textSecondary },
  chipTextActive: { color: Colors.gold, fontWeight: '600' },
  slotItem: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 14, paddingHorizontal: Spacing.md, marginBottom: 6, borderRadius: 10, backgroundColor: Colors.surface, borderWidth: 1, borderColor: Colors.border },
  slotActive: { borderColor: Colors.gold, backgroundColor: Colors.gold + '10' },
  slotText: { fontSize: FontSize.md, color: Colors.textSecondary },
  slotTextActive: { color: Colors.gold, fontWeight: '600' },
  notesInput: { backgroundColor: Colors.surface, borderRadius: 12, padding: Spacing.md, fontSize: FontSize.md, color: Colors.text, borderWidth: 1, borderColor: Colors.border, minHeight: 100, textAlignVertical: 'top' },
  submitBtn: { marginHorizontal: Spacing.lg, backgroundColor: Colors.gold, paddingVertical: 16, borderRadius: 12, alignItems: 'center', marginTop: Spacing.sm },
  submitBtnText: { fontSize: FontSize.md, fontWeight: '700', color: '#000', letterSpacing: 2 },
  // Modal
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'flex-end' },
  modalContent: { backgroundColor: Colors.card, borderTopLeftRadius: 20, borderTopRightRadius: 20, maxHeight: '80%', padding: Spacing.lg },
  modalHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: Spacing.md },
  modalTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text },
  modalSearch: { backgroundColor: Colors.surface, borderRadius: 10, paddingHorizontal: Spacing.md, paddingVertical: 12, fontSize: FontSize.md, color: Colors.text, borderWidth: 1, borderColor: Colors.border, marginBottom: Spacing.md },
  pickerItem: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: Colors.border },
  pickerItemSelected: { backgroundColor: Colors.gold + '08' },
  pickerImg: { width: 44, height: 44, borderRadius: 8, backgroundColor: Colors.surface },
  pickerTitle: { fontSize: FontSize.sm, fontWeight: '600', color: Colors.text },
  pickerMeta: { fontSize: FontSize.xs, color: Colors.textMuted, textTransform: 'capitalize' },
  emptyText: { fontSize: FontSize.sm, color: Colors.textMuted, textAlign: 'center', paddingVertical: 20 },
  modalDone: { backgroundColor: Colors.gold, paddingVertical: 14, borderRadius: 10, alignItems: 'center', marginTop: Spacing.md },
  modalDoneText: { fontSize: FontSize.sm, fontWeight: '700', color: '#000', letterSpacing: 1 },
});
