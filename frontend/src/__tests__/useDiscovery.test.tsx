import React from 'react';
import { Text } from 'react-native';
import { act, render, waitFor } from '@testing-library/react-native';

/** R03 client side: a refresh opens a NEW discovery session, a late response of the previous session is discarded,
 *  pages are appended without duplicates, viewability is batched into impressions, offline refresh shows the cached
 *  page labelled as cached (never as a server refresh). */
const mockPost = jest.fn<Promise<any>, [string, any?]>();
const mockGet = jest.fn<Promise<any>, [string]>();
const mockCachedGet = jest.fn<Promise<any>, [string]>();

jest.mock('../api', () => {
  const actual = jest.requireActual('../api');
  return { ...actual, api: { get: (...a: [string]) => mockGet(...a), post: (...a: [string, any?]) => mockPost(...a) } };
});
jest.mock('../dataCache', () => ({ cachedGet: (...a: [string]) => mockCachedGet(...a) }));

// eslint-disable-next-line import/first
import { useDiscovery, VIEWABILITY } from '../hooks/useDiscovery';
// eslint-disable-next-line import/first
import { TransientError } from '../api';

let hook!: ReturnType<typeof useDiscovery>;
function Probe({ metal }: { metal?: string }) {
  hook = useDiscovery({ metal_type: metal });
  return <Text>{hook.state.mode}:{hook.state.sessionId}:{hook.state.items.map(i => i.id).join(',')}</Text>;
}
const session = (sid: string, ids: string[], extra: any = {}) => ({ session_id: sid, products: ids.map(id => ({ id })), pages: 2, unseen: ids.length, seen: 0, exhausted: false, ...extra });
const deferred = <T,>() => { let resolve!: (v: T) => void; const promise = new Promise<T>(r => { resolve = r; }); return { promise, resolve }; };

beforeEach(() => { mockPost.mockReset(); mockGet.mockReset(); mockCachedGet.mockReset(); jest.useRealTimers(); });

describe('useDiscovery', () => {
  it('uses a real viewability rule (mostly visible for a dwell time), not download/prefetch', () => {
    expect(VIEWABILITY.itemVisiblePercentThreshold).toBeGreaterThanOrEqual(50);
    expect(VIEWABILITY.minimumViewTime).toBeGreaterThanOrEqual(1000);
  });

  it('a late response from the previous session never replaces the newer refresh', async () => {
    const first = deferred<any>(), second = deferred<any>();
    mockPost.mockImplementationOnce(() => first.promise).mockImplementationOnce(() => second.promise);
    const tree = render(<Probe />);
    let p1!: Promise<void>, p2!: Promise<void>;
    await act(async () => { p1 = hook.refresh(); });
    await act(async () => { p2 = hook.refresh(); });
    await act(async () => { second.resolve(session('s2', ['b1', 'b2'])); await p2; });
    expect(tree.getByText('discovery:s2:b1,b2')).toBeTruthy();
    await act(async () => { first.resolve(session('s1', ['a1', 'a2'])); await p1; });
    expect(tree.getByText('discovery:s2:b1,b2')).toBeTruthy();   // stale session 1 ignored
    expect(mockPost).toHaveBeenCalledTimes(2);
    expect(mockPost.mock.calls[0][0]).toBe('/discovery/sessions');
  });

  it('loads further pages of the SAME session and merges without duplicates', async () => {
    mockPost.mockResolvedValueOnce(session('s1', ['a1', 'a2']));
    mockGet.mockResolvedValueOnce({ session_id: 's1', products: [{ id: 'a2' }, { id: 'a3' }], pages: 2 });
    const tree = render(<Probe />);
    await act(async () => { await hook.refresh(); });
    await act(async () => { await hook.loadMore(); });
    expect(mockGet).toHaveBeenCalledWith('/discovery/sessions/s1?page=2&limit=20');
    expect(tree.getByText('discovery:s1:a1,a2,a3')).toBeTruthy();
    await act(async () => { await hook.loadMore(); });                       // last page reached: no further request
    expect(mockGet).toHaveBeenCalledTimes(1);
  });

  it('reports each product as seen once, batched, and forgets nothing when the flush fails', async () => {
    jest.useFakeTimers();
    mockPost.mockResolvedValueOnce(session('s1', ['a1', 'a2', 'a3']));
    render(<Probe />);
    await act(async () => { await hook.refresh(); });
    mockPost.mockRejectedValueOnce(new Error('offline'));
    act(() => { hook.onViewable(['a1', 'a2']); hook.onViewable(['a2']); });
    expect(mockPost).toHaveBeenCalledTimes(1);                              // batched, not sent per item
    await act(async () => { jest.advanceTimersByTime(3000); });
    await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(2));
    expect(mockPost).toHaveBeenLastCalledWith('/discovery/impressions', { product_ids: ['a1', 'a2'], session_id: 's1' });
    mockPost.mockResolvedValueOnce({ recorded: 3 });
    act(() => { hook.onViewable(['a3']); });
    await act(async () => { jest.advanceTimersByTime(3000); });
    await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(3));
    expect(mockPost.mock.calls[2][1].product_ids.sort()).toEqual(['a1', 'a2', 'a3']);   // failed ids retried with the next flush
  });

  it('offline refresh shows the cached catalogue page labelled "cached", never as a discovery refresh', async () => {
    mockPost.mockRejectedValueOnce(new TransientError('Network unavailable'));
    mockCachedGet.mockResolvedValueOnce({ products: [{ id: 'c1' }], pages: 1 });
    const tree = render(<Probe metal="silver" />);
    await act(async () => { await hook.refresh(); });
    expect(mockCachedGet).toHaveBeenCalledWith('/products?page=1&limit=20&metal_type=silver');
    expect(tree.getByText('cached::c1')).toBeTruthy();
  });
});
