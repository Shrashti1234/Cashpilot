import {useEffect,useState} from 'react';

/** Clear prior tenant data immediately when the URL changes; ignore late reads. */
export function useAuthenticatedResource<T>(url:string|null,token:string,revision=0){
 const [state,setState]=useState<{url:string|null;data:T|null;loading:boolean;error:string}>({url:null,data:null,loading:false,error:''});
 useEffect(()=>{
  if(!url){setState({url:null,data:null,loading:false,error:''});return;}
  const controller=new AbortController();let active=true;
  const timer=window.setTimeout(()=>controller.abort(),90000);
  setState({url,data:null,loading:true,error:''});
  async function load(){try{
   const r=await fetch(url!,{headers:{Authorization:`Bearer ${token}`},signal:controller.signal});
   if(!r.ok){const body=await r.json().catch(()=>null);throw new Error(typeof body?.detail==='string'?body.detail:'Could not load financial records.');}
   const data:T=await r.json();if(active)setState({url,data,loading:false,error:''});
  }catch(e){if(active)setState({url,data:null,loading:false,error:controller.signal.aborted?'Request timed out. Please retry.':e instanceof Error?e.message:'Could not load records.'});}
  finally{window.clearTimeout(timer);}}
  void load();return()=>{active=false;controller.abort();window.clearTimeout(timer);};
 },[url,token,revision]);
 return state.url===url?state:{url,data:null,loading:Boolean(url),error:''};
}
