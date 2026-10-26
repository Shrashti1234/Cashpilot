import React,{useState} from 'react';
import {Copy} from 'lucide-react';
import type {BusinessWorkspace} from './CustomerManagement';
import {useAuthenticatedResource} from './useAuthenticatedResource';
import './operations.css';

export function JoinBusiness({apiUrl,accessToken,onJoined}:{apiUrl:string;accessToken:string;onJoined:(w:BusinessWorkspace)=>void}){
 const account=useAuthenticatedResource<{user_id:string}>(apiUrl+'/api/v1/me',accessToken);
 const [token,setToken]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 async function accept(e:React.FormEvent){
  e.preventDefault();if(busy)return;setBusy(true);setError('');const controller=new AbortController();const timer=window.setTimeout(()=>controller.abort(),90000);
  try{const r=await fetch(apiUrl+'/api/v1/invitations/accept',{method:'POST',headers:{Authorization:`Bearer ${accessToken}`,'Content-Type':'application/json'},body:JSON.stringify({token:token.trim()}),signal:controller.signal});const data=await r.json();
   if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:'Check the invitation code and your account.');setToken('');onJoined(data.organization);
  }catch(e){setError(controller.signal.aborted?'Request timed out. Please retry.':e instanceof Error?e.message:'Could not accept invitation.');}finally{window.clearTimeout(timer);setBusy(false);}
 }
 async function copyAccount(){if(!account.data)return;try{await navigator.clipboard.writeText(account.data.user_id);setNotice('Account code copied. Share it with the administrator inviting you.');}catch{setNotice('Select and copy your account code below.');}}
 return <section className="panel ops-join"><h2>Join an invited business</h2><p>Share your account code with its administrator, then paste the private invitation code they give you.</p>{account.error&&<p className="error" role="alert">{account.error}</p>}{account.data&&<div className="ops-actions"><label className="ops-select">Your account code<input readOnly value={account.data.user_id}/></label><button className="workspace-secondary" onClick={()=>void copyAccount()}><Copy size={16}/>Copy my account code</button></div>}{notice&&<p role="status">{notice}</p>}
  <form className="ops-join-form" onSubmit={e=>void accept(e)}><label>Invitation code<input type="password" required minLength={40} maxLength={100} autoComplete="off" value={token} disabled={busy} onChange={e=>setToken(e.target.value)}/></label><button className="primary" disabled={busy}>{busy?'Joining…':'Accept invitation'}</button></form>{error&&<div className="error" role="alert">{error}</div>}
 </section>;
}
