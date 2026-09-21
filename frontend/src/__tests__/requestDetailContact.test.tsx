import React from 'react';
import { Linking } from 'react-native';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';

/**
 * F08 (independent review): Call / WhatsApp on a query are WORK actions for a telecaller. They must claim the query
 * first (atomic, first tap wins), re-check ownership right before dialling, and stay OFF while another telecaller
 * holds the query. Administrators / billing keep an explicit exception. Only the transport (api / Linking) is mocked.
 */
const mockGet = jest.fn<Promise<any>, [string]>();
const mockPost = jest.fn<Promise<any>, [string, any?]>();
const mockPatch = jest.fn<Promise<any>, [string, any?]>();
let mockUser: any = { id: 't1', role: 'telecaller', name: 'Tele One' };

jest.mock('@expo/vector-icons', () => {
  const ReactActual = jest.requireActual('react');
  const { Text: RNText } = jest.requireActual('react-native');
  return { Ionicons: (props: { name: string }) => ReactActual.createElement(RNText, { testID: `icon-${props.name}` }, props.name) };
});
jest.mock('expo-image', () => ({ Image: () => null }));
jest.mock('expo-router', () => ({ useRouter: () => ({ push: jest.fn(), replace: jest.fn(), back: jest.fn() }) }));
jest.mock('../api', () => ({ api: { get: (...a: [string]) => mockGet(...a), post: (...a: [string, any?]) => mockPost(...a), patch: (...a: [string, any?]) => mockPatch(...a) } }));
jest.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: mockUser, loading: false }) }));
jest.mock('../utils/alert', () => ({ showAlert: jest.fn(), confirmAlert: jest.fn() }));

// eslint-disable-next-line import/first
import RequestDetail from '../components/staff/RequestDetail';

const CONTACT = { tel: '+919000000004', whatsapp: '919000000004' };
const base = (over: any = {}) => ({
  id: 'q1', request_type: 'callback', status: 'pending', head: 'new', head_label: 'New', assignee_id: '', assignee_name: '', resolver_id: null,
  version: 3, customer_id: 'c1', customer_name: 'Customer One', customer_phone_display: '+91 90000 00004', user_phone: '9000000004',
  contact: CONTACT, items: [], completions: [], customer: {}, other_requests: 0, created_at: '2026-09-20T05:00:00Z', pending_seconds: 60,
  permissions: { can_work: false, can_claim: true, can_assign: false, can_reopen: false }, ...over,
});
const serve = (detail: any) => mockGet.mockImplementation(async (path: string) => {
  if (path === '/requests/q1') return detail();
  if (path === '/requests/q1/history') return { history: [] };
  if (path === '/requests/catalog') return { heads: ['new', 'contacted'], head_labels: {}, outcomes: ['converted', 'other'] };
  throw new Error(`unexpected GET ${path}`);
});

let openURL: jest.SpyInstance;
beforeEach(() => {
  mockGet.mockReset(); mockPost.mockReset(); mockPatch.mockReset();
  mockUser = { id: 't1', role: 'telecaller', name: 'Tele One' };
  openURL = jest.spyOn(Linking, 'openURL').mockResolvedValue(true as any);
});
afterEach(() => openURL.mockRestore());

const renderDetail = () => render(<RequestDetail requestId="q1" onClose={() => {}} onChanged={() => {}} staff={[]} />);

describe('F08 – contact actions follow the claim workflow', () => {
  it('an unclaimed query is CLAIMED atomically before the phone app opens; the hint says so', async () => {
    let claimed = false;
    serve(() => base(claimed ? { status: 'in_progress', assignee_id: 't1', permissions: { can_work: true, can_claim: false } } : {}));
    mockPost.mockImplementation(async () => { claimed = true; return { id: 'q1', status: 'in_progress', assignee_id: 't1' }; });
    renderDetail();
    await screen.findByTestId('request-call');
    expect(String(screen.getByTestId('request-contact-gate').props.children)).toMatch(/takes this query for you first/);
    fireEvent.press(screen.getByTestId('request-call'));
    await waitFor(() => expect(openURL).toHaveBeenCalledWith('tel:+919000000004'));
    expect(mockPost).toHaveBeenCalledWith('/requests/q1/claim');
    expect(mockPost.mock.invocationCallOrder[0]).toBeLessThan(openURL.mock.invocationCallOrder[0]);
    expect(screen.getByTestId('request-detail-info').props.children).toBe('Query is now yours');
    expect(screen.getByTestId('request-detail-owner').props.children.props.children).toBe('Taken by you');
  });

  it('when another telecaller wins the claim race nothing is dialled and the winner is named', async () => {
    let taken = false;
    serve(() => base(taken ? { status: 'in_progress', assignee_id: 't2', assignee_name: 'Tele Two', permissions: { can_work: false, can_claim: false } } : {}));
    mockPost.mockImplementation(async () => { taken = true; const e: any = new Error('Tele Two already took this query'); e.code = 'ALREADY_ASSIGNED'; e.body = { assignee_name: 'Tele Two' }; throw e; });
    renderDetail();
    await screen.findByTestId('request-whatsapp');
    fireEvent.press(screen.getByTestId('request-whatsapp'));
    await screen.findByText('Tele Two took this query first');
    expect(openURL).not.toHaveBeenCalled();
    // the refreshed detail shows the holder and the contact actions are now OFF for this telecaller
    await waitFor(() => expect(screen.getByTestId('request-whatsapp').props.accessibilityState?.disabled ?? screen.getByTestId('request-whatsapp').props.disabled).toBe(true));
    expect(screen.getByTestId('request-contact-gate').props.children).toMatch(/available to the telecaller holding this query/);
  });

  it('a query held by ANOTHER telecaller has Call and WhatsApp disabled (no external app is opened)', async () => {
    serve(() => base({ status: 'in_progress', assignee_id: 't2', assignee_name: 'Tele Two', permissions: { can_work: false, can_claim: false } }));
    renderDetail();
    await screen.findByTestId('request-held-by-other');
    const call = screen.getByTestId('request-call');
    expect(call.props.accessibilityState?.disabled ?? call.props.disabled).toBe(true);
    fireEvent.press(call);
    expect(openURL).not.toHaveBeenCalled();
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('the claimant re-validates ownership on the server right before dialling and is stopped after a 03:00 release', async () => {
    let released = false;
    serve(() => base(released ? { status: 'pending', assignee_id: '', reset_count: 1, permissions: { can_work: false, can_claim: true } }
                                : { status: 'in_progress', assignee_id: 't1', permissions: { can_work: true, can_claim: false } }));
    renderDetail();
    await screen.findByTestId('request-work-card');
    released = true; // the daily release happened between the screen load and the tap
    fireEvent.press(screen.getByTestId('request-call'));
    await screen.findByText('Take the query before contacting the customer');
    expect(openURL).not.toHaveBeenCalled();
    expect(mockPost).not.toHaveBeenCalled(); // no silent re-claim: the telecaller takes it again explicitly
    expect(mockGet.mock.calls.filter(([p]) => p === '/requests/q1').length).toBeGreaterThanOrEqual(2);
  });

  it('the claimant whose ownership is confirmed dials without a second claim', async () => {
    serve(() => base({ status: 'in_progress', assignee_id: 't1', permissions: { can_work: true, can_claim: false } }));
    renderDetail();
    await screen.findByTestId('request-work-card');
    fireEvent.press(screen.getByTestId('request-whatsapp'));
    await waitFor(() => expect(openURL).toHaveBeenCalledWith('https://wa.me/919000000004'));
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('a completed query keeps contact actions only for the telecaller who completed it', async () => {
    serve(() => base({ status: 'resolved', assignee_id: '', resolver_id: 't2', resolver_name: 'Tele Two', permissions: { can_work: false, can_claim: false } }));
    renderDetail();
    await screen.findByTestId('request-call');
    expect(screen.getByTestId('request-call').props.accessibilityState?.disabled ?? screen.getByTestId('request-call').props.disabled).toBe(true);
    expect(screen.getByTestId('request-contact-gate').props.children).toMatch(/Completed by another staff member/);
  });

  it('administrators are an explicit exception: they can contact without taking the query, and the hint says so', async () => {
    mockUser = { id: 'a1', role: 'admin', name: 'Admin' };
    serve(() => base({ status: 'in_progress', assignee_id: 't2', assignee_name: 'Tele Two', permissions: { can_work: true, can_claim: false, can_assign: true, can_reopen: true } }));
    renderDetail();
    await screen.findByTestId('request-admin-card');
    fireEvent.press(screen.getByTestId('request-call'));
    await waitFor(() => expect(openURL).toHaveBeenCalledWith('tel:+919000000004'));
    expect(mockPost).not.toHaveBeenCalled();
    expect(screen.getByTestId('request-contact-gate').props.children.join('')).toMatch(/does not take the query from Tele Two/);
  });
});
