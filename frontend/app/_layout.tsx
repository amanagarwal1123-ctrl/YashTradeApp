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
          <Stack.Screen name="knowledge" options={{ presentation: 'modal' }} />
          <Stack.Screen name="admin" options={{ presentation: 'modal' }} />
          <Stack.Screen name="admin-batches" options={{ presentation: 'modal' }} />
          <Stack.Screen name="admin-batch-detail" options={{ presentation: 'modal' }} />
          <Stack.Screen name="image-viewer" options={{ presentation: 'modal', animation: 'fade' }} />
          <Stack.Screen name="executive" options={{ presentation: 'modal' }} />
        </Stack>
      </LanguageProvider>
    </AuthProvider>
  );
}
