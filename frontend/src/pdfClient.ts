import { Platform } from 'react-native';
import * as DocumentPicker from 'expo-document-picker';
import { File as NativeFile, Paths } from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import * as SecureStore from 'expo-secure-store';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { sha256 } from '@noble/hashes/sha256';
import { bytesToHex } from '@noble/hashes/utils';
import { api, API_BASE, authenticatedFetch, getToken, responseJson } from './api';

export type PickedPDF = {name: string; size: number; uri: string; webFile?: File};
const KEY = 'yash-pdf-resume-v1';
export const resumeStore = {
  get: async () => {const s=Platform.OS==='web'?await AsyncStorage.getItem(KEY):await SecureStore.getItemAsync(KEY);return s?JSON.parse(s):null;},
  set: async (v:any) => {const s=JSON.stringify(v);if(Platform.OS==='web')await AsyncStorage.setItem(KEY,s);else await SecureStore.setItemAsync(KEY,s);},
  clear: async () => {if(Platform.OS==='web')await AsyncStorage.removeItem(KEY);else await SecureStore.deleteItemAsync(KEY);},
};

export async function pickPDF(): Promise<PickedPDF|null> {
  const result=await DocumentPicker.getDocumentAsync({type:'application/pdf',copyToCacheDirectory:true,multiple:false,base64:false});
  if(result.canceled)return null;
  const asset=result.assets[0];
  return {name:asset.name,size:asset.size||new NativeFile(asset.uri).size,uri:asset.uri,webFile:asset.file};
}
async function bytes(file:PickedPDF,offset:number,length:number):Promise<Uint8Array> {
  if(Platform.OS==='web') {
    if(!file.webFile)throw new Error('Reselect the same PDF to resume in this browser');
    return new Uint8Array(await file.webFile.slice(offset,offset+length).arrayBuffer());
  }
  const handle=new NativeFile(file.uri).open();
  try{handle.offset=offset;return handle.readBytes(length);}finally{handle.close();}
}
export async function hashFile(file:PickedPDF,chunkSize:number,progress:(s:string)=>void) {
  const digest=sha256.create();
  for(let offset=0;offset<file.size;offset+=chunkSize){digest.update(await bytes(file,offset,Math.min(chunkSize,file.size-offset)));progress(`Checking file identity ${Math.round(Math.min(offset+chunkSize,file.size)/file.size*100)}%`);await new Promise(r=>setTimeout(r,0));}
  return bytesToHex(digest.digest());
}

export async function uploadPDF(file:PickedPDF,batchId:string,mode:string,limits:any,signal:AbortSignal,onState:(id:string,bytes:number,detail:string)=>void) {
  if(file.size>limits.max_bytes)throw new Error(`Configured size limit is ${Math.round(limits.max_bytes/1024/1024)} MB`);
  const hash=await hashFile(file,limits.chunk_bytes,s=>onState('',0,s));
  const prior=await resumeStore.get();
  if(prior&&prior.batchId===batchId&&prior.sha256!==hash)throw new Error('Wrong file for resume. Cancel the previous import or choose its original PDF.');
  const init=await api.post('/pdf-upload/init',{batch_id:batchId,filename:file.name,file_size:file.size,total_chunks:Math.ceil(file.size/limits.chunk_bytes),sha256:hash,mode});
  const id=init.upload_id;
  await resumeStore.set({id,batchId,sha256:hash,name:file.name,size:file.size,uri:Platform.OS==='web'?'':file.uri,mode});
  let status=await api.get(`/pdf-upload/${id}/status`);
  if(status.phase==='paused')status=await api.post(`/pdf-upload/${id}/resume`);
  onState(id,status.bytes_received,'Upload acknowledged by server');
  if(status.phase!=='uploading')return id;
  const received=new Set(status.received_chunk_indices);
  let uploaded=status.bytes_received;
  for(let i=0;i<status.total_chunks;i++){
    if(signal.aborted)throw new Error('Upload paused; acknowledged chunks are retained');
    if(received.has(i))continue;
    const offset=i*limits.chunk_bytes;const part=await bytes(file,offset,Math.min(limits.chunk_bytes,file.size-offset));
    const checksum=bytesToHex(sha256(part));
    let temp:NativeFile|null=null;
    if(Platform.OS!=='web'){temp=new NativeFile(Paths.cache,`yash-chunk-${id}-${i}`);temp.create({overwrite:true});temp.write(part);}
    try{
      for(let attempt=0;attempt<4;attempt++){
        try{
          const body=new FormData();
          if(Platform.OS==='web')body.append('file',new Blob([part as BlobPart]),`chunk-${i}`);
          else body.append('file',{uri:temp!.uri,name:`chunk-${i}`,type:'application/octet-stream'} as any);
          await responseJson(await authenticatedFetch(`/pdf-upload/${id}/chunk?chunk_index=${i}`,{method:'POST',headers:{'X-Chunk-Sha256':checksum},body,signal}));break;
        }catch(e:any){if(signal.aborted||attempt===3||(e.status&&e.status<500))throw e;await new Promise(r=>setTimeout(r,1000*2**attempt));}
      }
    }finally{temp?.delete();}
    uploaded+=part.length;onState(id,uploaded,`Uploaded ${uploaded.toLocaleString()} / ${file.size.toLocaleString()} bytes`);
  }
  await api.post(`/pdf-upload/${id}/complete`);return id;
}

export async function downloadSample() {
  const filename='Yash-Catalog-Template-v1.pdf';
  if(Platform.OS==='web'){
    const res=await authenticatedFetch('/pdf-template/sample.pdf');if(!res.ok)await responseJson(res);
    const url=URL.createObjectURL(await res.blob());const anchor=document.createElement('a');anchor.href=url;anchor.download=filename;anchor.click();setTimeout(()=>URL.revokeObjectURL(url),30000);
  }else{
    await api.get('/auth/me');
    const destination=new NativeFile(Paths.cache,filename);if(destination.exists)destination.delete();
    const file=await NativeFile.downloadFileAsync(`${API_BASE}/pdf-template/sample.pdf`,destination,{headers:{Authorization:`Bearer ${getToken()}`}});
    if(await Sharing.isAvailableAsync())await Sharing.shareAsync(file.uri,{mimeType:'application/pdf',UTI:'com.adobe.pdf',dialogTitle:filename});
    else throw new Error('PDF saved to app cache, but this device has no supported share/open service');
  }
}