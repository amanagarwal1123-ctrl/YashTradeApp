import { API_BASE, resolveFileUrl } from '../../api';

export const HEAD_COLORS: Record<string, string> = { new: '#3B82F6', contacted: '#A855F7', interested: '#D4AF37', follow_up: '#F59E0B', unreachable: '#9CA3AF' };
export const TYPE_LABELS: Record<string, string> = {
  video_call: 'Video call', ask_price: 'Price enquiry', callback: 'Call back', similar_products: 'Similar products',
  hold_item: 'Hold item', quick_reorder: 'Quick re-order', cart_selection: 'Cart selection',
};
export const typeLabel = (t?: string) => TYPE_LABELS[t || ''] || (t || 'Query').replace(/_/g, ' ');

export const VIEW_PRESETS = [
  { key: 'all_pending', label: 'All Pending' },
  { key: 'my_pending', label: 'My Pending' },
  { key: 'my_completed', label: 'My Completed' },
] as const;
export const ADMIN_VIEWS = [...VIEW_PRESETS, { key: 'completed', label: 'All Completed' }] as const;

/** Item picture for staff: current thumbnail when the product is still listed, nothing when it was removed. */
export const itemImage = (item: any): string => {
  if (!item?.available) return '';
  if (item.thumbnail_path) return `${API_BASE}/files/${item.thumbnail_path}`;
  if (item.storage_path) return `${API_BASE}/files/${item.storage_path}?w=400`;
  return resolveFileUrl(item.images?.[0] || '');
};

/** Quick follow-up moments (IST calendar, expressed as ISO with the device offset; the server normalises to UTC). */
export function followUpOptions(now = new Date()): { label: string; iso: string }[] {
  const at = (d: Date, h: number, m = 0) => { const x = new Date(d); x.setHours(h, m, 0, 0); return x; };
  const tomorrow = new Date(now); tomorrow.setDate(now.getDate() + 1);
  const inThree = new Date(now); inThree.setDate(now.getDate() + 3);
  const inOneHour = new Date(now.getTime() + 60 * 60 * 1000);
  return [
    { label: 'In 1 hour', iso: inOneHour.toISOString() },
    { label: 'Tomorrow 10:00', iso: at(tomorrow, 10).toISOString() },
    { label: 'Tomorrow 17:00', iso: at(tomorrow, 17).toISOString() },
    { label: 'In 3 days', iso: at(inThree, 11).toISOString() },
  ];
}

export const freshness = (r: any) => r?.reset_count ? `Released at 03:00 · cycle ${r.reset_cycle || ''}`.trim() : 'Fresh';
export const istDate = (d = new Date()) => new Date(d.getTime() + 330 * 60000).toISOString().slice(0, 10);
