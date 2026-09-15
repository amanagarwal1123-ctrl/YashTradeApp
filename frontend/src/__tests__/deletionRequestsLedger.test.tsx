import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';

const mockGet = jest.fn<Promise<any>, [string]>();
const mockPost = jest.fn<Promise<any>, [string, any?]>();
const mockAlert = jest.fn();

jest.mock('@expo/vector-icons', () => {
  const ReactActual = jest.requireActual('react');
  const { Text: RNText } = jest.requireActual('react-native');
  return { Ionicons: (props: { name: string }) => ReactActual.createElement(RNText, { testID: `icon-${props.name}` }, props.name) };
});
jest.mock('../api', () => ({ api: { get: (...a: [string]) => mockGet(...a), post: (...a: [string, any?]) => mockPost(...a) } }));
jest.mock('../utils/alert', () => ({ showAlert: (...a: any[]) => mockAlert(...a), confirmAlert: jest.fn() }));

// eslint-disable-next-line import/first
import DeletionRequests from '../components/staff/DeletionRequests';

const entry = (provider: string, state: string, extra: any = {}) => ({
  provider, state, data_present: state === 'not_applicable' ? false : true, holds: `${provider} data`, procedure: `Email ${provider} support and record the ticket`,
  requested_at: null, request_reference: null, channel: null, outcome: null, outcome_at: null, retention_exception: null, history: [], ...extra,
});
const ROW = {
  reference: 'DEL-abc', source: 'app', requested_at: '2026-09-14T10:00:00Z', status: 'cleanup_completed',
  cleanup: { app: 'completed', website: 'acknowledged', website_acknowledged_at: '2026-09-14T11:00:00Z', completed_at: '2026-09-14T11:00:00Z' },
  provider_erasure: 'outstanding',
  providers: {
    sms_provider: entry('MSG91', 'not_requested'),
    ai_provider: entry('Anthropic via Emergent', 'requested', { requested_at: '2026-09-14T12:00:00Z', request_reference: 'EMG-1' }),
    object_storage: entry('Emergent Managed Object Storage', 'not_applicable'),
  },
};

beforeEach(() => { mockGet.mockReset(); mockPost.mockReset(); mockAlert.mockReset(); });
// The ledger also asks GET /admin/maintenance (MaintenanceCard); count only ledger loads.
const ledgerLoads = () => mockGet.mock.calls.filter(([path]) => path === '/admin/deletion-requests').length;

describe('DeletionRequests ledger', () => {
  it('shows cleanup and provider erasure as separate outcomes: website ack completed while providers stay outstanding', async () => {
    mockGet.mockResolvedValue({ requests: [ROW], total: 1, provider_procedures: {}, states: {} });
    await render(<DeletionRequests />);
    await waitFor(() => expect(screen.getByTestId('deletion-row-DEL-abc')).toBeTruthy());
    expect(screen.getByText('APP + WEBSITE CLEANUP COMPLETED')).toBeTruthy();
    expect(screen.getByText('PROVIDER ERASURE OUTSTANDING')).toBeTruthy();
    await fireEvent.press(screen.getByTestId('deletion-toggle-DEL-abc'));
    expect(screen.getByTestId('provider-state-DEL-abc-sms_provider').props.children).toBe('NOT REQUESTED');
    expect(screen.getByTestId('provider-state-DEL-abc-ai_provider').props.children).toBe('REQUESTED');
    expect(screen.getByTestId('provider-state-DEL-abc-object_storage').props.children).toBe('NOT APPLICABLE');
    expect(screen.getByText(/Requested .*ref EMG-1/)).toBeTruthy();
    // A not-applicable provider offers no request actions; an outstanding one does.
    expect(screen.queryByTestId('act-requested-DEL-abc-object_storage')).toBeNull();
    expect(screen.getByTestId('act-requested-DEL-abc-sms_provider')).toBeTruthy();
    expect(screen.getByTestId('act-confirmed-DEL-abc-ai_provider')).toBeTruthy();
  });

  it('records a manual provider request with reference and channel, then a refusal with the retention exception', async () => {
    mockGet.mockResolvedValue({ requests: [ROW], total: 1, provider_procedures: {}, states: {} });
    mockPost.mockResolvedValue({ ...ROW });
    await render(<DeletionRequests />);
    await waitFor(() => expect(screen.getByTestId('deletion-toggle-DEL-abc')).toBeTruthy());
    await fireEvent.press(screen.getByTestId('deletion-toggle-DEL-abc'));
    await fireEvent.press(screen.getByTestId('act-requested-DEL-abc-sms_provider'));
    await fireEvent.changeText(screen.getByTestId('in-ref-DEL-abc-sms_provider'), ' MSG91-77 ');
    await fireEvent.changeText(screen.getByTestId('in-channel-DEL-abc-sms_provider'), 'support ticket');
    await fireEvent.press(screen.getByTestId('submit-DEL-abc-sms_provider'));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/admin/deletion-requests/DEL-abc/providers/sms_provider',
      { action: 'requested', request_reference: 'MSG91-77', channel: 'support ticket' }));
    await waitFor(() => expect(ledgerLoads()).toBe(2)); // ledger reloaded after the change
    await fireEvent.press(screen.getByTestId('act-refused-DEL-abc-ai_provider'));
    await fireEvent.changeText(screen.getByTestId('in-outcome-DEL-abc-ai_provider'), 'Emergent declined');
    await fireEvent.changeText(screen.getByTestId('in-reason-DEL-abc-ai_provider'), 'Logs retained for abuse monitoring');
    await fireEvent.changeText(screen.getByTestId('in-basis-DEL-abc-ai_provider'), 'terms s.4');
    await fireEvent.changeText(screen.getByTestId('in-review-DEL-abc-ai_provider'), '2027-03-14');
    await fireEvent.press(screen.getByTestId('submit-DEL-abc-ai_provider'));
    await waitFor(() => expect(mockPost).toHaveBeenLastCalledWith('/admin/deletion-requests/DEL-abc/providers/ai_provider',
      { action: 'refused', outcome: 'Emergent declined', retention_exception: { reason: 'Logs retained for abuse monitoring', basis: 'terms s.4', review_at: '2027-03-14' } }));
  });

  it('surfaces a server rejection instead of pretending the entry was recorded', async () => {
    mockGet.mockResolvedValue({ requests: [ROW], total: 1, provider_procedures: {}, states: {} });
    mockPost.mockRejectedValue(Object.assign(new Error('Record the request (date + reference) before recording the provider\'s confirmation'), { status: 409, code: 'PROVIDER_STATE' }));
    await render(<DeletionRequests />);
    await waitFor(() => expect(screen.getByTestId('deletion-toggle-DEL-abc')).toBeTruthy());
    await fireEvent.press(screen.getByTestId('deletion-toggle-DEL-abc'));
    await fireEvent.press(screen.getByTestId('act-confirmed-DEL-abc-ai_provider'));
    await fireEvent.changeText(screen.getByTestId('in-outcome-DEL-abc-ai_provider'), 'confirmed by email');
    await fireEvent.press(screen.getByTestId('submit-DEL-abc-ai_provider'));
    await waitFor(() => expect(mockAlert).toHaveBeenCalledWith('Not recorded', expect.stringContaining('Record the request')));
    expect(ledgerLoads()).toBe(1);
  });

  it('tells non-administrators the ledger is administrator only', async () => {
    mockGet.mockRejectedValue(Object.assign(new Error('You do not have permission for this action'), { status: 403, code: 'PERMISSION_DENIED' }));
    await render(<DeletionRequests />);
    await waitFor(() => expect(screen.getByTestId('deletion-ledger-error').props.children).toBe('Administrator only.'));
  });
});
