import React, { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, Modal, StyleSheet, FlatList } from 'react-native';
import { Colors, Spacing, FontSize } from '../theme';
import { COUNTRIES, DEFAULT_COUNTRY } from '../phone';
import type { CountryCode } from 'libphonenumber-js';

type Props = {
  country: CountryCode;
  national: string;
  onChange: (country: CountryCode, national: string) => void;
  placeholder?: string;
  testID?: string;
  autoFocus?: boolean;
  editable?: boolean;
  inputStyle?: any;
};

/** Country selector (India default) + national-number input. Digits only; the caller converts to canonical form. */
export default function PhoneField({ country, national, onChange, placeholder, testID = 'phone-input', autoFocus, editable = true, inputStyle }: Props) {
  const [open, setOpen] = useState(false);
  const meta = COUNTRIES.find(c => c.code === country) || COUNTRIES[0];
  return (
    <View style={styles.row}>
      <TouchableOpacity testID={`${testID}-country`} style={styles.country} onPress={() => editable && setOpen(true)} accessibilityRole="button" accessibilityLabel={`Country ${meta.label} ${meta.dial}`}>
        <Text style={styles.flag}>{meta.flag}</Text>
        <Text style={styles.dial}>{meta.dial}</Text>
        <Text style={styles.caret}>{'\u25BE'}</Text>
      </TouchableOpacity>
      <TextInput
        testID={testID}
        style={[styles.input, inputStyle]}
        placeholder={placeholder || meta.example}
        placeholderTextColor={Colors.textMuted}
        keyboardType="phone-pad"
        maxLength={meta.maxDigits}
        value={national}
        autoFocus={autoFocus}
        editable={editable}
        onChangeText={v => onChange(country, v.replace(/[^0-9]/g, '').slice(0, meta.maxDigits))}
      />
      <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
        <TouchableOpacity style={styles.backdrop} activeOpacity={1} onPress={() => setOpen(false)}>
          <View style={styles.sheet}>
            <Text style={styles.sheetTitle}>Select country</Text>
            <FlatList data={COUNTRIES} keyExtractor={c => c.code} renderItem={({ item }) => (
              <TouchableOpacity testID={`${testID}-country-${item.code}`} style={[styles.option, item.code === country && styles.optionActive]} onPress={() => { setOpen(false); if (item.code !== country) onChange(item.code, ''); }}>
                <Text style={styles.flag}>{item.flag}</Text>
                <Text style={styles.optionLabel}>{item.label}</Text>
                <Text style={styles.optionDial}>{item.dial}</Text>
              </TouchableOpacity>
            )} />
          </View>
        </TouchableOpacity>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', backgroundColor: Colors.surface, borderRadius: 12, borderWidth: 1, borderColor: Colors.border, minHeight: 52 },
  country: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: Spacing.md, height: 52, borderRightWidth: 1, borderRightColor: Colors.border, minWidth: 96, gap: 4 },
  flag: { fontSize: 18 },
  dial: { color: Colors.gold, fontSize: FontSize.md, fontWeight: '700' },
  caret: { color: Colors.textMuted, fontSize: 12 },
  input: { flex: 1, color: Colors.text, fontSize: FontSize.lg, paddingHorizontal: Spacing.md, height: 52, letterSpacing: 1 },
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'flex-end' },
  sheet: { backgroundColor: Colors.modal, borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: Spacing.lg, paddingBottom: Spacing.xl, maxHeight: '60%' },
  sheetTitle: { color: Colors.text, fontSize: FontSize.md, fontWeight: '700', marginBottom: Spacing.md },
  option: { flexDirection: 'row', alignItems: 'center', paddingVertical: 14, paddingHorizontal: Spacing.md, borderRadius: 12, gap: 12, minHeight: 48 },
  optionActive: { backgroundColor: Colors.surface },
  optionLabel: { color: Colors.text, fontSize: FontSize.md, flex: 1 },
  optionDial: { color: Colors.textSecondary, fontSize: FontSize.md },
});
