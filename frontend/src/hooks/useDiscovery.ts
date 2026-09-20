/**
 * Unseen-first Home discovery (R03). A refresh opens a server-side discovery SESSION: the eligible catalogue is split
 * into products this account has not actually SEEN (reported viewability impressions) and products already seen; the
 * unseen part is shuffled with a fresh seed, the seen part is least-recently-seen first, and pages are stable slices of
 * that order (no duplicates, no re-shuffled pages). A new refresh is a new session; late responses of the previous
 * session are discarded. Offline, the last cached catalogue page is shown and labelled as cached — never as a refresh.
 *
 * "Seen" = the card was at least 60 % visible for 1.2 s (FlatList viewability), batched to POST /discovery/impressions.
 * Impressions are per account (server side) and never influence another account's order.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { api, TransientError, SessionChangedError } from '../api';
import { cachedGet } from '../dataCache';

export const VIEWABILITY = { itemVisiblePercentThreshold: 60, minimumViewTime: 1200 };
const PAGE = 20;
const FLUSH_MS = 3000;
const FLUSH_AT = 10;

export type DiscoveryState = {
  items: any[]; page: number; pages: number; loading: boolean; loaded: boolean;
  sessionId: string; unseen: number; seen: number; exhausted: boolean; mode: 'discovery' | 'cached' | 'none';
};
export const EMPTY: DiscoveryState = { items: [], page: 0, pages: 1, loading: false, loaded: false, sessionId: '', unseen: 0, seen: 0, exhausted: false, mode: 'none' };

const merge = (previous: any[], next: any[]) => Array.from(new Map([...previous, ...next].map(p => [p.id, p])).values());

export function useDiscovery(filters: { metal_type?: string; category?: string }) {
  const [state, setState] = useState<DiscoveryState>(EMPTY);
  const generation = useRef(0);          // bumped on every refresh: stale responses are ignored
  const reported = useRef<Set<string>>(new Set());
  const pending = useRef<Set<string>>(new Set());
  const flushTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const filterKey = `${filters.metal_type || ''}|${filters.category || ''}`;

  const flush = useCallback(async () => {
    if (flushTimer.current) { clearTimeout(flushTimer.current); flushTimer.current = null; }
    const ids = Array.from(pending.current).slice(0, 50);
    if (!ids.length) return;
    ids.forEach(id => pending.current.delete(id));
    try { await api.post('/discovery/impressions', { product_ids: ids, session_id: state.sessionId }); }
    catch { ids.forEach(id => pending.current.add(id)); } // offline / server error: kept pending, sent with the next flush
  }, [state.sessionId]);

  /** Called from FlatList.onViewableItemsChanged with the viewable product ids. */
  const onViewable = useCallback((ids: string[]) => {
    let added = false;
    for (const id of ids) {
      if (reported.current.has(id)) continue;
      reported.current.add(id); pending.current.add(id); added = true;
    }
    if (!added) return;
    if (pending.current.size >= FLUSH_AT) { flush(); return; }
    if (!flushTimer.current) flushTimer.current = setTimeout(flush, FLUSH_MS);
  }, [flush]);

  /** Explicit refresh (pull / first load): new session, unseen first. Throws only when even the cache is unavailable. */
  const refresh = useCallback(async () => {
    const gen = ++generation.current;
    await flush();                           // what was seen so far counts for this refresh
    reported.current = new Set();
    setState(prev => ({ ...prev, loading: true }));
    try {
      const res = await api.post('/discovery/sessions', { metal_type: filters.metal_type || '', category: filters.category || '', limit: PAGE });
      if (gen !== generation.current) return;
      setState({ items: res.products || [], page: 1, pages: res.pages || 1, loading: false, loaded: true, sessionId: res.session_id,
        unseen: res.unseen, seen: res.seen, exhausted: !!res.exhausted, mode: 'discovery' });
    } catch (e: any) {
      if (gen !== generation.current || e instanceof SessionChangedError) return;
      if (e instanceof TransientError || e?.transient) {
        // Offline / server unavailable: the cached catalogue page is shown and labelled, not presented as a refresh.
        const qs = new URLSearchParams({ page: '1', limit: String(PAGE) });
        if (filters.metal_type) qs.set('metal_type', filters.metal_type);
        if (filters.category) qs.set('category', filters.category);
        try {
          const cached = await cachedGet(`/products?${qs}`);
          if (gen !== generation.current) return;
          setState({ items: cached.products || [], page: 1, pages: cached.pages || 1, loading: false, loaded: true, sessionId: '', unseen: 0, seen: 0, exhausted: false, mode: 'cached' });
          return;
        } catch { /* fall through */ }
      }
      setState(prev => ({ ...prev, loading: false }));
      throw e;
    }
  }, [filterKey, flush]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadMore = useCallback(async () => {
    const s = state;
    if (s.loading || !s.loaded || s.page >= s.pages) return;
    const gen = generation.current;
    setState(prev => ({ ...prev, loading: true }));
    try {
      let res: any;
      if (s.mode === 'discovery' && s.sessionId) res = await api.get(`/discovery/sessions/${s.sessionId}?page=${s.page + 1}&limit=${PAGE}`);
      else {
        const qs = new URLSearchParams({ page: String(s.page + 1), limit: String(PAGE) });
        if (filters.metal_type) qs.set('metal_type', filters.metal_type);
        res = await cachedGet(`/products?${qs}`);
      }
      if (gen !== generation.current) return;
      setState(prev => ({ ...prev, items: merge(prev.items, res.products || []), page: s.page + 1, pages: res.pages || prev.pages, loading: false }));
    } catch (e: any) {
      if (gen !== generation.current) return;
      setState(prev => ({ ...prev, loading: false }));
      if (e?.code === 'DISCOVERY_SESSION_EXPIRED') refresh().catch(() => {});
    }
  }, [state, filterKey, refresh]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => () => { flush(); }, [flush]); // unmount: report what was seen

  return { state, refresh, loadMore, onViewable, flush };
}
