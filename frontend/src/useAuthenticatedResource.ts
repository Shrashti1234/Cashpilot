import {useEffect,useState} from 'react';

/** Clear prior tenant data immediately when the URL changes; ignore late reads. */
export function useAuthenticatedResource<T>(url:string|null,token:string,revision=0){
 const [state,setState]=useState<{url:string|null;token:string;revision:number;data:T|null;loading:boolean;error:string}>({url:null,token:'',revision:0,data:null,loading:false,error:''});
 useEffect(()=>{
  const key={url,token,revision};
  if(!url){setState({...key,data:null,loading:false,error:''});return;}
  const controller=new AbortController();let active=true;
  const timer=window.setTimeout(()=>controller.abort(),90000);
  setState({...key,data:null,loading:true,error:''});
  async function load(){try{
   const r=await fetch(url!,{headers:{Authorization:`Bearer ${token}`},signal:controller.signal});
   if(!r.ok){const body=await r.json().catch(()=>null);throw new Error(typeof body?.detail==='string'?body.detail:'Could not load financial records.');}
   const data:T=await r.json();if(active)setState({...key,data,loading:false,error:''});
  }catch(e){if(active)setState({...key,data:null,loading:false,error:controller.signal.aborted?'Request timed out. Please retry.':e instanceof Error?e.message:'Could not load records.'});}
  finally{window.clearTimeout(timer);}}
  void load();return()=>{active=false;controller.abort();window.clearTimeout(timer);};
 },[url,token,revision]);
 if(state.url!==url||state.token!==token||state.revision!==revision)return {url,data:null,loading:Boolean(url),error:''};
 return {url,data:state.data,loading:state.loading,error:state.error};
}
