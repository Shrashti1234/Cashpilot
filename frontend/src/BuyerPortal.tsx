import React,{useEffect,useState} from 'react';
import {money,scaled} from './operationsTypes';
import './operations.css';
import './buyer.css';

type PromiseRecord={id:string;amount_paise:number;promised_date:string;state:string};
type InvoiceView={invoice_number:string;due_date:string;adjusted_total_paise:number;net_received_paise:number;outstanding_paise:number;customer_credit_paise:number;seller:{legal_name:string;address:string;gstin:string};recipient_name:string;lines:{description:string;quantity_milliunits:number;total_paise:number}[];as_of:string;expires_at:string;permissions:{can_dispute:boolean;can_promise:boolean};dispute:{status:string;reason:string}|null;promises:PromiseRecord[]};
export function BuyerPortal({apiUrl,initialToken}:{apiUrl:string;initialToken:string}){
 const [data,setData]=useState<InvoiceView|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[revision,setRevision]=useState(0);
 const [amount,setAmount]=useState(''),[day,setDay]=useState(''),[note,setNote]=useState(''),[reason,setReason]=useState('amount_mismatch'),[description,setDescription]=useState('');
 const [requestKey,setRequestKey]=useState(()=>crypto.randomUUID());
 useEffect(()=>{history.replaceState(null,'',location.pathname+location.search);},[]);
 async function request(path:string,body:object,signal?:AbortSignal){
  const response=await fetch(apiUrl+'/api/v1/buyer/'+path,{method:'POST',credentials:'omit',cache:'no-store',headers:{'Content-Type':'application/json'},body:JSON.stringify({...body,token:initialToken}),signal:signal??AbortSignal.timeout(90000)});
  const result=await response.json().catch(()=>null);
  if(!response.ok){if(response.status===404)setData(null);throw new Error(typeof result?.detail==='string'?result.detail:'Could not complete this request. Please retry.');}return result;
 }
 useEffect(()=>{let active=true;const controller=new AbortController();const timeout=window.setTimeout(()=>controller.abort(),90000);setData(null);setError('');
  if(!initialToken){window.clearTimeout(timeout);setError('Open the complete private link supplied by the business.');return;}
  void request('inspect',{},controller.signal).then(result=>{if(active)setData(result);}).catch(e=>{if(active)setError(e instanceof Error?e.message:'Invoice unavailable.');}).finally(()=>window.clearTimeout(timeout));
  return()=>{active=false;controller.abort();window.clearTimeout(timeout);};
 },[apiUrl,initialToken,revision]);
 useEffect(()=>{if(!data)return;let timer:number;function check(){const remaining=Date.parse(data!.expires_at)-Date.now();if(remaining<=0){setData(null);setError('This private access has expired. Ask the business for a new link.');}else timer=window.setTimeout(check,Math.min(remaining,3600000));}check();return()=>window.clearTimeout(timer);},[data]);
 async function submit(e:React.FormEvent,kind:'promise'|'dispute'){
  e.preventDefault();if(busy)return;setBusy(true);setError('');
  try{await request(kind,kind==='promise'?{amount_paise:scaled(amount,2),promised_date:day,note,request_key:requestKey}:{reason,description});setRequestKey(crypto.randomUUID());setNote('');setDescription('');setRevision(v=>v+1);}
  catch(e){setError(e instanceof Error?e.message:'Could not save.');}finally{setBusy(false);}
 }
 const maxDay=data?new Date(Date.parse(data.as_of+'T00:00:00Z')+90*86400000).toISOString().slice(0,10):'';
 return <div className="workspace-screen"><main className="decision-content ops-content buyer-content"><span className="eyebrow">CASHPILOT · PRIVATE INVOICE</span><h1>{data?.invoice_number??'Your invoice'}</h1><p>Anyone with this link can access this invoice until the business revokes it or it expires. Keep it private.</p><button disabled={busy} onClick={()=>setRevision(v=>v+1)}>Refresh invoice</button>{error&&<p role="alert" className="error">{error}</p>}{!data&&!error&&<p role="status">Loading private invoice…</p>}
 {data&&<><section className="panel"><h2>{data.seller.legal_name}</h2><p>{data.seller.address}</p>{data.seller.gstin&&<p>GSTIN: {data.seller.gstin}</p>}<p>For {data.recipient_name} · Due {data.due_date} · As of {data.as_of}</p><div className="lab-metrics"><div><span>Adjusted total</span><strong>{money(data.adjusted_total_paise)}</strong></div><div><span>Net recorded receipts</span><strong>{money(data.net_received_paise)}</strong></div><div><span>Outstanding</span><strong>{money(data.outstanding_paise)}</strong></div><div><span>Customer credit</span><strong>{money(data.customer_credit_paise)}</strong></div></div><div className="table-wrap"><table><thead><tr><th>Description</th><th>Quantity</th><th>Total</th></tr></thead><tbody>{data.lines.map((line,i)=><tr key={i}><td>{line.description}</td><td>{line.quantity_milliunits/1000}</td><td>{money(line.total_paise)}</td></tr>)}</tbody></table></div><p>Online payments are not connected. Contact the business using your existing contact details to arrange payment. A promise below does not record a payment.</p></section>
 <section className="panel"><h2>Payment commitments</h2>{data.promises.map(p=><p key={p.id}>{money(p.amount_paise)} by {p.promised_date} · {p.state}</p>)}{!data.promises.length&&<p>No payment commitments recorded.</p>}{data.permissions.can_promise&&data.outstanding_paise>0&&<form onSubmit={e=>void submit(e,'promise')}><label>Amount (INR)<input required inputMode="decimal" value={amount} onChange={e=>setAmount(e.target.value)}/></label><label>Promised date<input required type="date" min={data.as_of} max={maxDay} value={day} onChange={e=>setDay(e.target.value)}/></label><label>Note to the business<textarea maxLength={1000} value={note} onChange={e=>setNote(e.target.value)}/></label><button disabled={busy}>Record payment promise</button></form>}</section>
 <section className="panel"><h2>Invoice issue</h2>{data.dispute?<p>{data.dispute.reason.replace(/_/g,' ')} · {data.dispute.status}. Contact the business to add information.</p>:data.permissions.can_dispute?<form onSubmit={e=>void submit(e,'dispute')}><label>Reason<select value={reason} onChange={e=>setReason(e.target.value)}>{['amount_mismatch','missing_document','quality','delivery','other'].map(r=><option key={r} value={r}>{r.replace(/_/g,' ')}</option>)}</select></label><label>Describe the issue<textarea required maxLength={2000} value={description} onChange={e=>setDescription(e.target.value)}/></label><button disabled={busy}>Raise invoice issue</button></form>:<p>This link allows viewing only.</p>}</section><p>Access expires {new Date(data.expires_at).toLocaleString()}. Refresh to check updated balances and access.</p></>}
 </main></div>;
}
