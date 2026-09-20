import React, { useState } from 'react';
import { Modal, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { api } from '../../api';
import { useAuth } from '../../context/AuthContext';
import { displayPhone } from '../../phone';
import { confirmAlert } from '../../utils/alert';
import { KeyboardAwareScreen } from '../KeyboardScreen';
import { Button, Busy, Input, ui } from '../staff/Controls';

type Account = { id: string; name?: string; phone?: string; role?: string; status?: string; account_status?: string };
type Props = { kind: 'staff' | 'customer'; account: Account; onChanged: () => void; onDeleted?: () => void };

/**
 * Administrator account controls (R15). Three DISTINCT, server-enforced operations:
 *  - Disable: reversible; sign-in and privileged access stop immediately (sessions revoked, devices detached, open
 *    queries released for staff). Does not free the phone number.
 *  - Re-enable: explicit reversal of a disable.
 *  - Delete: the real erasure workflow (tombstone, anonymised queries, provider-erasure ledger, website outbox event).
 *    Needs a reason, the target's canonical ID + last four digits and an OTP sign-in within the last 30 minutes.
 * Owner / last-admin protection, self-deletion and version conflicts come back as actionable messages, never silently.
 */
export default function AccountActions({ kind, account, onChanged, onDeleted }: Props) {
  const { user, logout } = useAuth();
  const router = useRouter();
  const signInAgain = async () => { await logout(); router.replace('/login'); };
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [info, setInfo] = useState('');
  const [deleting, setDeleting] = useState(false), [reason, setReason] = useState(''), [last4, setLast4] = useState('');
  const [stepUp, setStepUp] = useState(false);
  const active = (account.account_status || account.status || 'active') === 'active';
  const deleted = (account.account_status || account.status) === 'deleted';
  const self = user?.id === account.id;
  const label = account.name || displayPhone(account.phone || '') || account.id;
  const statusPath = kind === 'staff' ? `/integrations/staff/${account.id}` : `/customers/${account.id}`;
  const statusBody = (next: 'active' | 'inactive') => kind === 'staff' ? { status: next } : { account_status: next };

  const explain = (e: any) => {
    if (e.code === 'RECENT_AUTH_REQUIRED') { setStepUp(true); return e.message; }
    if (e.code === 'OWNER_ADMIN_PROTECTED') return 'The default owner administrator cannot be disabled, demoted or deleted.';
    if (e.code === 'LAST_ADMIN') return 'This is the last usable administrator; add or re-enable another administrator first.';
    if (e.code === 'SELF_DELETION_DENIED') return 'You cannot delete your own account from here.';
    if (e.code === 'CONFIRMATION_REQUIRED') return 'The last four digits do not match this account. Check the number and try again.';
    if (e.transient) return `Server unavailable (${e.status}); nothing was changed. Try again.`;
    return e.message || 'The change was not applied';
  };

  const setStatus = async (next: 'active' | 'inactive') => {
    setBusy(true); setError(''); setInfo('');
    try {
      const res = await api.patch(statusPath, statusBody(next));
      setInfo(next === 'inactive'
        ? `Disabled. Sign-in is blocked immediately${res.queries_released ? `; ${res.queries_released} open quer${res.queries_released === 1 ? 'y' : 'ies'} released to the shared queue` : ''}. The number stays reserved for this account.`
        : 'Re-enabled. The account can sign in again with OTP.');
      onChanged();
    } catch (e: any) { setError(explain(e)); }
    finally { setBusy(false); }
  };

  const remove = async () => {
    setBusy(true); setError(''); setInfo('');
    try {
      const res = await api.post(`${statusPath}/delete`, { reason: reason.trim(), confirm_user_id: account.id, confirm_phone_last4: last4.trim() });
      setDeleting(false);
      setInfo(res.already_deleted ? 'This account was already deleted; nothing further to do.'
        : `Deleted (${res.reference || 'ledger entry created'}). Personal data removed; ${res.queries_released ? `${res.queries_released} open queries released; ` : ''}provider erasure is tracked separately in Deletions.`);
      onChanged(); onDeleted?.();
    } catch (e: any) { setError(explain(e)); }
    finally { setBusy(false); }
  };

  if (deleted) return <Text testID={`account-deleted-${account.id}`} style={ui.muted}>Account deleted · erasure tracked in the Deletions ledger</Text>;

  return <View style={{ gap: 8 }} testID={`account-actions-${account.id}`}>
    <View style={ui.row}>
      {active
        ? <Button id={`account-disable-${account.id}`} title="Disable" icon="pause-circle-outline" disabled={busy || self} onPress={() => confirmAlert('Disable this account?', `${label} will be signed out everywhere and cannot sign in until re-enabled. ${kind === 'staff' ? 'Their open queries return to the shared queue. ' : ''}This is reversible; it does not delete anything.`, () => setStatus('inactive'), 'Disable')} />
        : <Button id={`account-enable-${account.id}`} title="Re-enable" icon="play-circle-outline" disabled={busy} onPress={() => setStatus('active')} />}
      <Button id={`account-delete-${account.id}`} title="Delete account…" icon="trash-outline" disabled={busy || self} onPress={() => { setError(''); setInfo(''); setDeleting(true); }} />
    </View>
    {self && <Text style={ui.muted}>You cannot disable or delete your own account from here.</Text>}
    {busy && <Busy />}
    {!!error && <Text testID={`account-error-${account.id}`} style={ui.error}>{error}</Text>}
    {stepUp && <Button id={`account-stepup-${account.id}`} title="Sign in again with OTP" icon="key-outline" onPress={signInAgain} />}
    {!!info && <Text testID={`account-info-${account.id}`} style={[ui.muted, ui.success]}>{info}</Text>}

    <Modal visible={deleting} animationType="slide" onRequestClose={() => setDeleting(false)}>
      <SafeAreaView style={ui.screen}>
        <KeyboardAwareScreen contentContainerStyle={ui.content} testID="account-delete-sheet">
          <View style={ui.row}><Button id="account-delete-cancel" title="Cancel" icon="arrow-back" onPress={() => setDeleting(false)} /></View>
          <Text style={ui.title}>Delete {kind === 'staff' ? 'staff' : 'customer'} account</Text>
          <View style={ui.card}>
            <Text style={ui.text}>{label}</Text>
            <Text style={ui.muted}>{displayPhone(account.phone || '')} · ID {account.id}</Text>
            <Text style={ui.muted}>This is NOT a disable. Personal data is removed or anonymised through the erasure workflow; sessions and devices are revoked{kind === 'staff' ? '; open queries are released to the shared queue; completion attribution stays in the immutable ledger' : ''}. Business records (queries, orders) are kept without personal data. Erasure at SMS/AI/storage providers is recorded separately in the Deletions ledger and is not complete until confirmed there. A later sign-up with the same number creates a NEW account.</Text>
          </View>
          <Input id="account-delete-reason" label="Reason (recorded in the audit history, at least 10 characters)" value={reason} onChange={setReason} multiline />
          <Input id="account-delete-last4" label={`Confirm: last four digits of ${displayPhone(account.phone || '')}`} value={last4} onChange={v => setLast4(v.replace(/[^0-9]/g, '').slice(0, 4))} numeric />
          <Text style={ui.muted}>Requires an OTP sign-in within the last 30 minutes. Owner and last-administrator accounts are protected by the server.</Text>
          {!!error && <Text testID="account-delete-error" style={ui.error}>{error}</Text>}
          {stepUp && <Button id="account-delete-stepup" title="Sign in again with OTP" icon="key-outline" onPress={signInAgain} />}
          <Button id="account-delete-confirm" title="Delete permanently" icon="trash" disabled={busy || reason.trim().length < 10 || last4.length !== 4}
            onPress={() => confirmAlert('Delete permanently?', `${label} will be erased through the deletion workflow. This cannot be undone.`, remove, 'Delete')} />
          {busy && <Busy />}
        </KeyboardAwareScreen>
      </SafeAreaView>
    </Modal>
  </View>;
}
