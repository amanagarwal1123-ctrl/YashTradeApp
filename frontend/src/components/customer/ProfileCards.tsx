import React, { useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../../theme';
import { api } from '../../api';
import { useAuth } from '../../context/AuthContext';
import { useLang } from '../../context/LanguageContext';
import { showAlert } from '../../utils/alert';

const T: Record<string, any> = {
  en: { title: 'Complete your profile', body: 'Add your name, shop name and place so our team can serve you and send requests.', cta: 'COMPLETE PROFILE',
        cTitle: 'Which details should we keep?', cBody: 'Your website registration changed some details you had entered in the app. Choose the value to keep for each.',
        app: 'App', web: 'Website', save: 'SAVE CHOICES', saved: 'Profile updated', fail: 'Could not save your choices. Please try again.',
        name: 'Name', shop_name: 'Shop name', location: 'Place' },
  hi: { title: 'अपनी प्रोफ़ाइल पूरी करें', body: 'अपना नाम, दुकान का नाम और स्थान जोड़ें ताकि हमारी टीम आपकी सेवा कर सके।', cta: 'प्रोफ़ाइल पूरी करें',
        cTitle: 'कौन-सी जानकारी रखें?', cBody: 'वेबसाइट रजिस्ट्रेशन से ऐप में भरी गई कुछ जानकारी बदल गई है। हर फ़ील्ड के लिए चुनें कि क्या रखना है।',
        app: 'ऐप', web: 'वेबसाइट', save: 'चयन सहेजें', saved: 'प्रोफ़ाइल अपडेट हुई', fail: 'चयन सहेजा नहीं जा सका। फिर से कोशिश करें।',
        name: 'नाम', shop_name: 'दुकान का नाम', location: 'स्थान' },
  pa: { title: 'ਆਪਣੀ ਪ੍ਰੋਫ਼ਾਈਲ ਪੂਰੀ ਕਰੋ', body: 'ਆਪਣਾ ਨਾਮ, ਦੁਕਾਨ ਦਾ ਨਾਮ ਅਤੇ ਸਥਾਨ ਜੋੜੋ ਤਾਂ ਜੋ ਸਾਡੀ ਟੀਮ ਤੁਹਾਡੀ ਸੇਵਾ ਕਰ ਸਕੇ।', cta: 'ਪ੍ਰੋਫ਼ਾਈਲ ਪੂਰੀ ਕਰੋ',
        cTitle: 'ਕਿਹੜੀ ਜਾਣਕਾਰੀ ਰੱਖੀਏ?', cBody: 'ਵੈੱਬਸਾਈਟ ਰਜਿਸਟ੍ਰੇਸ਼ਨ ਨੇ ਐਪ ਵਿੱਚ ਭਰੀ ਕੁਝ ਜਾਣਕਾਰੀ ਬਦਲ ਦਿੱਤੀ ਹੈ। ਹਰ ਫ਼ੀਲਡ ਲਈ ਚੁਣੋ ਕਿ ਕੀ ਰੱਖਣਾ ਹੈ।',
        app: 'ਐਪ', web: 'ਵੈੱਬਸਾਈਟ', save: 'ਚੋਣ ਸੰਭਾਲੋ', saved: 'ਪ੍ਰੋਫ਼ਾਈਲ ਅੱਪਡੇਟ ਹੋਈ', fail: 'ਚੋਣ ਸੰਭਾਲੀ ਨਹੀਂ ਜਾ ਸਕੀ। ਮੁੜ ਕੋਸ਼ਿਸ਼ ਕਰੋ।',
        name: 'ਨਾਮ', shop_name: 'ਦੁਕਾਨ ਦਾ ਨਾਮ', location: 'ਸਥਾਨ' },
};

export type ProfileConflicts = Record<string, { previous: string; kept: string }>;

/** Name, shop name and place present (mirrors the backend `profile_complete` rule). */
export const isProfileComplete = (user: any) => !!(user?.name && user?.shop_name && (user?.location || user?.city));

/** Home card for customers whose profile is still missing name / shop name / place. Optional: the app stays usable. */
export function CompleteProfileCard() {
  const { user } = useAuth();
  const { language } = useLang();
  const router = useRouter();
  const t = T[language] || T.en;
  if (!user || user.role !== 'customer' || isProfileComplete(user)) return null;
  return (
    <TouchableOpacity testID="complete-profile-card" style={st.card} activeOpacity={0.85} onPress={() => router.push({ pathname: '/edit-profile', params: { complete: '1' } })}>
      <View style={st.iconWrap}><Ionicons name="person-circle-outline" size={28} color={Colors.gold} /></View>
      <View style={{ flex: 1 }}>
        <Text style={st.title}>{t.title}</Text>
        <Text style={st.body}>{t.body}</Text>
        <Text style={st.cta} testID="complete-profile-cta">{t.cta}  ›</Text>
      </View>
    </TouchableOpacity>
  );
}

/** Website registration overwrote values typed in the app: let the customer pick, field by field. */
export function ProfileConflictCard() {
  const { user, refreshUser } = useAuth();
  const { language } = useLang();
  const t = T[language] || T.en;
  const conflicts: ProfileConflicts = user?.profile_conflicts || {};
  const fields = Object.keys(conflicts);
  const [choice, setChoice] = useState<Record<string, 'previous' | 'kept'>>({});
  const [busy, setBusy] = useState(false);
  if (!user || fields.length === 0) return null;
  const ready = fields.every(f => choice[f]);
  const save = async () => {
    setBusy(true);
    try { await api.post('/auth/profile/conflicts/resolve', { choices: choice }); await refreshUser(); showAlert(t.saved); }
    catch (e: any) { showAlert(t.fail, e?.message); }
    finally { setBusy(false); }
  };
  return (
    <View testID="profile-conflict-card" style={[st.card, { flexDirection: 'column' }]}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
        <Ionicons name="git-compare-outline" size={20} color={Colors.warning} />
        <Text style={st.title}>{t.cTitle}</Text>
      </View>
      <Text style={st.body}>{t.cBody}</Text>
      {fields.map(f => (
        <View key={f} style={st.fieldBlock}>
          <Text style={st.fieldLabel}>{(t[f] || f).toUpperCase()}</Text>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            {(['previous', 'kept'] as const).map(side => {
              const selected = choice[f] === side;
              return (
                <TouchableOpacity key={side} testID={`conflict-${f}-${side}`} style={[st.option, selected && st.optionActive]}
                  onPress={() => setChoice(prev => ({ ...prev, [f]: side }))} accessibilityRole="radio" accessibilityState={{ selected }}>
                  <Text style={st.optionSource}>{side === 'previous' ? t.app : t.web}</Text>
                  <Text style={[st.optionValue, selected && { color: Colors.gold }]} numberOfLines={2}>{conflicts[f][side]}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>
      ))}
      <TouchableOpacity testID="conflict-save" style={[st.saveBtn, (!ready || busy) && { opacity: 0.4 }]} disabled={!ready || busy} onPress={save}>
        {busy ? <ActivityIndicator color="#000" /> : <Text style={st.saveText}>{t.save}</Text>}
      </TouchableOpacity>
    </View>
  );
}

const st = StyleSheet.create({
  card: { flexDirection: 'row', gap: 12, marginHorizontal: Spacing.lg, marginTop: Spacing.md, padding: Spacing.md, borderRadius: 14, backgroundColor: Colors.card, borderWidth: 1, borderColor: Colors.borderGold },
  iconWrap: { width: 44, height: 44, borderRadius: 22, backgroundColor: Colors.gold + '15', alignItems: 'center', justifyContent: 'center' },
  title: { fontSize: FontSize.md, fontWeight: '700', color: Colors.text },
  body: { fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: 4, lineHeight: 19 },
  cta: { fontSize: FontSize.xs, fontWeight: '700', color: Colors.gold, letterSpacing: 1, marginTop: 8 },
  fieldBlock: { marginTop: Spacing.md },
  fieldLabel: { fontSize: FontSize.xs, color: Colors.textMuted, letterSpacing: 1.2, fontWeight: '600', marginBottom: 6 },
  option: { flex: 1, borderRadius: 10, borderWidth: 1, borderColor: Colors.border, backgroundColor: Colors.surface, padding: 10, minHeight: 56 },
  optionActive: { borderColor: Colors.gold, backgroundColor: Colors.gold + '12' },
  optionSource: { fontSize: 10, color: Colors.textMuted, letterSpacing: 1, fontWeight: '700' },
  optionValue: { fontSize: FontSize.sm, color: Colors.text, marginTop: 2, fontWeight: '600' },
  saveBtn: { marginTop: Spacing.md, backgroundColor: Colors.gold, borderRadius: 10, paddingVertical: 12, alignItems: 'center', minHeight: 44 },
  saveText: { fontSize: FontSize.sm, fontWeight: '700', color: '#000', letterSpacing: 1 },
});
