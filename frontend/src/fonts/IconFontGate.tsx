/**
 * Single root gate for the icon font used throughout the app (Ionicons is the only icon family).
 * Icon-bearing routes are not mounted until the exact font map is registered, so a failed font can
 * never produce hundreds of blank icons and unhandled ExpoFontLoader rejections. The loading and
 * error states use system fonts only and never mount the icon family themselves.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Platform, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import * as Font from 'expo-font';
import { Ionicons } from '@expo/vector-icons';
import { Colors, FontSize, Spacing } from '../theme';
import { BACKEND_URL } from '../api';
import { createIconFontLoader, LoadOutcome } from './iconFontLoader';
import { createFallbackFetcher } from './fallbackFont';

export const ICON_FONT_MAP = Ionicons.font as Record<string, number>;
export const IONICONS_FAMILY = Object.keys(ICON_FONT_MAP)[0]; // "ionicons" — the registered family name
export const ICON_FONT_TIMEOUT_MS = 12000;

type GateState = { phase: 'loading' | 'ready' | 'error'; outcome?: LoadOutcome };

export function IconFontGate({ children, onSettled }: { children: React.ReactNode; onSettled?: (outcome: LoadOutcome) => void }) {
  const [state, setState] = useState<GateState>({ phase: 'loading' });
  const [retrying, setRetrying] = useState(false);
  const mounted = useRef(true);
  const loader = useMemo(() => createIconFontLoader({
    family: IONICONS_FAMILY,
    isLoaded: (family) => Font.isLoaded(family),
    loadBundled: () => Font.loadAsync(ICON_FONT_MAP),
    loadFromUri: (family, uri) => Font.loadAsync(family, { uri }),
    fetchFallback: createFallbackFetcher(BACKEND_URL),
    timeoutMs: ICON_FONT_TIMEOUT_MS,
    autoRetries: 1,
    retryDelayMs: 1500,
    onEvent: (event, detail) => { if (event !== 'fallback-loaded') console.warn(`[icon-font] ${event}${detail ? ': ' + detail : ''}`); },
  }), []);

  const settle = useCallback((outcome: LoadOutcome) => {
    if (!mounted.current) return;
    setState({ phase: outcome.ok ? 'ready' : 'error', outcome });
    setRetrying(false);
    onSettled?.(outcome);
  }, [onSettled]);

  useEffect(() => {
    mounted.current = true;
    loader.load().then(settle).catch((error) => settle({ ok: false, stage: 'bundled', message: String(error), fallbackTried: false, attempts: 0 }));
    return () => { mounted.current = false; };
  }, [loader, settle]);

  const retry = useCallback(() => {
    if (loader.isInFlight()) return;
    setRetrying(true);
    loader.retry().then(settle).catch((error) => settle({ ok: false, stage: 'bundled', message: String(error), fallbackTried: false, attempts: 0 }));
  }, [loader, settle]);

  if (state.phase === 'ready') return <>{children}</>;

  if (state.phase === 'loading') {
    return (
      <View style={styles.screen} testID="icon-font-loading">
        <ActivityIndicator size="large" color={Colors.gold} />
        <Text style={styles.brand}>YASH TRADE</Text>
        <Text style={styles.muted}>Preparing the app…</Text>
      </View>
    );
  }

  const outcome = state.outcome as Extract<LoadOutcome, { ok: false }>;
  return (
    <View style={styles.screen} testID="icon-font-error">
      <Text style={styles.brand}>YASH TRADE</Text>
      <Text style={styles.title}>Some app graphics could not be loaded</Text>
      <Text style={styles.body}>
        The icon font that draws the app&apos;s buttons and menus is unavailable on this device right now
        {outcome.stage === 'timeout' ? ' (the download timed out)' : ''}. Check your connection and try again.
      </Text>
      <TouchableOpacity testID="icon-font-retry" style={[styles.button, retrying && styles.buttonDisabled]} onPress={retry} disabled={retrying} accessibilityRole="button">
        {retrying ? <ActivityIndicator color="#000" /> : <Text style={styles.buttonText}>TRY AGAIN</Text>}
      </TouchableOpacity>
      <Text style={styles.detail} testID="icon-font-error-detail" numberOfLines={4}>
        {`Attempt ${outcome.attempts}${outcome.fallbackTried ? ' · fallback source tried' : ''} · ${Platform.OS}\n${outcome.message}`}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Colors.background, alignItems: 'center', justifyContent: 'center', paddingHorizontal: Spacing.xl, gap: Spacing.md },
  brand: { fontSize: FontSize.xl, fontWeight: '700', color: Colors.gold, letterSpacing: 4, marginTop: Spacing.md },
  muted: { fontSize: FontSize.sm, color: Colors.textMuted },
  title: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text, textAlign: 'center' },
  body: { fontSize: FontSize.sm, color: Colors.textSecondary, textAlign: 'center', lineHeight: 20 },
  button: { minWidth: 200, minHeight: 48, backgroundColor: Colors.gold, borderRadius: 12, alignItems: 'center', justifyContent: 'center', paddingHorizontal: Spacing.lg, marginTop: Spacing.sm },
  buttonDisabled: { opacity: 0.5 },
  buttonText: { color: '#000', fontWeight: '700', letterSpacing: 2, fontSize: FontSize.base },
  detail: { fontSize: FontSize.xs, color: Colors.textMuted, textAlign: 'center', marginTop: Spacing.sm },
});
