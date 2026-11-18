import React,{useEffect,useState} from 'react';
import {ArrowLeft,ShieldCheck} from 'lucide-react';
import type {BusinessWorkspace} from './CustomerManagement';
type Dispute={id:string;invoice_id:string;status:string;reason:string;description:string;resolution_note:string|null};
type Audit={id:string;actor_id:string;action:string;resource_id:string;occurred_at:string};

export function DisputeManagement({apiUrl,accessToken,workspace,onBack}:{apiUrl:string;accessToken:string;workspace:BusinessWorkspace;onBack:()=>void}){
 const [disputes,setDisputes]=useState<Dispute[]>([]);
 const [events,setEvents]=useState<Audit[]>([]);
 const [invoices,setInvoices]=useState<{id:string;invoice_number:string}[]>([]);
 const [invoiceId,setInvoiceId]=useState('');const [reason,setReason]=useState('amount_mismatch');
 const [description,setDescription]=useState('');const [notes,setNotes]=useState<Record<string,string>>({});
 const [refresh,setRefresh]=useState(0);const [busy,setBusy]=useState(false);const [error,setError]=useState('');
 const base=`${apiUrl}/api/v1/organizations/${encodeURIComponent(workspace.id)}`;
 const canWrite=workspace.role!=='viewer';
 useEffect(()=>{const controller=new AbortController();let active=true;setError('');
  const timer=window.setTimeout(()=>controller.abort(),90000);
  async function load(){try{const responses=await Promise.all(['/disputes','/audit','/invoices'].map(p=>fetch(base+p,{headers:{Authorization:`Bearer ${accessToken}`},signal:controller.signal})));if(responses.some(r=>!r.ok))throw new Error('Could not load disputes and activity.');const [d,a,i]=await Promise.all(responses.map(r=>r.json()));if(active){setDisputes(d.disputes);setEvents(a.events);setInvoices(i.invoices);}}catch(e){if(active)setError(e instanceof Error?e.message:'Could not load activity.');}finally{window.clearTimeout(timer);}}
  void load();return()=>{active=false;window.clearTimeout(timer);controller.abort();};
 },[base,accessToken,refresh]);
 async function post(path:string,payload:unknown){
  if(!canWrite||busy)return;setBusy(true);setError('');
  try{const r=await fetch(base+path,{method:'POST',headers:{Authorization:`Bearer ${accessToken}`,'Content-Type':'application/json'},body:JSON.stringify(payload)});const body=await r.json();if(!r.ok)throw new Error(typeof body.detail==='string'?body.detail:'Could not update dispute.');setDescription('');setRefresh(v=>v+1);}catch(e){setError(e instanceof Error?e.message:'Update failed.');}finally{setBusy(false);}
 }
 return <div className="workspace-screen"><div className="workspace-top"><div className="workspace-brand"><ShieldCheck size={23}/>CashPilot</div><span className="eyebrow">{workspace.name}</span></div><main className="decision-content"><button className="workspace-back" onClick={onBack}><ArrowLeft size={16}/>Back to customers</button><h1>Disputes & activity</h1><p>Resolve invoice disagreements with a recorded, human-reviewed workflow.</p>{error&&<div className="error" role="alert">{error}<button onClick={()=>setRefresh(v=>v+1)}>Retry</button></div>}
 {canWrite&&<section className="panel" style={{marginTop:24}}><h2>Open an invoice dispute</h2><form className="lab-ledger-form" onSubmit={e=>{e.preventDefault();void post('/disputes',{invoice_id:invoiceId,reason,description});}}><label>Invoice<select required value={invoiceId} onChange={e=>setInvoiceId(e.target.value)}><option value="">Choose an invoice</option>{invoices.filter(i=>!disputes.some(d=>d.invoice_id===i.id)).map(i=><option key={i.id} value={i.id}>{i.invoice_number}</option>)}</select></label><label>Reason<select value={reason} onChange={e=>setReason(e.target.value)}>{['amount_mismatch','missing_document','quality','delivery','other'].map(r=><option key={r} value={r}>{r.replace(/_/g,' ')}</option>)}</select></label><label>Description<input required maxLength={2000} value={description} onChange={e=>setDescription(e.target.value)}/></label><button className="primary" disabled={busy||!invoiceId}>Open dispute</button></form></section>}
 <section className="panel"><h2>Dispute register</h2><p>Open disputes are excluded from baseline Decision Lab receipts until resolved.</p>{disputes.map(d=><article className="lab-risk" key={d.id}><div className="lab-risk-heading"><strong>{invoices.find(i=>i.id===d.invoice_id)?.invoice_number??'Invoice'}</strong><span className="lab-badge">{d.status.replace(/_/g,' ')}</span></div><p>{d.reason.replace(/_/g,' ')} · {d.description}</p>{d.resolution_note&&<p>Resolution: {d.resolution_note}</p>}{canWrite&&d.status==='open'&&<button className="workspace-secondary" disabled={busy} onClick={()=>void post(`/disputes/${d.id}/status`,{status:'under_review'})}>Start review</button>}{canWrite&&d.status==='under_review'&&<form className="lab-ledger-form" onSubmit={e=>{e.preventDefault();void post(`/disputes/${d.id}/status`,{status:'resolved',resolution_note:notes[d.id]});}}><label>Resolution note<input required maxLength={2000} value={notes[d.id]??''} onChange={e=>setNotes(n=>({...n,[d.id]:e.target.value}))}/></label><button className="primary" disabled={busy}>Resolve dispute</button></form>}</article>)}{!disputes.length&&<p className="workspace-empty">No invoice disputes.</p>}</section>
 <section className="panel"><h2>Recorded workspace activity</h2><p>Latest 100 events. Runtime database access cannot update or delete audit records.</p><div className="table-wrap"><table><thead><tr><th>WHEN</th><th>ACTION</th><th>ACTOR ID</th><th>RESOURCE ID</th></tr></thead><tbody>{events.map(e=><tr key={e.id}><td>{new Date(e.occurred_at).toLocaleString()}</td><td>{e.action}</td><td>{e.actor_id.slice(0,8)}…</td><td>{e.resource_id.slice(0,12)}…</td></tr>)}</tbody></table>{!events.length&&<p className="workspace-empty">New workspace writes will appear here.</p>}</div></section></main></div>;
}
