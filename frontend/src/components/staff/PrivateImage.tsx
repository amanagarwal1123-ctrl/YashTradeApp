import React, { useEffect, useState } from 'react';
import { Image, Platform, StyleProp, Text, ImageStyle } from 'react-native';
import { API_BASE, authenticatedFetch, getToken, resolveFileUrl } from '../../api';
import { ui } from './Controls';

export default function PrivateImage({id,url,style}:{id:string;url:string;style:StyleProp<ImageStyle>}) {
  const [uri,setUri]=useState(''),[error,setError]=useState('');
  const absolute=resolveFileUrl(url),canonical=absolute.startsWith(`${API_BASE}/`);
  useEffect(()=>{
    let alive=true,objectUrl='';setUri('');setError('');
    if(!canonical){
      if(absolute.startsWith('https://'))setUri(absolute);
      else setError('Unsupported image URL');
    }else if(Platform.OS==='web') authenticatedFetch(absolute.slice(API_BASE.length)).then(async r=>{
      if(!r.ok)throw new Error('Image unavailable. Refresh your session and retry.');
      const blob=await r.blob(); if(!alive)return;
      objectUrl=URL.createObjectURL(blob);setUri(objectUrl);
    }).catch(e=>{if(alive)setError(e.message);});
    else setUri(absolute);
    return()=>{alive=false;if(objectUrl)URL.revokeObjectURL(objectUrl);};
  },[absolute,canonical]);
  return uri&&!error?<Image testID={id} source={{uri,...(canonical?{headers:{Authorization:`Bearer ${getToken()}`}}:{})}} resizeMode="contain" style={style} onError={()=>setError('Image could not be loaded')}/>:<Text testID={`${id}-status`} style={error?ui.error:ui.muted}>{error||'Loading private image…'}</Text>;
}