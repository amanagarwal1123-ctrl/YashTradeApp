import { useCallback, useEffect } from 'react';
import { BackHandler, Keyboard, Platform } from 'react-native';
import { useRouter } from 'expo-router';

export const ROLES = ['customer', 'admin', 'telecaller', 'billing_executive', 'upload_executive'] as const;
export type Role = (typeof ROLES)[number];
export const ROLE_LABELS: Record<string, string> = {
  customer: 'Customer', admin: 'Administrator', telecaller: 'Telecaller', billing_executive: 'Billing Executive', upload_executive: 'Upload Executive',
};

/** The root/home screen of each role: the destination after sign-in, after a deep link with no history and on hardware back at root. */
export const homeRouteFor = (role?: string | null): string => {
  switch (role) {
    case 'telecaller': return '/telecaller';
    case 'admin': case 'billing_executive': case 'upload_executive': return '/panel';
    case 'customer': return '/(tabs)';
    default: return '/login';
  }
};

/** Replaces the whole history with the role's home so login / OTP screens can never be reached with back. */
export function resetToHome(router: ReturnType<typeof useRouter>, role?: string | null) {
  try { if (router.canDismiss()) router.dismissAll(); } catch { /* nothing to dismiss */ }
  router.replace(homeRouteFor(role) as any);
}

/** Back that never lands on login: previous authorized screen when there is history, otherwise the role's home. */
export function useSafeBack(role?: string | null) {
  const router = useRouter();
  return useCallback(() => {
    Keyboard.dismiss();
    if (router.canGoBack()) router.back();
    else router.replace(homeRouteFor(role) as any);
  }, [router, role]);
}

/**
 * Android hardware/gesture back on a role's ROOT screen: dismiss the keyboard if open, otherwise stay on the screen
 * (never exit, never show login). Registered only while the root screen is mounted; `onBack` may handle tab switches
 * or modal dismissal first and return true to consume the event.
 */
export function useRootBackHandler(onBack?: () => boolean) {
  useEffect(() => {
    if (Platform.OS !== 'android') return;
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      if (Keyboard.isVisible()) { Keyboard.dismiss(); return true; }
      if (onBack && onBack()) return true;
      return true; // root screen: stay put
    });
    return () => sub.remove();
  }, [onBack]);
}

/** Route families and the roles allowed to open them from a notification / deep link (server permissions still apply). */
const ROUTE_ROLES: [string[], readonly string[]][] = [
  [['/(tabs)', '/wishlist', '/cart', '/my-requests', '/my-orders', '/rewards', '/request-call', '/request-success', '/edit-profile', '/delete-account', '/ai-assistant', '/ai-consent'], ['customer']],
  [['/admin-notifications', '/customer-directory', '/review-keys', '/media-usage', '/staff-reports'], ['admin']],
  [['/staff-requests', '/telecaller'], ['admin', 'telecaller', 'billing_executive']],
  [['/panel', '/staff-rates'], ['admin', 'billing_executive', 'upload_executive']],
  [['/product-catalog', '/pdf-import', '/catalog-author', '/product-photos'], ['admin', 'upload_executive']],
];

/** Routes a notification / deep-link destination only when the signed-in role may open it; otherwise the role's home. */
export function authorizedDestination(destination: string | undefined, role?: string | null): string {
  if (!role || !destination || !destination.startsWith('/') || destination.startsWith('//')) return homeRouteFor(role);
  const path = destination.split('?')[0];
  for (const [prefixes, roles] of ROUTE_ROLES) {
    if (prefixes.some(p => path === p || path.startsWith(p + '/') || path.startsWith(p + '?'))) {
      if (!roles.includes(role)) return homeRouteFor(role);
      // The telecaller root is that role's home; other query workers reach the same workspace through /staff-requests.
      if (path === '/telecaller' && role !== 'telecaller') return destination.replace('/telecaller', '/staff-requests');
      return destination;
    }
  }
  return destination; // public/shared screens (product, rate list, schemes, brands, notifications history, …)
}
