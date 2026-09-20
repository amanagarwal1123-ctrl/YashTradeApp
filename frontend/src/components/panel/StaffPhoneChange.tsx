import React, { useRef, useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, Modal, StyleSheet, ScrollView, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { Colors, Spacing, FontSize } from '../../theme';
import { api } from '../../api';
import { useAuth } from '../../context/AuthContext';
import { confirmAlert } from '../../utils/alert';
import PhoneField from '../PhoneField';
import { canonicalPhone, DEFAULT_COUNTRY, displayPhone } from '../../phone';
import type { CountryCode } from 'libphonenumber-js';

type Staff = { id: string; name: string; phone: string; role: string };
type Preview = {
  status: 'available' | 'customer' | 'staff' | 'unchanged';
  outcome: string; new_phone: string; new_phone_display: string; preview_token?: string;
  customer?: { id: string; name: string; masked_phone: string; role: string; account_status: string };
  owner?: { name: string; role: string; masked_phone: string };
};

const newKey = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}-${Math.random().toString(36).slice(2, 10)}`;

/** Administrator changes an ordinary staff member's LOGIN NUMBER (same account, role, code, assignments and history),
 *  or - when the number belongs to a customer - explicitly promotes that customer instead. Nothing is ever merged.
 *  The confirmation shown is bound (server-signed) to this staff member, their current number and the checked number:
 *  the submission always sends the CHECKED number, late or stale preview responses are ignored, and the field is
 *  locked while a confirmation is on screen. */
export default function StaffPhoneChange({ staff, onClose, onChanged }: { staff: Staff; onClose: () => void; onChanged: () => void }) {
  const router = useRouter();
  const { logout } = useAuth();
  const [country, setCountry] = useState<CountryCode>(DEFAULT_COUNTRY);
  const [national, setNational] = useState('');
  const [reason, setReason] = useState('');
  const [preview, setPreview] = useState<Preview | null>(null);
  const [promoteRole, setPromoteRole] = useState<'telecaller' | 'billing_executive'>('telecaller');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState<string>('');
  const canonical = canonicalPhone(national, country);
  const previewSeq = useRef(0);
  // One key per confirmation: a double tap or a retry after a network / OPERATION_INCOMPLETE error replays the same
  // operation; after any other refusal a fresh key is issued so a corrected submission is never answered with a replay.
  const keyRef = useRef(newKey());

  const fail = (e: any) => {
    if (e?.code === 'RECENT_AUTH_REQUIRED') {
      confirmAlert('Sign in again to confirm', e.message, async () => { await logout(); router.replace('/login'); }, 'Sign in');
      return;
    }
    if (e?.code !== 'OPERATION_INCOMPLETE' && e?.status) keyRef.current = newKey();
    setError(e?.message || 'Request failed');
  };

  const check = async () => {
    setError(''); setPreview(null);
    if (!canonical) { setError('Enter a valid number for the selected country'); return; }
    const seq = ++previewSeq.current;
    setBusy(true);
    try {
      const res: Preview = await api.post(`/integrations/staff/${staff.id}/phone/preview`, { new_phone: canonical });
      // ignore a response for a number that is no longer the one on screen
      if (seq !== previewSeq.current || res.new_phone !== canonicalPhone(national, country)) return;
      keyRef.current = newKey();
      setPreview(res);
    } catch (e: any) { if (seq === previewSeq.current) fail(e); } finally { if (seq === previewSeq.current) setBusy(false); }
  };

  const editNumber = (c: CountryCode, v: string) => { previewSeq.current += 1; setCountry(c); setNational(v); setPreview(null); setError(''); };

  const change = async () => {
    if (!preview?.preview_token) return;
    if (reason.trim().length < 10) { setError('Give an audit reason of at least 10 characters'); return; }
    setBusy(true); setError('');
    const body = { new_phone: preview.new_phone, reason: reason.trim(), confirm_user_id: staff.id, expected_phone: staff.phone,
      idempotency_key: keyRef.current, preview_token: preview.preview_token };
    try {
      let res: any;
      try { res = await api.post(`/integrations/staff/${staff.id}/phone`, body); }
      catch (e: any) {
        if (e?.code !== 'OPERATION_INCOMPLETE') throw e;
        res = await api.post(`/integrations/staff/${staff.id}/phone`, body); // same key: finishes the interrupted bookkeeping
      }
      setDone(`${staff.name} now signs in with ${res.new_phone_display}. All their sessions were signed out; the new number must be verified by OTP at the next sign-in.`);
      onChanged();
    } catch (e: any) { fail(e); } finally { setBusy(false); }
  };

  const promote = async () => {
    if (!preview?.customer) return;
    if (reason.trim().length < 10) { setError('Give an audit reason of at least 10 characters'); return; }
    setBusy(true); setError('');
    try {
      await api.post(`/integrations/staff/${preview.customer.id}/convert`, { role: promoteRole, reason: reason.trim(), confirm_user_id: preview.customer.id });
      setDone(`${preview.customer.name || 'The customer'} is now ${promoteRole.replace('_', ' ')} with their own account and history. ${staff.name} was not changed and keeps ${displayPhone(staff.phone)}.`);
      onChanged();
    } catch (e: any) { fail(e); } finally { setBusy(false); }
  };

  return (
    <Modal visible transparent animationType="slide" onRequestClose={onClose}>
      <View style={st.backdrop}>
        <View style={st.sheet}>
          <ScrollView keyboardShouldPersistTaps="handled">
            <Text style={st.title} testID="staff-phone-title">Change login number</Text>
            <Text style={st.sub}>{staff.name} · current {displayPhone(staff.phone)} · {staff.role.replace('_', ' ')}</Text>
            {done ? (
              <>
                <Text style={st.done} testID="staff-phone-done">{done}</Text>
                <TouchableOpacity style={st.primary} onPress={onClose} testID="staff-phone-close"><Text style={st.primaryText}>DONE</Text></TouchableOpacity>
              </>
            ) : (
              <>
                <Text style={st.label}>New login number</Text>
                <PhoneField testID="staff-new-phone" country={country} national={national} editable={!preview} onChange={editNumber} />
                <Text style={st.label}>Reason (recorded in the audit log)</Text>
                <TextInput testID="staff-phone-reason" style={st.input} value={reason} onChangeText={setReason} placeholder="e.g. Handset lost, new company SIM issued" placeholderTextColor={Colors.textMuted} maxLength={500} multiline />
                {!preview && (
                  <TouchableOpacity testID="staff-phone-check" style={[st.primary, (!canonical || busy) && st.disabled]} disabled={!canonical || busy} onPress={check}>
                    {busy ? <ActivityIndicator color="#000" /> : <Text style={st.primaryText}>CHECK NUMBER</Text>}
                  </TouchableOpacity>
                )}
                {preview && (
                  <View style={[st.card, preview.status === 'staff' && st.cardError]} testID={`staff-phone-preview-${preview.status}`}>
                    {preview.status === 'customer' && preview.customer && (
                      <>
                        <Text style={st.cardTitle}>This number belongs to an existing customer. Promote this customer to staff?</Text>
                        <Text style={st.cardLine}>Name: {preview.customer.name || '(no name)'}</Text>
                        <Text style={st.cardLine}>Number: {preview.customer.masked_phone} · Current role: {preview.customer.role} · {preview.customer.account_status}</Text>
                        <Text style={st.cardBody}>{preview.outcome}</Text>
                        <Text style={st.label}>Staff role for this customer</Text>
                        <View style={st.roleRow}>
                          {(['telecaller', 'billing_executive'] as const).map(r => (
                            <TouchableOpacity key={r} testID={`staff-promote-role-${r}`} style={[st.roleBtn, promoteRole === r && st.roleBtnActive]} onPress={() => setPromoteRole(r)}>
                              <Text style={[st.roleText, promoteRole === r && st.roleTextActive]}>{r === 'telecaller' ? 'Executive / Telecaller' : 'Billing Executive'}</Text>
                            </TouchableOpacity>
                          ))}
                        </View>
                        <TouchableOpacity testID="staff-promote-confirm" style={[st.primary, busy && st.disabled]} disabled={busy} onPress={promote}>
                          {busy ? <ActivityIndicator color="#000" /> : <Text style={st.primaryText}>YES, PROMOTE THIS CUSTOMER</Text>}
                        </TouchableOpacity>
                      </>
                    )}
                    {preview.status === 'available' && (
                      <>
                        <Text style={st.cardTitle}>Change {staff.name}&apos;s login number to {preview.new_phone_display}?</Text>
                        <Text style={st.cardBody}>{preview.outcome}</Text>
                        <TouchableOpacity testID="staff-phone-confirm" style={[st.primary, busy && st.disabled]} disabled={busy} onPress={change}>
                          {busy ? <ActivityIndicator color="#000" /> : <Text style={st.primaryText}>YES, CHANGE LOGIN NUMBER</Text>}
                        </TouchableOpacity>
                      </>
                    )}
                    {(preview.status === 'staff' || preview.status === 'unchanged') && <Text style={st.cardBody}>{preview.outcome}</Text>}
                    <TouchableOpacity testID="staff-phone-recheck" style={st.secondary} onPress={() => { previewSeq.current += 1; setPreview(null); }}><Text style={st.secondaryText}>Use a different number</Text></TouchableOpacity>
                  </View>
                )}
                {error ? <Text style={st.error} testID="staff-phone-error">{error}</Text> : null}
                <TouchableOpacity testID="staff-phone-cancel" style={st.secondary} onPress={onClose}><Text style={st.secondaryText}>Cancel</Text></TouchableOpacity>
              </>
            )}
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

const st = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.65)', justifyContent: 'flex-end' },
  sheet: { backgroundColor: Colors.modal, borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: Spacing.lg, maxHeight: '92%' },
  title: { color: Colors.text, fontSize: FontSize.lg, fontWeight: '700' },
  sub: { color: Colors.textSecondary, fontSize: FontSize.sm, marginTop: 4, marginBottom: Spacing.md },
  label: { color: Colors.textSecondary, fontSize: FontSize.xs, fontWeight: '600', marginTop: Spacing.md, marginBottom: 6, letterSpacing: 0.5 },
  input: { backgroundColor: Colors.surface, borderRadius: 12, borderWidth: 1, borderColor: Colors.border, color: Colors.text, padding: Spacing.md, minHeight: 52, fontSize: FontSize.md },
  primary: { backgroundColor: Colors.gold, borderRadius: 12, paddingVertical: 14, alignItems: 'center', marginTop: Spacing.md, minHeight: 48 },
  primaryText: { color: '#000', fontWeight: '800', fontSize: FontSize.sm, letterSpacing: 1 },
  secondary: { paddingVertical: 14, alignItems: 'center', minHeight: 48 },
  secondaryText: { color: Colors.textSecondary, fontSize: FontSize.sm },
  disabled: { opacity: 0.5 },
  card: { backgroundColor: Colors.surface, borderRadius: 14, padding: Spacing.md, marginTop: Spacing.md, borderWidth: 1, borderColor: Colors.borderGold },
  cardError: { borderColor: Colors.error },
  cardTitle: { color: Colors.text, fontSize: FontSize.md, fontWeight: '700', marginBottom: 6 },
  cardLine: { color: Colors.text, fontSize: FontSize.sm, marginTop: 2 },
  cardBody: { color: Colors.textSecondary, fontSize: FontSize.sm, marginTop: 8, lineHeight: 20 },
  roleRow: { flexDirection: 'row', gap: 8 },
  roleBtn: { flex: 1, paddingVertical: 12, borderRadius: 10, borderWidth: 1, borderColor: Colors.border, alignItems: 'center', minHeight: 44 },
  roleBtnActive: { borderColor: Colors.gold, backgroundColor: Colors.gold + '15' },
  roleText: { color: Colors.textSecondary, fontSize: FontSize.xs, fontWeight: '600' },
  roleTextActive: { color: Colors.gold },
  error: { color: Colors.error, marginTop: Spacing.sm, fontSize: FontSize.sm },
  done: { color: Colors.success, fontSize: FontSize.md, lineHeight: 22, marginTop: Spacing.md },
});
