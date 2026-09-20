import React, { useCallback, useState } from 'react';
import { ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';
import { api } from '../src/api';
import { useAuth } from '../src/context/AuthContext';
import { Button, ui } from '../src/components/staff/Controls';
// Content domain (R10): administrators and Upload Executives; the server enforces the same gate on every route.
const CONTENT_ROLES = ['admin', 'upload_executive'];

export default function MediaUsage() {
  const {user}=useAuth(),router=useRouter();const [data,setData]=useState<any>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const load=useCallback(async()=>{setBusy(true);try{setData(await api.get('/admin/media/usage'));setError('');}catch(e:any){setError(e.message);}finally{setBusy(false);}},[]);
  useFocusEffect(useCallback(()=>{if(CONTENT_ROLES.includes(user?.role||''))load();},[user,load]));
  if(!CONTENT_ROLES.includes(user?.role||''))return <SafeAreaView style={ui.guard}><Text testID="media-usage-denied" style={ui.error}>Admin or Upload Executive access required</Text></SafeAreaView>;
  return <SafeAreaView style={ui.screen}><ScrollView contentContainerStyle={ui.content}><Button id="media-usage-back" title="Back" onPress={()=>router.back()}/><Text testID="media-usage-title" style={ui.title}>Media usage</Text>
    {!!error&&<Text testID="media-usage-error" style={ui.error}>{error}</Text>}<Button id="media-usage-refresh" title="Refresh accounting" disabled={busy} onPress={load}/>
    {data&&<><View style={ui.card}><Text testID="media-tracked-bytes" style={ui.text}>{data.tracked.bytes.toLocaleString()} tracked bytes · {data.tracked.objects} objects</Text><Text testID="media-write-budget" style={ui.muted}>Application write budget: {data.write_budget_bytes.toLocaleString()} bytes / {data.write_object_limit} objects. This is NOT a provider quota or remaining-space guarantee.</Text>
      {data.remaining&&<Text testID="media-remaining" style={ui.muted}>Remaining before the application ceiling: {data.remaining.bytes.toLocaleString()} bytes · {data.remaining.objects} objects</Text>}
      {data.limit_reached&&<Text testID="media-limit-reached" style={ui.error}>Uploads blocked: {data.limit_reached} reached ({data.limit_reached==='MEDIA_WRITE_BUDGET_BYTES'?`${data.tracked.bytes.toLocaleString()} of ${data.write_budget_bytes.toLocaleString()} bytes`:`${data.tracked.objects} of ${data.write_object_limit} objects`}). Owner review required before raising it in backend/.env.</Text>}
      {data.high_watermark&&<Text testID="media-high-watermark" style={ui.error}>80% high-watermark reached. Review capacity before more uploads.</Text>}</View>
      <Text testID="media-inventory-warning" style={ui.error}>{data.warning}</Text>{data.groups.map((g:any)=><View key={g.purpose} style={ui.card}><Text testID={`media-group-${g.purpose}`} style={ui.text}>{g.purpose}: {g.objects} objects / {g.bytes.toLocaleString()} bytes · {g.unknown_size_objects} sizes unknown</Text></View>)}
      <Text testID="media-deletion-status" style={ui.error}>{data.blocked_deletions} deletion candidates blocked. Managed storage has no supported delete API; no remote objects have been erased.</Text>
      <Button id="media-lifecycle-audit" title="Audit lifecycle candidates (no remote deletion)" disabled={busy} onPress={async()=>{setBusy(true);try{await api.post('/admin/media/lifecycle-audit');await load();}catch(e:any){setError(e.message);}finally{setBusy(false);}}}/>
    </>}
  </ScrollView></SafeAreaView>;
}