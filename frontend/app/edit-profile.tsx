import React, { useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, TextInput, ActivityIndicator, KeyboardAvoidingView, Platform } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api } from '../src/api';
import { useAuth } from '../src/context/AuthContext';
import { showAlert } from '../src/utils/alert';

export default function EditProfileScreen() {
  const { user, refreshUser } = useAuth();
  const router = useRouter();

  const [name, setName] = useState(user?.name || '');
  const [shopName, setShopName] = useState(user?.shop_name || '');
  const [location, setLocation] = useState(user?.location || user?.city || '');
  const [saving, setSaving] = useState(false);

  // Phone change flow
  const [showPhoneChange, setShowPhoneChange] = useState(false);
  const [newPhone, setNewPhone] = useState('');
  const [phoneOtp, setPhoneOtp] = useState('');
  const [otpSent, setOtpSent] = useState(false);
  const [phoneBusy, setPhoneBusy] = useState(false);
  const [phoneError, setPhoneError] = useState('');

  const saveProfile = async () => {
    if (!name.trim()) { showAlert('Error', 'Name is required'); return; }
    setSaving(true);
    try {
      await api.put('/auth/profile', { name: name.trim(), shop_name: shopName.trim(), location: location.trim() });
      await refreshUser();
      showAlert('Saved', 'Your profile has been updated');
      router.back();
    } catch (e: any) {
      showAlert('Error', e?.message || 'Could not save profile. Please try again.');
    } finally { setSaving(false); }
  };

  const requestPhoneOtp = async () => {
    setPhoneError('');
    if (newPhone.length !== 10) { setPhoneError('Enter a valid 10-digit mobile number'); return; }
    setPhoneBusy(true);
    try {
      await api.post('/auth/phone-change/request', { new_phone: newPhone });
      setOtpSent(true);
    } catch (e: any) {
      setPhoneError(e?.message || 'Could not send OTP');
    } finally { setPhoneBusy(false); }
  };

  const verifyPhoneChange = async () => {
    setPhoneError('');
    if (phoneOtp.length !== 4) { setPhoneError('Enter the 4-digit OTP'); return; }
    setPhoneBusy(true);
    try {
      await api.post('/auth/phone-change/verify', { new_phone: newPhone, otp: phoneOtp });
      await refreshUser();
      setShowPhoneChange(false); setOtpSent(false); setNewPhone(''); setPhoneOtp('');
      showAlert('Phone Updated', 'Your registered number has been changed');
    } catch (e: any) {
      setPhoneError(e?.message || 'Could not verify OTP');
    } finally { setPhoneBusy(false); }
  };

  return (
    <SafeAreaView style={st.container} edges={['top']}>
      <View style={st.header}>
        <TouchableOpacity testID="edit-profile-back" onPress={() => router.back()} style={st.backBtn}>
          <Ionicons name="arrow-back" size={24} color={Colors.text} />
        </TouchableOpacity>
        <Text style={st.headerTitle}>Edit Profile</Text>
        <View style={{ width: 44 }} />
      </View>

      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={st.content} keyboardShouldPersistTaps="handled">
          <Text style={st.label}>CUSTOMER NAME</Text>
          <TextInput testID="edit-name" style={st.input} value={name} onChangeText={setName} placeholder="Your full name" placeholderTextColor={Colors.textMuted} />

          <Text style={st.label}>SHOP NAME</Text>
          <TextInput testID="edit-shop" style={st.input} value={shopName} onChangeText={setShopName} placeholder="Your shop / firm name" placeholderTextColor={Colors.textMuted} />

          <Text style={st.label}>LOCATION</Text>
          <TextInput testID="edit-location" style={st.input} value={location} onChangeText={setLocation} placeholder="City / area" placeholderTextColor={Colors.textMuted} />

          <TouchableOpacity testID="edit-save" style={[st.saveBtn, saving && { opacity: 0.5 }]} onPress={saveProfile} disabled={saving}>
            {saving ? <ActivityIndicator color="#000" /> : <Text style={st.saveBtnText}>SAVE CHANGES</Text>}
          </TouchableOpacity>

          {/* Phone number — protected change flow */}
          <Text style={st.label}>PHONE NUMBER</Text>
          <View style={st.phoneRow}>
            <Text style={st.phoneValue}>+91 {user?.phone}</Text>
            <View style={st.verifiedBadge}>
              <Ionicons name="shield-checkmark" size={12} color={Colors.success} />
              <Text style={st.verifiedText}>Verified</Text>
            </View>
          </View>
          {!showPhoneChange ? (
            <TouchableOpacity testID="change-phone-btn" style={st.changePhoneBtn} onPress={() => setShowPhoneChange(true)}>
              <Ionicons name="swap-horizontal" size={16} color={Colors.gold} />
              <Text style={st.changePhoneText}>Change Number (OTP verification required)</Text>
            </TouchableOpacity>
          ) : (
            <View style={st.phoneChangeCard}>
              <Text style={st.phoneChangeTitle}>Change Registered Number</Text>
              <Text style={st.phoneChangeHint}>An OTP will be sent to the new number to verify it belongs to you.</Text>
              <View style={st.inputRow}>
                <Text style={st.prefix}>+91</Text>
                <TextInput
                  testID="new-phone-input"
                  style={st.inputFlex}
                  placeholder="New 10-digit number"
                  placeholderTextColor={Colors.textMuted}
                  keyboardType="phone-pad"
                  maxLength={10}
                  value={newPhone}
                  editable={!otpSent}
                  onChangeText={v => { setNewPhone(v.replace(/[^0-9]/g, '')); setPhoneError(''); }}
                />
              </View>
              {otpSent && (
                <TextInput
                  testID="phone-otp-input"
                  style={[st.input, { textAlign: 'center', letterSpacing: 8, fontWeight: '700' }]}
                  placeholder="OTP"
                  placeholderTextColor={Colors.textMuted}
                  keyboardType="number-pad"
                  maxLength={4}
                  value={phoneOtp}
                  onChangeText={v => { setPhoneOtp(v.replace(/[^0-9]/g, '')); setPhoneError(''); }}
                />
              )}
              {phoneError ? <Text style={st.errorText}>{phoneError}</Text> : null}
              <View style={{ flexDirection: 'row', gap: 8, marginTop: Spacing.sm }}>
                <TouchableOpacity style={st.cancelBtn} onPress={() => { setShowPhoneChange(false); setOtpSent(false); setNewPhone(''); setPhoneOtp(''); setPhoneError(''); }}>
                  <Text style={st.cancelBtnText}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  testID="phone-change-action"
                  style={[st.saveBtn, { flex: 1, marginTop: 0 }, phoneBusy && { opacity: 0.5 }]}
                  onPress={otpSent ? verifyPhoneChange : requestPhoneOtp}
                  disabled={phoneBusy}
                >
                  {phoneBusy ? <ActivityIndicator color="#000" /> : <Text style={st.saveBtnText}>{otpSent ? 'VERIFY & UPDATE' : 'SEND OTP'}</Text>}
                </TouchableOpacity>
              </View>
            </View>
          )}
          <View style={{ height: 40 }} />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md },
  backBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: Colors.surface, alignItems: 'center', justifyContent: 'center' },
  headerTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text },
  content: { paddingHorizontal: Spacing.lg },
  label: { fontSize: FontSize.xs, color: Colors.textSecondary, letterSpacing: 1.5, fontWeight: '600', marginTop: Spacing.lg, marginBottom: 6 },
  input: { backgroundColor: Colors.surface, borderRadius: 10, borderWidth: 1, borderColor: Colors.border, color: Colors.text, paddingHorizontal: 14, paddingVertical: 12, fontSize: FontSize.md },
  saveBtn: { backgroundColor: Colors.gold, borderRadius: 10, paddingVertical: 14, alignItems: 'center', marginTop: Spacing.lg },
  saveBtnText: { fontSize: FontSize.sm, fontWeight: '700', color: '#000', letterSpacing: 1 },
  phoneRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: Colors.surface, borderRadius: 10, borderWidth: 1, borderColor: Colors.border, paddingHorizontal: 14, paddingVertical: 12 },
  phoneValue: { fontSize: FontSize.md, color: Colors.text, fontWeight: '600' },
  verifiedBadge: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: Colors.success + '15', paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 },
  verifiedText: { fontSize: 10, color: Colors.success, fontWeight: '700' },
  changePhoneBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: Spacing.sm, minHeight: 44 },
  changePhoneText: { fontSize: FontSize.sm, color: Colors.gold, fontWeight: '600' },
  phoneChangeCard: { backgroundColor: Colors.card, borderRadius: 12, borderWidth: 1, borderColor: Colors.borderGold, padding: Spacing.md, marginTop: Spacing.sm },
  phoneChangeTitle: { fontSize: FontSize.md, fontWeight: '700', color: Colors.text },
  phoneChangeHint: { fontSize: FontSize.xs, color: Colors.textMuted, marginTop: 4, marginBottom: Spacing.sm },
  inputRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: Colors.surface, borderRadius: 10, borderWidth: 1, borderColor: Colors.border, paddingHorizontal: 12, marginBottom: Spacing.sm },
  prefix: { fontSize: FontSize.md, color: Colors.textSecondary, marginRight: 8 },
  inputFlex: { flex: 1, color: Colors.text, paddingVertical: 12, fontSize: FontSize.md },
  errorText: { fontSize: FontSize.xs, color: Colors.error, marginTop: 6 },
  cancelBtn: { paddingHorizontal: 16, justifyContent: 'center', borderRadius: 10, borderWidth: 1, borderColor: Colors.border, minHeight: 44 },
  cancelBtnText: { fontSize: FontSize.sm, color: Colors.textMuted },
});
