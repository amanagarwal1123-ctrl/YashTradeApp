import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../theme';

export interface AiRecipient {
  name: string; service: string; role: string; via: string; location: string;
  data_sent: string[]; data_not_sent: string[]; purpose: string; retention: string;
}
export interface AiConsentInfo {
  granted: boolean; version?: string | null; current_version: string; granted_at?: string | null; withdrawn_at?: string | null;
  outdated?: boolean; recipients: AiRecipient[]; withdrawal_effects: string[]; required_for: string[]; not_required_for: string[];
}

interface Props {
  info: AiConsentInfo;
  busy?: boolean;
  onAllow: () => void;
  onDecline: () => void;
  declineLabel?: string;
}

/** Explicit AI data-sharing consent: names the recipient, what is and is not sent, and how to withdraw. */
export default function AiConsentCard({ info, busy, onAllow, onDecline, declineLabel = 'Not now' }: Props) {
  return (
    <View style={st.card} testID="ai-consent-card">
      <View style={st.titleRow}>
        <Ionicons name="shield-checkmark-outline" size={22} color={Colors.gold} />
        <Text style={st.title}>Allow AI data sharing?</Text>
      </View>
      <Text style={st.lead}>
        The AI assistant (including the quick prompts) sends your text to a third-party AI provider. Nothing is sent until you allow it.
        {info.outdated ? ' Our AI terms changed, so we are asking again.' : ''}
      </Text>
      {info.recipients.map(r => (
        <View key={r.name} style={st.recipient}>
          <Text style={st.recipientName}>{r.name} <Text style={st.recipientMeta}>· {r.service} · {r.location}</Text></Text>
          <Text style={st.recipientVia}>{r.role}. Sent via {r.via}.</Text>
          <Text style={st.sub}>WHAT IS SENT</Text>
          {r.data_sent.map(d => <Row key={d} icon="arrow-up-circle" color={Colors.warning} text={d} />)}
          <Text style={st.sub}>NEVER SENT</Text>
          {r.data_not_sent.map(d => <Row key={d} icon="close-circle" color={Colors.textMuted} text={d} />)}
          <Text style={st.sub}>PURPOSE & RETENTION</Text>
          <Text style={st.body}>{r.purpose}. {r.retention}</Text>
        </View>
      ))}
      <Text style={st.sub}>IF YOU WITHDRAW LATER (Profile → AI data sharing)</Text>
      {info.withdrawal_effects.map(e => <Row key={e} icon="checkmark-circle" color={Colors.success} text={e} />)}
      <Text style={st.footnote}>Consent version {info.current_version}. Declining keeps every other part of the app available.</Text>
      <TouchableOpacity testID="ai-consent-allow" style={[st.allowBtn, busy && { opacity: 0.5 }]} onPress={onAllow} disabled={busy}>
        {busy ? <ActivityIndicator color="#000" /> : <Text style={st.allowText}>ALLOW AND CONTINUE</Text>}
      </TouchableOpacity>
      <TouchableOpacity testID="ai-consent-decline" style={st.declineBtn} onPress={onDecline} disabled={busy}>
        <Text style={st.declineText}>{declineLabel}</Text>
      </TouchableOpacity>
    </View>
  );
}

const Row = ({ icon, color, text }: { icon: any; color: string; text: string }) => (
  <View style={st.row}><Ionicons name={icon} size={14} color={color} /><Text style={st.rowText}>{text}</Text></View>
);

const st = StyleSheet.create({
  card: { backgroundColor: Colors.card, borderRadius: 16, borderWidth: 1, borderColor: Colors.gold + '55', padding: Spacing.md, gap: 6 },
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  title: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text },
  lead: { fontSize: FontSize.sm, color: Colors.textSecondary, lineHeight: 20 },
  recipient: { backgroundColor: Colors.surface, borderRadius: 12, padding: Spacing.sm, marginTop: 4, gap: 4 },
  recipientName: { fontSize: FontSize.md, fontWeight: '700', color: Colors.text },
  recipientMeta: { fontSize: FontSize.xs, fontWeight: '400', color: Colors.textMuted },
  recipientVia: { fontSize: FontSize.xs, color: Colors.textSecondary, lineHeight: 16 },
  sub: { fontSize: FontSize.xs, color: Colors.textSecondary, letterSpacing: 1.2, fontWeight: '600', marginTop: 6 },
  body: { fontSize: FontSize.xs, color: Colors.textSecondary, lineHeight: 17 },
  row: { flexDirection: 'row', alignItems: 'flex-start', gap: 6 },
  rowText: { flex: 1, fontSize: FontSize.xs, color: Colors.textSecondary, lineHeight: 17 },
  footnote: { fontSize: FontSize.xs, color: Colors.textMuted, marginTop: 6 },
  allowBtn: { backgroundColor: Colors.gold, borderRadius: 10, paddingVertical: 14, alignItems: 'center', marginTop: Spacing.sm, minHeight: 48 },
  allowText: { fontSize: FontSize.sm, fontWeight: '700', color: '#000', letterSpacing: 1 },
  declineBtn: { alignItems: 'center', minHeight: 44, justifyContent: 'center' },
  declineText: { fontSize: FontSize.sm, color: Colors.textMuted, fontWeight: '600' },
});
