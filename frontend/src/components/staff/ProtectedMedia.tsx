import React, { useEffect, useState } from 'react';
import { Platform, StyleProp, ImageStyle, Text } from 'react-native';
import { Image } from 'expo-image';
import { API_BASE, authenticatedFetch, getToken } from '../../api';
import { ui } from './Controls';

/** Owner-bound import previews / private media: authorised per fetch, never kept in the device image cache. */
export default function ProtectedMedia({uri,id,style}:{uri:string;id:string;style:StyleProp<ImageStyle>}) {
  const [source,setSource]=useState(''),[error,setError]=useState('');
  useEffect(()=>{
    let active=true,objectUrl='';setError('');setSource('');
    if(Platform.OS==='web'&&uri?.startsWith(API_BASE)){
      authenticatedFetch(uri.slice(API_BASE.length)).then(async response=>{
        if(!response.ok)throw new Error('Private image could not be loaded');
        objectUrl=URL.createObjectURL(await response.blob());if(active)setSource(objectUrl);
      }).catch(e=>{if(active)setError(e.message);});
    }else setSource(uri);
    return()=>{active=false;if(objectUrl)URL.revokeObjectURL(objectUrl);};
  },[uri]);
  if(error)return <Text testID={`${id}-error`} style={ui.error}>{error}</Text>;
  return <Image testID={id} source={{uri:source,headers:uri?.startsWith(API_BASE)?{Authorization:`Bearer ${getToken()}`}:undefined}} style={style as any} contentFit="contain" cachePolicy="none"/>;
}