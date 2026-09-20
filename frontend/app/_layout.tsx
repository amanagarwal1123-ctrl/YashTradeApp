import React, { useCallback, useEffect } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import * as SplashScreen from 'expo-splash-screen';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { KeyboardProvider } from 'react-native-keyboard-controller';
import { useRouter } from 'expo-router';
import { AuthProvider, useAuth } from '../src/context/AuthContext';
import { LanguageProvider } from '../src/context/LanguageContext';
import { IconFontGate } from '../src/fonts/IconFontGate';
import { Colors, FontSize } from '../src/theme';
import { authorizedDestination } from '../src/navigation';
import { configureForeground, notificationsModule } from '../src/push';

// Hold the native splash until the icon font is registered (or has definitively failed). A hard
// deadline guarantees the splash can never stay up forever, even if font promises hang.
SplashScreen.preventAutoHideAsync().catch(() => {});
const SPLASH_DEADLINE_MS = 15000;

function ReviewEnvironmentBanner() {
  const { user } = useAuth();
  const insets = useSafeAreaInsets();
  if (!user?.review_environment) return null;
  return (
    <View style={[styles.reviewBanner, { paddingBottom: Math.max(insets.bottom, 4) }]} testID="review-environment-banner" accessibilityRole="header">
      <Text style={styles.reviewBannerText}>STORE-REVIEW ENVIRONMENT · synthetic data · SMS/calls simulated</Text>
    </View>
  );
}

/** Routes notification taps (foreground, background and cold start) to a role-authorised in-app destination. */
function NotificationTapRouter() {
  const { user, loading } = useAuth();
  const router = useRouter();
  useEffect(() => { configureForeground(); }, []);
  useEffect(() => {
    const Notifications = notificationsModule();
    if (!Notifications || loading) return;
    const open = (response: any) => {
      const data = response?.notification?.request?.content?.data || {};
      if (!user) return; // signed out: the login screen is shown; nothing from the alert is trusted
      router.push(authorizedDestination(data.destination, user.role) as any);
    };
    const sub = Notifications.addNotificationResponseReceivedListener(open);
    Notifications.getLastNotificationResponseAsync().then((last: any) => { if (last) open(last); }).catch(() => {});
    return () => sub.remove();
  }, [user?.id, user?.role, loading]);
  return null;
}

export default function RootLayout() {
  useEffect(() => {
    const deadline = setTimeout(() => { SplashScreen.hideAsync().catch(() => {}); }, SPLASH_DEADLINE_MS);
    return () => clearTimeout(deadline);
  }, []);
  const onFontsSettled = useCallback(() => { SplashScreen.hideAsync().catch(() => {}); }, []);

  return (
    <GestureHandlerRootView style={styles.root}>
    <KeyboardProvider>
    <AuthProvider>
      <LanguageProvider>
        <StatusBar style="light" />
        <IconFontGate onSettled={onFontsSettled}>
          <NotificationTapRouter />
          <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: '#050505' }, animation: 'slide_from_right' }}>
            <Stack.Screen name="index" />
            <Stack.Screen name="login" />
            <Stack.Screen name="help" options={{ presentation: 'modal' }} />
            <Stack.Screen name="verify-otp" />
            <Stack.Screen name="review-access" options={{ presentation: 'modal' }} />
            <Stack.Screen name="(tabs)" />
            <Stack.Screen name="product/[id]" options={{ presentation: 'modal' }} />
            <Stack.Screen name="ai-assistant" options={{ presentation: 'modal' }} />
            <Stack.Screen name="rewards" options={{ presentation: 'modal' }} />
            <Stack.Screen name="request-call" options={{ presentation: 'modal' }} />
            <Stack.Screen name="request-success" options={{ presentation: 'modal', animation: 'fade' }} />
            <Stack.Screen name="knowledge" options={{ presentation: 'modal' }} />
            <Stack.Screen name="image-viewer" options={{ presentation: 'modal', animation: 'fade' }} />
            <Stack.Screen name="my-requests" options={{ presentation: 'modal' }} />
            <Stack.Screen name="my-orders" options={{ presentation: 'modal' }} />
            <Stack.Screen name="edit-profile" options={{ presentation: 'modal' }} />
            <Stack.Screen name="delete-account" options={{ presentation: 'modal' }} />
            <Stack.Screen name="telecaller" />
            <Stack.Screen name="wishlist" options={{ presentation: 'modal' }} />
            <Stack.Screen name="cart" options={{ presentation: 'modal' }} />
            <Stack.Screen name="panel" options={{ presentation: 'modal' }} />
            <Stack.Screen name="rate-list" options={{ presentation: 'modal' }} />
            <Stack.Screen name="schemes" options={{ presentation: 'modal' }} />
            <Stack.Screen name="brands" options={{ presentation: 'modal' }} />
            <Stack.Screen name="showroom" options={{ presentation: 'modal' }} />
            <Stack.Screen name="exhibition" options={{ presentation: 'modal' }} />
            <Stack.Screen name="notifications" options={{ presentation: 'modal' }} />
            <Stack.Screen name="admin-notifications" />
            <Stack.Screen name="staff-requests" />
          </Stack>
          <ReviewEnvironmentBanner />
        </IconFontGate>
      </LanguageProvider>
    </AuthProvider>
    </KeyboardProvider>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  reviewBanner: { backgroundColor: Colors.gold, paddingVertical: 4, paddingHorizontal: 8, alignItems: 'center' },
  reviewBannerText: { color: '#000', fontSize: FontSize.xs, fontWeight: '700', letterSpacing: 0.5 },
});
