import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { AuthProvider } from '../src/context/AuthContext';
import { LanguageProvider } from '../src/context/LanguageContext';

export default function RootLayout() {
  return (
    <AuthProvider>
      <LanguageProvider>
        <StatusBar style="light" />
        <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: '#050505' }, animation: 'slide_from_right' }}>
          <Stack.Screen name="index" />
          <Stack.Screen name="login" />
          <Stack.Screen name="verify-otp" />
          <Stack.Screen name="(tabs)" />
          <Stack.Screen name="product/[id]" options={{ presentation: 'modal' }} />
          <Stack.Screen name="ai-assistant" options={{ presentation: 'modal' }} />
          <Stack.Screen name="rewards" options={{ presentation: 'modal' }} />
          <Stack.Screen name="request-call" options={{ presentation: 'modal' }} />
          <Stack.Screen name="request-success" options={{ presentation: 'modal', animation: 'fade' }} />
          <Stack.Screen name="knowledge" options={{ presentation: 'modal' }} />
          <Stack.Screen name="image-viewer" options={{ presentation: 'modal', animation: 'fade' }} />
          <Stack.Screen name="my-requests" options={{ presentation: 'modal' }} />
          <Stack.Screen name="wishlist" options={{ presentation: 'modal' }} />
          <Stack.Screen name="cart" options={{ presentation: 'modal' }} />
          <Stack.Screen name="panel" options={{ presentation: 'modal' }} />
          <Stack.Screen name="rate-list" options={{ presentation: 'modal' }} />
          <Stack.Screen name="schemes" options={{ presentation: 'modal' }} />
          <Stack.Screen name="brands" options={{ presentation: 'modal' }} />
          <Stack.Screen name="showroom" options={{ presentation: 'modal' }} />
          <Stack.Screen name="exhibition" options={{ presentation: 'modal' }} />
        </Stack>
      </LanguageProvider>
    </AuthProvider>
  );
}
