jest.mock('expo-constants', () => ({ __esModule: true, default: { expoConfig: { extra: { backendUrl: 'https://unit.test' } } } }));
jest.mock('expo-secure-store', () => ({ getItemAsync: jest.fn(async () => null), setItemAsync: jest.fn(async () => {}), deleteItemAsync: jest.fn(async () => {}) }));

import { productFull, productImage, productThumb, sizedUrl, variantFor } from '../api';

const stored = { id: 'p', storage_path: 'yash-trade/originals/p.jpg', thumbnail_path: 'yash-trade/thumbs/p.jpg', images: [] };
const legacy = { id: 'l', images: ['https://images.example.com/x.jpg'] };
const F = 'https://unit.test/api/files/';

describe('product image sizing (thumbnail-first, never the original in lists)', () => {
  it('chooses the display variant from dp width and density, capped at 2x', () => {
    expect(variantFor(170, 2)).toBe(400);   // two-column feed card
    expect(variantFor(170, 3)).toBe(400);   // 3x phones get 2x bytes
    expect(variantFor(358, 2)).toBe(800);   // full-width Home card
    expect(variantFor(358, 1)).toBe(400);   // low-density tablet / web
    expect(variantFor(80, 3)).toBe(400);
  });

  it('small cards use the stored thumbnail, large cards a sized variant of the master, details the full original', () => {
    expect(productImage(stored, 170)).toBe(`${F}yash-trade/thumbs/p.jpg`);
    expect(productImage(stored, 358)).toBe(`${F}yash-trade/originals/p.jpg?w=800`);
    expect(productThumb(stored)).toBe(`${F}yash-trade/thumbs/p.jpg`);
    expect(productFull(stored)).toBe(`${F}yash-trade/originals/p.jpg`);
    // master without a stored thumbnail: variants come from the master, never the full file in a list
    const noThumb = { ...stored, thumbnail_path: '' };
    expect(productImage(noThumb, 170)).toBe(`${F}yash-trade/originals/p.jpg?w=400`);
    expect(productThumb(noThumb)).toBe(`${F}yash-trade/originals/p.jpg?w=400`);
  });

  it('legacy external URLs pass through unchanged and gallery URLs get a bounded width', () => {
    expect(productImage(legacy, 358)).toBe('https://images.example.com/x.jpg');
    expect(productFull(legacy)).toBe('https://images.example.com/x.jpg');
    expect(sizedUrl(`${F}yash-trade/products/manual/a.jpg`, 56)).toBe(`${F}yash-trade/products/manual/a.jpg?w=400`);
    expect(sizedUrl('https://images.example.com/x.jpg', 56)).toBe('https://images.example.com/x.jpg');
  });
});
