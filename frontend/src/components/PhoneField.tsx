import React, { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, Modal, StyleSheet, FlatList } from 'react-native';
import { Colors, Spacing, FontSize } from '../theme';
import { COUNTRIES, canonicalPhone, countryMeta, displayPhone, parseInput } from '../phone';
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
  /** Live line under the field: the formatted number once valid, otherwise what is expected for the country. */
  showHint?: boolean;
};

/**
 * Country selector (India default) + national-number input. Accepts typed or pasted numbers in any common format
 * (spaces, brackets, dashes, trunk zero, full international form) and never cuts digits; `parseInput` normalises and a
 * pasted "+…" number switches the selector to its own country. The caller sends `canonicalPhone(national, country)`.
 */
export default function PhoneField({ country, national, onChange, placeholder, testID = 'phone-input', autoFocus, editable = true, inputStyle, showHint = true }: Props) {
  const [open, setOpen] = useState(false);
  const meta = countryMeta(country);
  const canonical = canonicalPhone(national, country);
  const hint = !national ? '' : canonical ? displayPhone(canonical) : `Enter a valid ${meta.label} mobile number (e.g. ${meta.example})`;
  return (
    <View>
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
          autoComplete="tel"
          textContentType="telephoneNumber"
          value={national}
          autoFocus={autoFocus}
          editable={editable}
          onChangeText={raw => { const next = parseInput(raw, country); onChange(next.country, next.national); }}
        />
      </View>
      {showHint && hint ? <Text testID={`${testID}-hint`} style={[styles.hint, !canonical && styles.hintError]}>{hint}</Text> : null}
      <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
        <TouchableOpacity style={styles.backdrop} activeOpacity={1} onPress={() => setOpen(false)}>
          <View style={styles.sheet}>
            <Text style={styles.sheetTitle}>Select country</Text>
            <FlatList data={COUNTRIES} keyExtractor={c => c.code} renderItem={({ item }) => (
              <TouchableOpacity testID={`${testID}-country-${item.code}`} style={[styles.option, item.code === country && styles.optionActive]}
                onPress={() => { setOpen(false); if (item.code !== country) onChange(item.code, parseInput(national, item.code).national); }}>
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
  hint: { color: Colors.textSecondary, fontSize: FontSize.xs, marginTop: 6, marginLeft: 4 },
  hintError: { color: Colors.warning },
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'flex-end' },
  sheet: { backgroundColor: Colors.modal, borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: Spacing.lg, paddingBottom: Spacing.xl, maxHeight: '60%' },
  sheetTitle: { color: Colors.text, fontSize: FontSize.md, fontWeight: '700', marginBottom: Spacing.md },
  option: { flexDirection: 'row', alignItems: 'center', paddingVertical: 14, paddingHorizontal: Spacing.md, borderRadius: 12, gap: 12, minHeight: 48 },
  optionActive: { backgroundColor: Colors.surface },
  optionLabel: { color: Colors.text, fontSize: FontSize.md, flex: 1 },
  optionDial: { color: Colors.textSecondary, fontSize: FontSize.md },
});
