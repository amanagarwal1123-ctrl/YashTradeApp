import React from 'react';
import { Text } from 'react-native';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';

const mockLoadAsync = jest.fn<Promise<void>, [unknown, unknown?]>();
const mockIsLoaded = jest.fn<boolean, [string]>(() => false);
const mockIconRenders = jest.fn<void, [string]>();
const mockFetchFallback = jest.fn<Promise<{ uri: string }>, []>();

jest.mock('expo-font', () => ({ loadAsync: (...args: unknown[]) => mockLoadAsync(...(args as [unknown, unknown?])), isLoaded: (family: string) => mockIsLoaded(family) }));
jest.mock('@expo/vector-icons', () => {
  const ReactActual = jest.requireActual('react');
  const { Text: RNText } = jest.requireActual('react-native');
  const Ionicons = (props: { name: string }) => { mockIconRenders(props.name); return ReactActual.createElement(RNText, { testID: 'ionicon' }, props.name); };
  Ionicons.font = { ionicons: 42 };
  return { Ionicons };
});
jest.mock('../../api', () => ({ BACKEND_URL: 'https://backend.test' }));
jest.mock('../fallbackFont', () => ({ createFallbackFetcher: () => () => mockFetchFallback() }));

// eslint-disable-next-line import/first
import { IconFontGate, ICON_FONT_MAP, ICON_FONT_TIMEOUT_MS, IONICONS_FAMILY } from '../IconFontGate';
// eslint-disable-next-line import/first
import { Ionicons } from '@expo/vector-icons';

const ANDROID_EMPTY = 'Font file for ionicons is empty. Make sure the local file path is correctly populated.';
const Child = () => (<><Text>home-screen</Text><Ionicons name="diamond" /></>);

beforeEach(() => { mockLoadAsync.mockReset(); mockIsLoaded.mockReset().mockReturnValue(false); mockIconRenders.mockReset(); mockFetchFallback.mockReset(); });

describe('IconFontGate', () => {
  it('uses the exact Ionicons font map and registered family name', () => {
    expect(ICON_FONT_MAP).toEqual({ ionicons: 42 });
    expect(IONICONS_FAMILY).toBe('ionicons');
  });

  it('holds icon-bearing routes until the font is registered, then renders them', async () => {
    let resolveLoad: () => void = () => undefined;
    mockLoadAsync.mockImplementationOnce(() => new Promise<void>((resolve) => { resolveLoad = resolve; }));
    const settled = jest.fn();
    await render(<IconFontGate onSettled={settled}><Child /></IconFontGate>);
    expect(screen.getByTestId('icon-font-loading')).toBeTruthy();
    expect(screen.queryByText('home-screen')).toBeNull();
    expect(mockIconRenders).not.toHaveBeenCalled();
    expect(settled).not.toHaveBeenCalled();
    await act(async () => { resolveLoad(); });
    await waitFor(() => expect(screen.getByText('home-screen')).toBeTruthy());
    expect(mockIconRenders).toHaveBeenCalledWith('diamond');
    expect(mockLoadAsync).toHaveBeenCalledWith({ ionicons: 42 });
    expect(settled).toHaveBeenCalledWith(expect.objectContaining({ ok: true, source: 'bundled' }));
  });

  it('shows a system-font error state (no icons mounted) when bundled and fallback both fail, with a working bounded retry', async () => {
    mockLoadAsync.mockRejectedValue(new Error(ANDROID_EMPTY));
    mockFetchFallback.mockRejectedValue(new Error('FALLBACK_HTTP_0: Network request failed'));
    const settled = jest.fn();
    await render(<IconFontGate onSettled={settled}><Child /></IconFontGate>);
    await waitFor(() => expect(screen.getByTestId('icon-font-error')).toBeTruthy(), { timeout: 8000 });
    expect(screen.queryByText('home-screen')).toBeNull();
    expect(mockIconRenders).not.toHaveBeenCalled();
    expect(screen.getByTestId('icon-font-error-detail').props.children).toContain('fallback source tried');
    expect(mockLoadAsync).toHaveBeenCalledTimes(2); // initial + one automatic retry, then it stops
    expect(mockFetchFallback).toHaveBeenCalledTimes(2);
    expect(settled).toHaveBeenCalledTimes(1);
    expect(settled).toHaveBeenLastCalledWith(expect.objectContaining({ ok: false, fallbackTried: true, attempts: 2 }));

    // Deliberate retry re-runs the real loader; a second tap while the retry is in flight is ignored.
    let resolveRetry: () => void = () => undefined;
    mockLoadAsync.mockImplementation(() => new Promise<void>((resolve) => { resolveRetry = resolve; }));
    await fireEvent.press(screen.getByTestId('icon-font-retry'));
    expect(mockLoadAsync).toHaveBeenCalledTimes(3);
    await fireEvent.press(screen.getByTestId('icon-font-retry'));
    expect(mockLoadAsync).toHaveBeenCalledTimes(3); // single-flight: no second load started
    await act(async () => { resolveRetry(); });
    await waitFor(() => expect(screen.getByText('home-screen')).toBeTruthy());
    expect(mockLoadAsync).toHaveBeenCalledTimes(3);
    expect(mockIconRenders).toHaveBeenCalledWith('diamond');
    expect(settled).toHaveBeenLastCalledWith(expect.objectContaining({ ok: true, source: 'bundled', attempts: 3 }));
  });

  it('recovers through the validated fallback when the bundled file is empty', async () => {
    mockLoadAsync.mockImplementation((arg: unknown) => (typeof arg === 'object' && arg && 'ionicons' in (arg as object)
      ? Promise.reject(new Error(ANDROID_EMPTY)) : Promise.resolve()));
    mockFetchFallback.mockResolvedValue({ uri: 'file:///data/user/0/host.exp.exponent/cache/icon-fonts/Ionicons-fa2ab7d2557819b2.ttf' });
    const settled = jest.fn();
    await render(<IconFontGate onSettled={settled}><Child /></IconFontGate>);
    await waitFor(() => expect(screen.getByText('home-screen')).toBeTruthy());
    expect(mockLoadAsync).toHaveBeenCalledWith('ionicons', { uri: 'file:///data/user/0/host.exp.exponent/cache/icon-fonts/Ionicons-fa2ab7d2557819b2.ttf' });
    expect(mockIconRenders).toHaveBeenCalledWith('diamond');
    expect(settled).toHaveBeenCalledWith(expect.objectContaining({ ok: true, source: 'fallback', attempts: 1 }));
  });

  it('skips loading entirely when the family is already registered in this process', async () => {
    mockIsLoaded.mockReturnValue(true);
    const settled = jest.fn();
    await render(<IconFontGate onSettled={settled}><Child /></IconFontGate>);
    await waitFor(() => expect(screen.getByText('home-screen')).toBeTruthy());
    expect(mockLoadAsync).not.toHaveBeenCalled();
    expect(mockFetchFallback).not.toHaveBeenCalled();
    expect(settled).toHaveBeenCalledWith(expect.objectContaining({ ok: true, source: 'already-loaded' }));
  });

  it('bounds a hanging native loader: the splash is released with a timeout error instead of spinning forever', async () => {
    jest.useFakeTimers();
    try {
      mockLoadAsync.mockImplementation(() => new Promise<void>(() => undefined)); // never settles
      mockFetchFallback.mockImplementation(() => new Promise<{ uri: string }>(() => undefined)); // never settles either
      const settled = jest.fn();
      await render(<IconFontGate onSettled={settled}><Child /></IconFontGate>);
      expect(screen.getByTestId('icon-font-loading')).toBeTruthy();
      // attempt 1: bundled timeout + fallback timeout, then the retry delay, then attempt 2 (same), then it stops.
      await act(async () => { await jest.advanceTimersByTimeAsync(ICON_FONT_TIMEOUT_MS * 2 + 1500 + ICON_FONT_TIMEOUT_MS * 2 + 50); });
      expect(screen.getByTestId('icon-font-error')).toBeTruthy();
      expect(screen.getByTestId('icon-font-error-detail').props.children).toContain('TIMEOUT');
      expect(screen.queryByText('home-screen')).toBeNull();
      expect(mockLoadAsync).toHaveBeenCalledTimes(2);
      expect(settled).toHaveBeenCalledTimes(1);
      expect(settled).toHaveBeenCalledWith(expect.objectContaining({ ok: false, stage: 'timeout', attempts: 2 }));
    } finally {
      jest.useRealTimers();
    }
  });
});
