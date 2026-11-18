import React,{useState} from 'react';
import {ArrowLeft,Copy,Users} from 'lucide-react';
import type {BusinessWorkspace} from './CustomerManagement';
import {useAuthenticatedResource} from './useAuthenticatedResource';
import './operations.css';

type Member={user_id:string;role:string;active:boolean};
type Invitation={id:string;target_user_id:string;role:string;expires_at:string;used:boolean;revoked:boolean;created_by:string};
type Team={actor_id:string;actor_role:string;members:Member[];invitations:Invitation[]};
type Props={apiUrl:string;accessToken:string;workspace:BusinessWorkspace;onBack:()=>void;onOwnAccessChanged:()=>void};

function MemberEditor({member,owner,busy,onSave}:{member:Member;owner:boolean;busy:boolean;onSave:(m:Member)=>void}){
 const [role,setRole]=useState(member.role),[active,setActive]=useState(member.active);
 const allowed=owner||!['owner','admin'].includes(member.role);
 return <form className="ops-member" onSubmit={e=>{e.preventDefault();onSave({...member,role,active});}}><div><strong>{member.user_id}</strong><p>{member.active?'Active member':'Access deactivated'}</p></div>{allowed?<><label>Role for {member.user_id}<select disabled={busy} value={role} onChange={e=>setRole(e.target.value)}>{(owner?['owner','admin','accountant','viewer']:['accountant','viewer']).map(r=><option key={r} value={r}>{r}</option>)}</select></label><label className="ops-checkbox"><input disabled={busy} type="checkbox" checked={active} onChange={e=>setActive(e.target.checked)}/>Active access for {member.user_id}</label><button className="workspace-secondary" disabled={busy}>Save access for {member.user_id}</button></>:<span className="lab-badge">{member.role} · owner-managed</span>}</form>;
}

export function TeamSettings({apiUrl,accessToken,workspace,onBack,onOwnAccessChanged}:Props){
 const [revision,setRevision]=useState(0),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const [target,setTarget]=useState(''),[role,setRole]=useState('viewer');
 const [privateInvite,setPrivateInvite]=useState<{token:string;target_user_id:string;expires_at:string}|null>(null);
 const base=`${apiUrl}/api/v1/organizations/${encodeURIComponent(workspace.id)}/team`;
 const team=useAuthenticatedResource<Team>(base,accessToken,revision);
 const owner=team.data?.actor_role==='owner',disabled=busy||team.loading;
 async function post(path:string,payload:unknown,onSaved?:(value:Record<string,unknown>)=>void){
  if(disabled)return;setBusy(true);setError('');setNotice('');const controller=new AbortController();const timer=window.setTimeout(()=>controller.abort(),90000);
  try{const r=await fetch(base+path,{method:'POST',headers:{Authorization:`Bearer ${accessToken}`,'Content-Type':'application/json'},body:JSON.stringify(payload),signal:controller.signal});
   const data=await r.json();if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:'Check the account, role and permissions.');onSaved?.(data);setNotice('Team access saved.');setRevision(v=>v+1);
  }catch(e){setError(controller.signal.aborted?'Request timed out. Reload the team before retrying.':e instanceof Error?e.message:'Could not update access.');}
  finally{window.clearTimeout(timer);setBusy(false);}
 }
 async function copyInvite(){if(!privateInvite)return;try{await navigator.clipboard.writeText(privateInvite.token);setNotice('Private invitation code copied. Share it only with the intended account.');}catch{setNotice('Clipboard access is unavailable. Select and copy the private code.');}}
 return <div className="workspace-screen"><div className="workspace-top"><div className="workspace-brand"><Users size={24}/>CashPilot</div><span className="eyebrow">{workspace.name}</span></div><main className="decision-content ops-content"><button className="workspace-back" onClick={onBack}><ArrowLeft size={16}/>Back to customers</button><h1>Team & access</h1><p>Invite verified accounts, assign roles and revoke business access.</p>
  {(error||team.error)&&<div role="alert" className="error">{error||team.error}<button onClick={()=>{setError('');setRevision(v=>v+1);}}>Reload</button></div>}{notice&&<p className="lab-notice" role="status">{notice}</p>}{team.loading&&<p role="status" className="lab-loading">Loading team access…</p>}
  {team.data&&<fieldset disabled={disabled} className="ops-fieldset"><section className="panel" style={{marginTop:24}}><h2>Invite an account</h2><p>Ask the recipient for their account code from Your businesses. Invitations are private, bound to that account and expire in seven days. Share the code directly; no message is sent automatically.</p><form className="lab-ledger-form" onSubmit={e=>{e.preventDefault();setPrivateInvite(null);void post('/invitations',{target_user_id:target.trim(),role},data=>{if(typeof data.token==='string'&&typeof data.target_user_id==='string'&&typeof data.expires_at==='string')setPrivateInvite({token:data.token,target_user_id:data.target_user_id,expires_at:data.expires_at});setTarget('');});}}><label>Recipient account code<input required maxLength={200} value={target} autoComplete="off" onChange={e=>setTarget(e.target.value)}/></label><label>Invitation role<select value={role} onChange={e=>setRole(e.target.value)}>{(owner?['admin','accountant','viewer']:['accountant','viewer']).map(r=><option key={r} value={r}>{r}</option>)}</select></label><button className="primary">Create private invitation</button></form>
   {privateInvite&&<div className="ops-private"><strong>Invitation for {privateInvite.target_user_id}</strong><p>Copy now; the server stores only its hash. Expires {new Date(privateInvite.expires_at).toLocaleString()}.</p><label className="ops-select">Private invitation code<input type="password" readOnly autoComplete="off" value={privateInvite.token}/></label><div className="ops-actions"><button className="workspace-secondary" onClick={()=>void copyInvite()}><Copy size={16}/>Copy private invitation</button><button className="workspace-secondary" onClick={()=>setPrivateInvite(null)}>Hide private code</button></div></div>}
  </section><section className="panel"><h2>Business members</h2><p>Owners manage all roles. Administrators manage accountants and viewers. The last active owner is protected. Deactivation blocks future business API requests, including existing signed-in sessions.</p>{team.data.members.map(m=><MemberEditor key={`${m.user_id}:${m.role}:${m.active}`} member={m} owner={owner} busy={disabled} onSave={updated=>void post('/member',updated,()=>{if(updated.user_id===team.data?.actor_id)onOwnAccessChanged();})}/>)}</section>
   <section className="panel"><h2>Latest 100 invitations</h2><div className="table-wrap" tabIndex={0} role="region" aria-label="Team invitations"><table><thead><tr><th>ACCOUNT</th><th>ROLE</th><th>EXPIRES</th><th>STATUS</th><th></th></tr></thead><tbody>{team.data.invitations.map(i=>{const status=i.revoked?'Revoked':i.used?'Accepted':Date.parse(i.expires_at)<=Date.now()?'Expired':'Pending';return <tr key={i.id}><td>{i.target_user_id}</td><td>{i.role}</td><td>{new Date(i.expires_at).toLocaleDateString()}</td><td>{status}</td><td>{status==='Pending'&&(owner||i.role!=='admin')&&<button className="workspace-secondary" onClick={()=>void post('/invitations/'+i.id+'/revoke',{})}>Revoke invitation for {i.target_user_id}</button>}</td></tr>;})}</tbody></table>{!team.data.invitations.length&&<p className="workspace-empty">No invitations yet.</p>}</div></section>
  </fieldset>}
 </main></div>;
}
