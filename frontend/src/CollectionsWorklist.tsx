import React,{useState} from 'react';
import type {BusinessWorkspace} from './CustomerManagement';
import {useAuthenticatedResource} from './useAuthenticatedResource';
import {money} from './operationsTypes';
import './buyer.css';

const labels:Record<string,string>={resolve_dispute:'Resolve dispute',review_followup:'Review follow-up',review_promise:'Review payment promise',wait:'Wait: recently contacted',monitor:'Monitor'};
type Task={assignee:string;follow_up:string;note:string;active:boolean};
type Row={invoice_id:string;reference:string;customer_name:string;outstanding_paise:number;action:string;reason:string;task:Task|null};
type Data={as_of:string;actions:Row[];members:string[];me:string;page:number;page_size:number;total:number};
export function CollectionsWorklist({apiUrl,accessToken,workspace,onBack}:{apiUrl:string;accessToken:string;workspace:BusinessWorkspace;onBack:()=>void}){
 const base=apiUrl+'/api/v1/organizations/'+encodeURIComponent(workspace.id)+'/collections/worklist';
 const [revision,setRevision]=useState(0),[filter,setFilter]=useState('all'),[selected,setSelected]=useState<Row|null>(null);
 const [page,setPage]=useState(1),[search,setSearch]=useState(''),[query,setQuery]=useState('');
 const [assignee,setAssignee]=useState(''),[date,setDate]=useState(''),[note,setNote]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const params=new URLSearchParams({view:filter,page:String(page),q:query});
 const resource=useAuthenticatedResource<Data>(base+'?'+params,accessToken,revision),data=resource.data,admin=['owner','admin'].includes(workspace.role);
 const rows=data?.actions??[];
 async function save(e:React.FormEvent){
  e.preventDefault();if(!selected||busy)return;setBusy(true);setError('');
  try{
   const response=await fetch(base+'/'+encodeURIComponent(selected.invoice_id),{method:'POST',headers:{Authorization:'Bearer '+accessToken,'Content-Type':'application/json'},body:JSON.stringify({assignee,follow_up:date,note}),signal:AbortSignal.timeout(90000)});
   if(!response.ok){const body=await response.json().catch(()=>null);throw new Error(typeof body?.detail==='string'?body.detail:'Could not save the follow-up.');}
   setSelected(null);setPage(1);setRevision(v=>v+1);
  }catch(e){setError(e instanceof Error?e.message:'Could not save.');}finally{setBusy(false);}
 }
 return <div className="workspace-screen"><main className="buyer-content">
  <button onClick={onBack}>Back to business</button><h1>Collections worklist</h1>
  <p>Open balances with follow-ups due come first. Assign ownership and a follow-up date. This screen does not send reminders or record payments.</p>
  <form onSubmit={e=>{e.preventDefault();setQuery(search.trim());setPage(1);setSelected(null);}}>
   <label>Search by invoice or customer<input value={search} maxLength={100} onChange={e=>setSearch(e.target.value)}/></label><button disabled={busy}>Search</button>
  </form>
  <label>Show<select aria-label="Filter worklist" disabled={busy} value={filter} onChange={e=>{setFilter(e.target.value);setPage(1);setSelected(null);}}><option value="all">All open balances</option><option value="mine">Assigned to me</option><option value="due">Follow-up due</option><option value="unassigned">Unassigned or needs reassignment</option></select></label>
  {(error||resource.error)&&<p role="alert" className="error">{error||resource.error}</p>}
  {resource.loading&&<p role="status">Loading worklist…</p>}
  {selected&&data&&<section className="panel"><h2>Follow up on {selected.reference}</h2><form onSubmit={e=>void save(e)}>
   <label>Team member<select aria-label="Team member" required value={assignee} onChange={e=>setAssignee(e.target.value)}>{(admin?data.members:[data.me]).map(id=><option value={id} key={id}>{id===data.me?'Me':id}</option>)}</select></label>
   <label>Follow-up date<input type="date" min={data.as_of} required value={date} onChange={e=>setDate(e.target.value)}/></label>
   <label>Internal note<textarea maxLength={500} value={note} onChange={e=>setNote(e.target.value)}/></label>
   <button disabled={busy}>Save follow-up</button><button type="button" disabled={busy} onClick={()=>setSelected(null)}>Cancel</button>
  </form></section>}
  {data&&!rows.length&&<p>No open balances in this view.</p>}
  {rows.map(r=><section className="panel" key={r.invoice_id}><h2>{r.reference} · {r.customer_name}</h2><strong>{money(r.outstanding_paise)} outstanding</strong>
   <p><strong>{labels[r.action]??r.action}</strong> — {r.reason}</p>
   <p>{r.task?('Follow-up '+r.task.follow_up+' · '+(r.task.active?(r.task.assignee===data?.me?'Assigned to me':r.task.assignee):'Needs reassignment')):'Unassigned'}</p>
   {r.task?.note&&<p>{r.task.note}</p>}
   {workspace.role!=='viewer'&&(admin||!r.task||r.task.assignee===data?.me)&&<button disabled={busy} onClick={()=>{if(!data)return;setSelected(r);setAssignee(r.task?.active?r.task.assignee:data.me);setDate(r.task&&r.task.follow_up>=data.as_of?r.task.follow_up:data.as_of);setNote(r.task?.note??'');setError('');}}>Edit follow-up</button>}
  </section>)}
  {data&&<nav aria-label="Worklist pages"><p>{data.total} matching open balances · Page {page} of {Math.max(1,Math.ceil(data.total/data.page_size))}</p>
   <button disabled={busy||page===1} onClick={()=>{setSelected(null);setPage(p=>p-1);}}>Previous page</button>
   <button disabled={busy||page*data.page_size>=data.total} onClick={()=>{setSelected(null);setPage(p=>p+1);}}>Next page</button>
  </nav>}
 </main></div>;
}
