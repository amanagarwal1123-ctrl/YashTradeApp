import React, { useState } from 'react';
import { View, Text, StyleSheet, TextInput, TouchableOpacity, ScrollView, KeyboardAvoidingView, Platform, Modal, FlatList } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../../src/theme';

const ITEM_PRESETS = ['Silver Payal', 'Silver Chain', 'Silver Ring', 'Silver Article', 'Silver Gift Item', 'Silver Bowl', 'Silver Pooja Item', 'Silver Bracelet', 'Silver Anklet', 'Silver Coin', 'Silver Kadaa', 'Silver Toe Ring', 'Silver Necklace', 'Silver Earring', 'Silver Pendant', 'Silver Dinner Set', 'Gold Chain', 'Gold Necklace', 'Gold Ring', 'Gold Bangles', 'Diamond Ring', 'Diamond Pendant'];

interface CalcItem { name: string; weight: string; rate: string; making: string; }

function ItemSelector({ value, onChange, testID }: { value: string; onChange: (v: string) => void; testID?: string }) {
  const [show, setShow] = useState(false);
  const [search, setSearch] = useState('');
  const filtered = ITEM_PRESETS.filter(i => i.toLowerCase().includes(search.toLowerCase()));
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>Item Name</Text>
      <TouchableOpacity testID={testID} style={styles.selectorBtn} onPress={() => setShow(true)}>
        <Text style={value ? styles.selectorText : styles.selectorPlaceholder}>{value || 'Select or type item name'}</Text>
        <Ionicons name="chevron-down" size={16} color={Colors.textMuted} />
      </TouchableOpacity>
      <Modal visible={show} transparent animationType="slide">
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Select Item</Text>
              <TouchableOpacity onPress={() => setShow(false)}><Ionicons name="close" size={24} color={Colors.text} /></TouchableOpacity>
            </View>
            <TextInput style={styles.modalSearch} placeholder="Search or type custom name..." placeholderTextColor={Colors.textMuted} value={search} onChangeText={setSearch} autoFocus />
            <FlatList data={filtered} keyExtractor={i => i} renderItem={({ item }) => (
              <TouchableOpacity style={styles.modalItem} onPress={() => { onChange(item); setShow(false); setSearch(''); }}>
                <Ionicons name="diamond-outline" size={16} color={Colors.gold} />
                <Text style={styles.modalItemText}>{item}</Text>
              </TouchableOpacity>
            )} ListEmptyComponent={search.length > 0 ? (
              <TouchableOpacity style={styles.modalItem} onPress={() => { onChange(search); setShow(false); setSearch(''); }}>
                <Ionicons name="add" size={16} color={Colors.success} />
                <Text style={[styles.modalItemText, { color: Colors.success }]}>Use "{search}"</Text>
              </TouchableOpacity>
            ) : null} />
          </View>
        </View>
      </Modal>
    </View>
  );
}

export default function CalculatorScreen() {
  const [mode, setMode] = useState<'single' | 'multi'>('single');
  const [gstPercent, setGstPercent] = useState('3');
  const [discount, setDiscount] = useState('0');

  // Single item
  const [itemName, setItemName] = useState('');
  const [weight, setWeight] = useState('');
  const [rate, setRate] = useState('');
  const [making, setMaking] = useState('');

  // Multi items
  const [items, setItems] = useState<CalcItem[]>([{ name: '', weight: '', rate: '', making: '' }]);

  const calc = (w: string, r: string, m: string) => {
    const wt = parseFloat(w) || 0;
    const rt = parseFloat(r) || 0;
    const mk = parseFloat(m) || 0;
    return wt * rt + mk;
  };

  const singleBase = calc(weight, rate, making);
  const singleDisc = parseFloat(discount) || 0;
  const singleAfterDisc = Math.max(0, singleBase - singleDisc);
  const singleGST = singleAfterDisc * (parseFloat(gstPercent) || 0) / 100;
  const singleTotal = singleAfterDisc + singleGST;

  const multiBase = items.reduce((sum, i) => sum + calc(i.weight, i.rate, i.making), 0);
  const multiGST = multiBase * (parseFloat(gstPercent) || 0) / 100;
  const multiTotal = multiBase + multiGST;

  const addItem = () => setItems([...items, { name: '', weight: '', rate: '', making: '' }]);
  const updateItem = (idx: number, field: keyof CalcItem, val: string) => {
    const newItems = [...items];
    newItems[idx] = { ...newItems[idx], [field]: val };
    setItems(newItems);
  };
  const removeItem = (idx: number) => { if (items.length > 1) setItems(items.filter((_, i) => i !== idx)); };

  const clearAll = () => {
    setItemName(''); setWeight(''); setRate(''); setMaking(''); setDiscount('0');
    setItems([{ name: '', weight: '', rate: '', making: '' }]);
  };

  const InputField = ({ label, value, onChangeText, placeholder, testID }: any) => (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput testID={testID} style={styles.fieldInput} value={value} onChangeText={onChangeText} placeholder={placeholder} placeholderTextColor={Colors.textMuted} keyboardType="decimal-pad" />
    </View>
  );

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={{ flex: 1 }}>
        <ScrollView showsVerticalScrollIndicator={false}>
          <View style={styles.header}>
            <Ionicons name="calculator" size={28} color={Colors.gold} />
            <Text style={styles.headerTitle}>Silver Calculator</Text>
          </View>

          {/* Mode Toggle */}
          <View style={styles.modeRow}>
            <TouchableOpacity testID="single-mode-btn" style={[styles.modeBtn, mode === 'single' && styles.modeBtnActive]} onPress={() => setMode('single')}>
              <Text style={[styles.modeBtnText, mode === 'single' && styles.modeBtnTextActive]}>Single Item</Text>
            </TouchableOpacity>
            <TouchableOpacity testID="multi-mode-btn" style={[styles.modeBtn, mode === 'multi' && styles.modeBtnActive]} onPress={() => setMode('multi')}>
              <Text style={[styles.modeBtnText, mode === 'multi' && styles.modeBtnTextActive]}>Multi Item Bill</Text>
            </TouchableOpacity>
          </View>

          {mode === 'single' ? (
            <View style={styles.calcCard}>
              <ItemSelector testID="item-name-input" value={itemName} onChange={setItemName} />
              <View style={styles.row}>
                <View style={{ flex: 1 }}><InputField testID="weight-input" label="Weight (grams)" value={weight} onChangeText={setWeight} placeholder="0" /></View>
                <View style={{ flex: 1 }}><InputField testID="rate-input" label="Rate (₹/gram)" value={rate} onChangeText={setRate} placeholder="0" /></View>
              </View>
              <View style={styles.row}>
                <View style={{ flex: 1 }}><InputField testID="making-input" label="Making (₹)" value={making} onChangeText={setMaking} placeholder="0" /></View>
                <View style={{ flex: 1 }}><InputField testID="discount-input" label="Discount (₹)" value={discount} onChangeText={setDiscount} placeholder="0" /></View>
              </View>
              <InputField testID="gst-input" label="GST %" value={gstPercent} onChangeText={setGstPercent} placeholder="3" />

              <View style={styles.resultCard}>
                <View style={styles.resultRow}><Text style={styles.resultLabel}>Base Amount</Text><Text style={styles.resultValue}>₹{singleBase.toFixed(2)}</Text></View>
                {singleDisc > 0 && <View style={styles.resultRow}><Text style={styles.resultLabel}>Discount</Text><Text style={[styles.resultValue, { color: Colors.success }]}>-₹{singleDisc.toFixed(2)}</Text></View>}
                <View style={styles.resultRow}><Text style={styles.resultLabel}>GST ({gstPercent}%)</Text><Text style={styles.resultValue}>₹{singleGST.toFixed(2)}</Text></View>
                <View style={styles.divider} />
                <View style={styles.resultRow}><Text style={styles.totalLabel}>TOTAL</Text><Text style={styles.totalValue}>₹{singleTotal.toFixed(2)}</Text></View>
              </View>
            </View>
          ) : (
            <View style={styles.calcCard}>
              {items.map((item, idx) => (
                <View key={idx} style={styles.multiItemRow}>
                  <View style={styles.multiItemHeader}>
                    <Text style={styles.multiItemTitle}>Item {idx + 1}</Text>
                    {items.length > 1 && <TouchableOpacity onPress={() => removeItem(idx)}><Ionicons name="close-circle" size={20} color={Colors.error} /></TouchableOpacity>}
                  </View>
                  <ItemSelector value={item.name} onChange={v => updateItem(idx, 'name', v)} />
                  <View style={styles.row}>
                    <TextInput style={[styles.miniInput, { flex: 1 }]} placeholder="Weight (g)" placeholderTextColor={Colors.textMuted} keyboardType="decimal-pad" value={item.weight} onChangeText={v => updateItem(idx, 'weight', v)} />
                    <TextInput style={[styles.miniInput, { flex: 1 }]} placeholder="Rate ₹/g" placeholderTextColor={Colors.textMuted} keyboardType="decimal-pad" value={item.rate} onChangeText={v => updateItem(idx, 'rate', v)} />
                    <TextInput style={[styles.miniInput, { flex: 1 }]} placeholder="Making ₹" placeholderTextColor={Colors.textMuted} keyboardType="decimal-pad" value={item.making} onChangeText={v => updateItem(idx, 'making', v)} />
                  </View>
                  <Text style={styles.itemTotal}>₹{calc(item.weight, item.rate, item.making).toFixed(2)}</Text>
                </View>
              ))}
              <TouchableOpacity testID="add-item-btn" style={styles.addBtn} onPress={addItem}>
                <Ionicons name="add-circle" size={20} color={Colors.gold} />
                <Text style={styles.addBtnText}>Add Item</Text>
              </TouchableOpacity>

              <InputField testID="multi-gst-input" label="GST %" value={gstPercent} onChangeText={setGstPercent} placeholder="3" />

              <View style={styles.resultCard}>
                {items.map((item, idx) => item.weight && item.rate ? (
                  <View key={idx} style={styles.resultRow}>
                    <Text style={styles.resultLabel} numberOfLines={1}>{item.name || `Item ${idx + 1}`}</Text>
                    <Text style={styles.resultValue}>₹{calc(item.weight, item.rate, item.making).toFixed(2)}</Text>
                  </View>
                ) : null)}
                <View style={styles.divider} />
                <View style={styles.resultRow}><Text style={styles.resultLabel}>Subtotal</Text><Text style={styles.resultValue}>₹{multiBase.toFixed(2)}</Text></View>
                <View style={styles.resultRow}><Text style={styles.resultLabel}>GST ({gstPercent}%)</Text><Text style={styles.resultValue}>₹{multiGST.toFixed(2)}</Text></View>
                <View style={styles.divider} />
                <View style={styles.resultRow}><Text style={styles.totalLabel}>GRAND TOTAL</Text><Text style={styles.totalValue}>₹{multiTotal.toFixed(2)}</Text></View>
              </View>
            </View>
          )}

          <TouchableOpacity testID="clear-btn" style={styles.clearBtn} onPress={clearAll}>
            <Text style={styles.clearBtnText}>Clear All</Text>
          </TouchableOpacity>

          <View style={{ height: 40 }} />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: Spacing.lg, paddingTop: Spacing.md, paddingBottom: Spacing.sm },
  headerTitle: { fontSize: FontSize.xl, fontWeight: '700', color: Colors.text },
  modeRow: { flexDirection: 'row', marginHorizontal: Spacing.lg, marginBottom: Spacing.md, backgroundColor: Colors.surface, borderRadius: 12, padding: 4 },
  modeBtn: { flex: 1, paddingVertical: 10, borderRadius: 10, alignItems: 'center' },
  modeBtnActive: { backgroundColor: Colors.gold },
  modeBtnText: { fontSize: FontSize.sm, fontWeight: '600', color: Colors.textSecondary },
  modeBtnTextActive: { color: '#000' },
  calcCard: { marginHorizontal: Spacing.lg, backgroundColor: Colors.card, borderRadius: 16, padding: Spacing.lg, borderWidth: 1, borderColor: Colors.cardBorder },
  field: { marginBottom: Spacing.md },
  fieldLabel: { fontSize: FontSize.xs, color: Colors.textSecondary, fontWeight: '600', letterSpacing: 1, marginBottom: 6 },
  fieldInput: { backgroundColor: Colors.surface, borderRadius: 10, paddingHorizontal: Spacing.md, paddingVertical: 12, fontSize: FontSize.base, color: Colors.text, borderWidth: 1, borderColor: Colors.border },
  row: { flexDirection: 'row', gap: Spacing.sm },
  resultCard: { backgroundColor: Colors.surface, borderRadius: 12, padding: Spacing.md, marginTop: Spacing.md },
  resultRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 6 },
  resultLabel: { fontSize: FontSize.sm, color: Colors.textSecondary, flex: 1 },
  resultValue: { fontSize: FontSize.sm, color: Colors.text, fontWeight: '600' },
  divider: { height: 1, backgroundColor: Colors.border, marginVertical: 8 },
  totalLabel: { fontSize: FontSize.base, color: Colors.gold, fontWeight: '700', letterSpacing: 1 },
  totalValue: { fontSize: FontSize.lg, color: Colors.gold, fontWeight: '700' },
  multiItemRow: { borderBottomWidth: 1, borderBottomColor: Colors.border, paddingBottom: Spacing.md, marginBottom: Spacing.md },
  multiItemHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: Spacing.sm },
  multiItemTitle: { fontSize: FontSize.sm, fontWeight: '600', color: Colors.textSecondary },
  miniInput: { backgroundColor: Colors.surface, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 10, fontSize: FontSize.sm, color: Colors.text, borderWidth: 1, borderColor: Colors.border, marginBottom: 6 },
  itemTotal: { fontSize: FontSize.sm, color: Colors.gold, fontWeight: '600', textAlign: 'right' },
  addBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 12, marginBottom: Spacing.md },
  addBtnText: { fontSize: FontSize.sm, color: Colors.gold, fontWeight: '600' },
  clearBtn: { marginHorizontal: Spacing.lg, marginTop: Spacing.md, paddingVertical: 14, borderRadius: 12, borderWidth: 1, borderColor: Colors.border, alignItems: 'center' },
  clearBtnText: { fontSize: FontSize.sm, color: Colors.textSecondary, fontWeight: '600' },
  selectorBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: Colors.surface, borderRadius: 10, paddingHorizontal: Spacing.md, paddingVertical: 14, borderWidth: 1, borderColor: Colors.border },
  selectorText: { fontSize: FontSize.base, color: Colors.text },
  selectorPlaceholder: { fontSize: FontSize.base, color: Colors.textMuted },
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'flex-end' },
  modalContent: { backgroundColor: Colors.card, borderTopLeftRadius: 20, borderTopRightRadius: 20, maxHeight: '70%', padding: Spacing.lg },
  modalHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: Spacing.md },
  modalTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text },
  modalSearch: { backgroundColor: Colors.surface, borderRadius: 10, paddingHorizontal: Spacing.md, paddingVertical: 12, fontSize: FontSize.md, color: Colors.text, borderWidth: 1, borderColor: Colors.border, marginBottom: Spacing.md },
  modalItem: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: Colors.border },
  modalItemText: { fontSize: FontSize.md, color: Colors.text },
});
