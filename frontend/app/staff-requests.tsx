import React from 'react';
import { useRouter } from 'expo-router';
import RequestsWorkspace from '../src/components/staff/RequestsWorkspace';
export default function StaffRequests() {
  const router = useRouter();
  return <RequestsWorkspace onBack={() => router.replace('/panel')}/>;
}