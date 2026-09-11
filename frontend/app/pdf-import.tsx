import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AppState, Image, KeyboardAvoidingView, Platform, RefreshControl, ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';
import { api, authenticatedFetch, getToken, resolveFileUrl } from '../src/api';
import { useAuth } from '../src/context/AuthContext';
import { downloadSample, pickPDF, PickedPDF, resumeStore, uploadPDF } from '../src/pdfClient';
import { Button, Input, ui } from '../src/components/staff/Controls';

function ProtectedPreview({ row }: { row: any }) {
  const [uri,setUri]=useState('');
  useEffect(()=>{
    let alive=true,objectUrl='';
    if(Platform.OS==='web')authenticatedFetch(row.preview_url.replace('/api','')).then(async response=>{
      if(!response.ok)throw new Error('Preview unavailable');objectUrl=URL.createObjectURL(await response.blob());if(alive)setUri(objectUrl);
    }).catch(()=>setUri(''));
    else setUri(resolveFileUrl(row.preview_url));
    return()=>{alive=false;if(objectUrl)URL.revokeObjectURL(objectUrl);};
  },[row.preview_url,row.version]);
  return uri?<Image testID={`pdf-preview-${row.id}`} source={{uri,headers:{Authorization:`Bearer ${getToken()}`}}} style={ui.image} resizeMode="contain"/>:<Text testID={`pdf-preview-error-${row.id}`} style={ui.muted}>Loading protected preview…</Text>;
}

function ReviewRow({row,jobId,reload,onError}:{row:any;jobId:string;reload:()=>Promise<void>;onError:(s:string)=>void}) {
  const [editing,setEditing]=useState(false),[fields,setFields]=useState(JSON.stringify(row.fields,null,2));
  const [crop,setCrop]=useState<string>((row.crop_points||[]).join(', ')),[busy,setBusy]=useState(false);
  const save=async(body:any)=>{setBusy(true);try{await api.patch(`/pdf-upload/${jobId}/rows/${row.id}`,{version:row.version,...body});setEditing(false);await reload();}catch(e:any){onError(e.message);}finally{setBusy(false);}};
  return <View testID={`pdf-row-${row.id}`} style={ui.card}>
    <ProtectedPreview row={row}/><Text testID={`pdf-code-${row.id}`} style={ui.label}>{row.fields.product_code||'Code required'} · {row.fields.metal_type||'Type required'}</Text>
    <Text style={ui.text}>{row.fields.title||'Name required'}</Text><Text style={ui.muted}>Page {row.page} · Block {row.block_id} · {row.excluded?'Excluded':'Selected'}{ '\n' }{row.fields.category} · {row.fields.approx_weight||'Weight blank'} · {row.fields.purity||'Purity blank'}</Text>
    {row.errors?.map((e:string,i:number)=><Text testID={`pdf-row-error-${row.id}-${i}`} style={ui.error} key={i}>{e}</Text>)}
    {row.warnings?.map((w:string,i:number)=><Text testID={`pdf-row-warning-${row.id}-${i}`} style={ui.muted} key={i}>{w}</Text>)}
    {row.existing_product&&<View style={ui.card}><Text style={ui.text}>Existing product: {row.existing_product.title}</Text><Text style={ui.muted}>Explicit duplicate decision required before overwriting. Default: Skip.</Text><View style={ui.row}>
      <Button id={`pdf-skip-${row.id}`} title="Skip existing" active={row.duplicate_policy==='skip'} disabled={busy} onPress={()=>save({duplicate_policy:'skip'})}/><Button id={`pdf-update-${row.id}`} title="Confirm update existing" active={row.duplicate_policy==='update'} disabled={busy} onPress={()=>save({duplicate_policy:'update',expected_product_version:row.existing_product.version||0})}/></View></View>}
    <View style={ui.row}><Button id={`pdf-exclude-${row.id}`} title={row.excluded?'Include row':'Exclude row'} disabled={busy} onPress={()=>save({excluded:!row.excluded})}/><Button id={`pdf-edit-${row.id}`} title="Review all fields & crop" onPress={()=>setEditing(!editing)}/></View>
    {editing&&<><Input id={`pdf-fields-${row.id}`} label="All product fields (editable JSON)" value={fields} onChange={setFields} multiline/><Button id={`pdf-save-fields-${row.id}`} title="Save corrected fields" disabled={busy} onPress={()=>{try{save({fields:JSON.parse(fields)});}catch{onError('Product fields must be valid JSON');}}}/>
      <Input id={`pdf-crop-${row.id}`} label="Square photo rectangle: x0, y0, x1, y1 in PDF points" value={crop} onChange={setCrop}/><Text style={ui.muted}>Adjust inside the photograph, not into labels or adjacent products. Equal width and height required. The preview updates after the server commits.</Text><Button id={`pdf-save-crop-${row.id}`} title="Apply square crop" disabled={busy} onPress={()=>save({crop_points:crop.split(',').map(n=>Number(n.trim()))})}/></>}
    {row.commit_result&&<Text testID={`pdf-row-result-${row.id}`} style={ui.success}>{row.commit_result.status}: {row.commit_result.reason||row.commit_result.product_id}</Text>}
  </View>;
}

export default function PDFImport() {
  const router=useRouter();const params=useLocalSearchParams<{batchId?:string}>();const {user}=useAuth();
  const [caps,setCaps]=useState<any>(null),[batches,setBatches]=useState<any[]>([]),[batchId,setBatchId]=useState(params.batchId||'');
  const [file,setFile]=useState<PickedPDF|null>(null),[jobId,setJobId]=useState(''),[job,setJob]=useState<any>(null),[rows,setRows]=useState<any[]>([]);
  const [phase,setPhase]=useState(''),[bytes,setBytes]=useState(0),[error,setError]=useState(''),[busy,setBusy]=useState(false),[publish,setPublish]=useState(false),[partial,setPartial]=useState(false),[mode,setMode]=useState('template_v1');
  const [rowPage,setRowPage]=useState(1),[rowTotal,setRowTotal]=useState(0),[batchName,setBatchName]=useState('');
  const controller=useRef<AbortController|null>(null);
  useEffect(()=>{if(user?.role!=='admin')return;Promise.all([api.get('/pdf-template/capabilities'),api.get('/batches'),resumeStore.get()]).then(([cap,b,resume])=>{setCaps(cap);setBatches(b.batches||[]);if(resume){setJobId(resume.id);setBatchId(resume.batchId);setMode(resume.mode);if(resume.uri)setFile({name:resume.name,size:resume.size,uri:resume.uri});}}).catch(e=>setError(e.message));},[user]);
  const load=useCallback(async()=>{if(!jobId)return;try{const j=await api.get(`/pdf-upload/${jobId}/status`);setJob(j);setBytes(j.bytes_received);if(['review','committed'].includes(j.phase)){const p=await api.get(`/pdf-upload/${jobId}/preview?page=${rowPage}&limit=10`);setRows(p.rows);setRowTotal(p.total);}setError('');}catch(e:any){setError(`Import status may be stale. ${e.message}`);}},[jobId,rowPage]);
  useFocusEffect(useCallback(()=>{load();const timer=setInterval(load,3000);return()=>clearInterval(timer);},[load]));
  useEffect(()=>{const listener=AppState.addEventListener('change',s=>{if(s==='active')load();});return()=>listener.remove();},[load]);
  const upload=async()=>{if(!file||!batchId||!caps)return;setBusy(true);setError('');controller.current=new AbortController();try{const id=await uploadPDF(file,batchId,mode,caps.limits,controller.current.signal,(id,n,message)=>{if(id)setJobId(id);setBytes(n);setPhase(message);});setJobId(id);await load();}catch(e:any){setError(e.message);}finally{setBusy(false);}};
  const action=async(path:string)=>{try{if(path==='pause')controller.current?.abort();await api.post(`/pdf-upload/${jobId}/${path}`);await load();}catch(e:any){setError(e.message);}};
  if(user?.role!=='admin')return <SafeAreaView style={ui.guard}><Text testID="pdf-access-denied" style={ui.error}>Admin access required</Text><Button id="pdf-sign-in" title="Sign in" onPress={()=>router.replace('/login')}/></SafeAreaView>;
  return <SafeAreaView style={ui.screen}><KeyboardAvoidingView style={ui.screen} behavior={Platform.OS==='ios'?'padding':undefined}><ScrollView contentContainerStyle={ui.content} keyboardShouldPersistTaps="handled" refreshControl={<RefreshControl refreshing={false} onRefresh={load}/>}>
    <Button id="pdf-back" title="Back to products" onPress={()=>router.replace('/panel')}/><Text testID="pdf-title" style={ui.title}>Reviewed PDF import</Text><Text style={ui.muted}>Choose template → Upload → Analyze → Review → Confirm drafts. Nothing is customer-visible during analysis.</Text>
    {!!error&&<Text testID="pdf-error" style={ui.error}>{error}</Text>}
    <View style={ui.row}><Button id="pdf-download-sample" title="Download Sample PDF" icon="download-outline" onPress={()=>downloadSample().catch(e=>setError(e.message))}/><Button id="pdf-select" title="Select PDF" icon="document-outline" disabled={busy} onPress={async()=>{try{const picked=await pickPDF();if(picked)setFile(picked);}catch(e:any){setError(e.message);}}}/></View>
    <Text testID="pdf-limits" style={ui.muted}>{caps?`Configured limit: ${caps.limits.max_bytes/1024/1024} MB · ${caps.limits.max_pages} pages · ${caps.limits.chunk_bytes/1024/1024} MB chunks`:'Loading actual server limits…'}{ '\n' }Template v1 uses 1024×1024 masters and 320×320 thumbnails. Configured limits are not measured performance guarantees.</Text>
    {!jobId&&<><Text style={ui.label}>CHOOSE BATCH</Text><View style={ui.row}>{batches.map(b=><Button key={b.id} id={`pdf-batch-${b.id}`} title={b.name} active={batchId===b.id} onPress={()=>setBatchId(b.id)}/>)}</View><Input id="pdf-new-batch-name" label="Or create a batch" value={batchName} onChange={setBatchName}/><Button id="pdf-create-batch" title="Create batch" disabled={!batchName.trim()} onPress={async()=>{try{const b=await api.post('/batches',{name:batchName,metal_type:'mixed'});setBatches([...batches,b]);setBatchId(b.id);setBatchName('');}catch(e:any){setError(e.message);}}}/>
      <View style={ui.row}><Button id="pdf-mode-template" title="Template v1" active={mode==='template_v1'} onPress={()=>setMode('template_v1')}/><Button id="pdf-mode-legacy" title="Explicit legacy pages" active={mode==='legacy_pages'} onPress={()=>setMode('legacy_pages')}/></View>{mode==='legacy_pages'&&<Text style={ui.error}>Manual legacy mode: each nonblank page needs field correction and photo review. No OCR or automatic publication.</Text>}</>}
    {file&&<Text testID="pdf-selected-file" style={ui.text}>{file.name} · {(file.size/1024/1024).toFixed(2)} MB</Text>}
    <Text testID="pdf-upload-bytes" style={ui.muted}>{bytes.toLocaleString()} bytes acknowledged{phase?` · ${phase}`:''}</Text>
    {(!job||['uploading','paused'].includes(job.phase))&&<Button id="pdf-upload" title={jobId?'Resume same file':'Upload & analyze'} disabled={busy||!file||!batchId||!caps} onPress={upload}/>}
    {job&&<View style={ui.card}><Text testID="pdf-job-phase" style={ui.label}>{job.phase.toUpperCase()}</Text><Text testID="pdf-analysis-progress" style={ui.text}>Analysis: {job.pages_processed} / {job.total_pages??'—'} pages · {job.product_count} product blocks</Text>{job.error&&<Text style={ui.error}>{job.error}</Text>}
      <View style={ui.row}>{['uploading','analyzing','queued'].includes(job.phase)&&<Button id="pdf-pause" title="Pause upload / analysis" onPress={()=>action('pause')}/>}{job.phase==='paused'&&<Button id="pdf-resume-job" title="Resume job" onPress={()=>action('resume')}/>}{!['committed','cancelled'].includes(job.phase)&&<Button id="pdf-cancel" title="Cancel import" onPress={()=>action('cancel')}/>}</View>
      {['committed','cancelled','error'].includes(job.phase)&&<Button id="pdf-new-import" title="Choose another import" onPress={async()=>{await resumeStore.clear();setJobId('');setJob(null);setRows([]);setFile(null);}}/>}
      {job.phase==='error'&&<Button id="pdf-retry-analysis" title="Retry failed analysis" onPress={()=>action('resume')}/>}
    </View>}
    {rows.map(row=><ReviewRow key={`${row.id}-${row.version}`} row={row} jobId={jobId} reload={load} onError={setError}/>)}
    {rowTotal>10&&<View style={ui.row}><Button id="pdf-rows-prev" title="Previous products" disabled={rowPage<=1} onPress={()=>setRowPage(rowPage-1)}/><Button id="pdf-rows-next" title="Next products" disabled={rowPage*10>=rowTotal} onPress={()=>setRowPage(rowPage+1)}/></View>}
    {job?.phase==='review'&&<View style={ui.card}><Text style={ui.label}>FINAL CONFIRMATION</Text><Button id="pdf-publish-toggle" title={publish?'Publish selected products: YES':'Save hidden drafts (default)'} active={publish} onPress={()=>setPublish(!publish)}/><Button id="pdf-partial-toggle" title={partial?'Valid selected rows only: confirmed':'Require all selected rows valid'} active={partial} onPress={()=>setPartial(!partial)}/><Button id="pdf-confirm-import" title={publish?'Confirm import & publish':'Confirm import as hidden drafts'} disabled={busy} onPress={async()=>{setBusy(true);try{await api.post(`/pdf-upload/${jobId}/commit`,{version:job.version,confirm:true,publish,allow_partial:partial});await load();}catch(e:any){setError(e.message);}finally{setBusy(false);}}}/></View>}
    {job?.result&&<View testID="pdf-result" style={ui.card}><Text style={ui.text}>Created {job.result.created} · Updated {job.result.updated} · Skipped {job.result.skipped} · Failed {job.result.failed}</Text>{job.result.rows.map((r:any)=><Text key={r.row_id} testID={`pdf-result-${r.row_id}`} style={ui.muted}>{r.row_id.slice(0,8)} · {r.status} · {r.reason||r.product_id}</Text>)}</View>}
  </ScrollView></KeyboardAvoidingView></SafeAreaView>;
}