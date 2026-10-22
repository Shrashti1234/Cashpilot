import React,{useEffect,useState} from 'react';
import {ArrowLeft,FileText,Plus,RefreshCw,X} from 'lucide-react';
import type {BusinessWorkspace} from './CustomerManagement';

type Customer={id:string;name:string};
type Invoice={id:string;customer_id:string;invoice_number:string;due_date:string;total_paise:number};
type Props={apiUrl:string;accessToken:string;workspace:BusinessWorkspace;onBack:()=>void};
const inr=(paise:number)=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR'}).format(paise/100);
export function InvoiceManagement({apiUrl,accessToken,workspace,onBack}:Props){
 const [invoices,setInvoices]=useState<Invoice[]>([]);
 const [customers,setCustomers]=useState<Customer[]>([]);
 const [loading,setLoading]=useState(true);
 const [error,setError]=useState('');
 const [showForm,setShowForm]=useState(false);
 const [busy,setBusy]=useState(false);
 const [customerId,setCustomerId]=useState('');
 const [number,setNumber]=useState('');
 const [dueDate,setDueDate]=useState('');
 const [amount,setAmount]=useState('');
 const base=apiUrl+'/api/v1/organizations/'+encodeURIComponent(workspace.id);
 const headers={Authorization:'Bearer '+accessToken};
 const canWrite=workspace.role!=='viewer';
 async function load(signal?:AbortSignal){
  setLoading(true);setError('');
  try{
   const [a,b]=await Promise.all([
    fetch(base+'/invoices',{headers,signal}),
    fetch(base+'/customers',{headers,signal})
   ]);
   if(!a.ok||!b.ok)throw new Error('Could not load invoices and customers.');
   const inv:{invoices:Invoice[]}=await a.json();
   const cus:{customers:Customer[]}=await b.json();
   if(!signal?.aborted){setInvoices(inv.invoices);setCustomers(cus.customers);}
  }catch(e){if(!signal?.aborted)setError(e instanceof Error?e.message:'Network error');}
  finally{if(!signal?.aborted)setLoading(false);}
 }
 useEffect(()=>{const controller=new AbortController();void load(controller.signal);return()=>controller.abort();},[base,accessToken]);
 async function submit(e:React.FormEvent){
  e.preventDefault();if(!canWrite||busy)return;
  const rupees=Number(amount);
  if(!Number.isFinite(rupees)||rupees<=0||!Number.isSafeInteger(Math.round(rupees*100))){setError('Enter a valid amount.');return;}
  setBusy(true);setError('');
  try{
   const response=await fetch(base+'/invoices',{method:'POST',headers:{...headers,'Content-Type':'application/json'},body:JSON.stringify({customer_id:customerId,invoice_number:number.trim(),due_date:dueDate,total_paise:Math.round(rupees*100)})});
   if(!response.ok){const detail=await response.json().catch(()=>null);throw new Error(typeof detail?.detail==='string'?detail.detail:'Could not create invoice.');}
   const created:Invoice=await response.json();
   setInvoices(current=>[...current,created]);setShowForm(false);setNumber('');setAmount('');setDueDate('');
  }catch(e){setError(e instanceof Error?e.message:'Could not create invoice.');}
  finally{setBusy(false);}
 }
 const customerName=(id:string)=>customers.find(c=>c.id===id)?.name??'Customer';
 return <div className="workspace-screen">
  <div className="workspace-top"><div className="workspace-brand"><FileText size={23}/> CashPilot</div><span className="eyebrow">{workspace.name}</span></div>
  <div className="workspace-content"><button className="workspace-back" onClick={onBack}><ArrowLeft size={16}/>Back to customers</button>
   <div className="workspace-heading"><div><span className="eyebrow">INVOICE WORKSPACE</span><h1>Invoices</h1><p>Track issued invoices for this business.</p></div>{canWrite&&<button className="primary" disabled={!customers.length} onClick={()=>{setCustomerId(customers[0]?.id??'');setShowForm(true);}}><Plus size={17}/>New invoice</button>}</div>
   {error&&<div className="error" role="alert">{error}<button aria-label="Retry" onClick={()=>void load()}><RefreshCw size={16}/></button></div>}
   {loading?<div className="workspace-empty">Loading invoices…</div>:invoices.length===0?<div className="workspace-empty">{customers.length?'No invoices yet. Create your first invoice.':'Add a customer before creating invoices.'}</div>:<section className="panel"><div className="table-wrap"><table><thead><tr><th>INVOICE</th><th>CUSTOMER</th><th>DUE DATE</th><th>AMOUNT</th></tr></thead><tbody>{invoices.map(inv=><tr key={inv.id}><td>{inv.invoice_number}</td><td>{customerName(inv.customer_id)}</td><td>{inv.due_date}</td><td>{inr(inv.total_paise)}</td></tr>)}</tbody></table></div></section>}
  </div>
  {showForm&&<div className="overlay" onMouseDown={e=>{if(e.target===e.currentTarget)setShowForm(false)}}><form className="dialog" onSubmit={submit}><div className="dialog-head"><h2>Create invoice</h2><button className="icon-button" type="button" aria-label="Close" onClick={()=>setShowForm(false)}><X size={20}/></button></div>
   <label>Customer<select required value={customerId} onChange={e=>setCustomerId(e.target.value)}>{customers.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
   <label>Invoice number<input required maxLength={64} value={number} onChange={e=>setNumber(e.target.value)}/></label>
   <label>Due date<input type="date" required value={dueDate} onChange={e=>setDueDate(e.target.value)}/></label>
   <label>Amount (INR)<input type="number" required min="0.01" step="0.01" value={amount} onChange={e=>setAmount(e.target.value)}/></label>
   <button className="primary submit" disabled={busy}>{busy?'Creating…':'Create invoice'}</button>
  </form></div>}
 </div>;
}
