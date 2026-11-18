import React,{useEffect,useRef,useState} from 'react';
import {ArrowLeft,FileText,Plus,RefreshCw,X} from 'lucide-react';
import type {BusinessWorkspace} from './CustomerManagement';
import {scaled} from './operationsTypes';
import {useAuthenticatedResource} from './useAuthenticatedResource';

type Customer={id:string;name:string};
type Invoice={opening_receivable?:boolean;id:string;customer_id:string;invoice_number:string;due_date:string;total_paise:number;outstanding_paise?:number;effective_total_paise?:number};
type Summary={total_invoiced_paise:number;paid_paise:number;outstanding_paise:number;overdue_paise:number;invoice_count:number;adjusted_invoiced_paise?:number;customer_credit_paise?:number;refunded_paise?:number};
type Payment={id:string;amount_paise:number;created_at:string};
type CollectionAction={invoice_id:string;customer_name:string;outstanding_paise:number;overdue_days:number;action:string;reason:string;priority_score:number};
type CollectionPlan={method:string;disclaimer:string;actions:CollectionAction[]};
type Props={apiUrl:string;accessToken:string;workspace:BusinessWorkspace;onBack:()=>void};
const inr=(paise:number)=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR'}).format(paise/100);
export function InvoiceManagement({apiUrl,accessToken,workspace,onBack}:Props){
 const [invoices,setInvoices]=useState<Invoice[]>([]);
 const [customers,setCustomers]=useState<Customer[]>([]);
 const [summary,setSummary]=useState<Summary|null>(null);
 const [collectionPlan,setCollectionPlan]=useState<CollectionPlan|null>(null);
 const [showCollections,setShowCollections]=useState(false);
 const [paymentInvoice,setPaymentInvoice]=useState<Invoice|null>(null);
 const [paymentAmount,setPaymentAmount]=useState('');
 const [paymentRequestKey,setPaymentRequestKey]=useState(()=>crypto.randomUUID());
 const [paymentError,setPaymentError]=useState('');
 const [paymentRevision,setPaymentRevision]=useState(0);
 const paymentDialog=useRef<HTMLDialogElement>(null);
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
 const paymentHistory=useAuthenticatedResource<{payments:Payment[]}>(paymentInvoice?base+'/invoices/'+encodeURIComponent(paymentInvoice.id)+'/payments':null,accessToken,paymentRevision);
 useEffect(()=>{
  const dialog=paymentDialog.current;
  if(!dialog||!paymentInvoice)return;
  dialog.showModal();
  return()=>dialog.close();
 },[paymentInvoice]);
 async function load(signal?:AbortSignal){
  setLoading(true);setError('');
  try{
   const [a,b,c,d]=await Promise.all([
    fetch(base+'/invoices',{headers,signal}),
    fetch(base+'/customers',{headers,signal}),
    fetch(base+'/invoices/summary',{headers,signal}),
    fetch(base+'/collections/plan',{headers,signal})
   ]);
   if(!a.ok||!b.ok||!c.ok||!d.ok)throw new Error('Could not load invoices and customers.');
   const inv:{invoices:Invoice[]}=await a.json();
   const cus:{customers:Customer[]}=await b.json();
   const sum:Summary=await c.json();
   const plan:CollectionPlan=await d.json();
   if(!signal?.aborted){setInvoices(inv.invoices);setCustomers(cus.customers);setSummary(sum);setCollectionPlan(plan);}
  }catch(e){if(!signal?.aborted)setError(e instanceof Error?e.message:'Network error');}
  finally{if(!signal?.aborted)setLoading(false);}
 }
 useEffect(()=>{const controller=new AbortController();void load(controller.signal);return()=>controller.abort();},[base,accessToken]);
 async function submit(e:React.FormEvent){
  e.preventDefault();if(!canWrite||busy)return;
  let paise:number;
  try{paise=scaled(amount,2);}catch{setError('Enter a positive amount with up to two decimal places.');return;}
  if(paise<=0||paise>2_000_000_000){setError('Enter a positive amount up to ₹2 crore.');return;}
  setBusy(true);setError('');
  try{
   const response=await fetch(base+'/invoices',{method:'POST',headers:{...headers,'Content-Type':'application/json'},body:JSON.stringify({customer_id:customerId,invoice_number:number.trim(),due_date:dueDate,total_paise:paise})});
   if(!response.ok){const detail=await response.json().catch(()=>null);throw new Error(typeof detail?.detail==='string'?detail.detail:'Could not create invoice.');}
   await response.json();
   setShowForm(false);setNumber('');setAmount('');setDueDate('');await load();
  }catch(e){setError(e instanceof Error?e.message:'Could not create invoice.');}
  finally{setBusy(false);}
 }
 function openPayment(invoice:Invoice){
  setPaymentInvoice(invoice);setPaymentAmount('');setPaymentRequestKey(crypto.randomUUID());setPaymentError('');
 }
 async function submitPayment(e:React.FormEvent){
  e.preventDefault();if(!paymentInvoice||busy||!canWrite||!paymentHistory.data)return;
  let paise:number;
  try{paise=scaled(paymentAmount,2);}catch{setPaymentError('Enter a positive amount with up to two decimal places.');return;}
  const outstanding=paymentInvoice.outstanding_paise??(paymentInvoice.total_paise-paymentHistory.data.payments.reduce((sum,p)=>sum+p.amount_paise,0));
  if(paise<=0||paise>outstanding){setPaymentError('Payment must be positive and no more than the outstanding balance.');return;}
  setBusy(true);setPaymentError('');
  try{const response=await fetch(base+'/invoices/'+encodeURIComponent(paymentInvoice.id)+'/payments',{method:'POST',headers:{...headers,'Content-Type':'application/json'},body:JSON.stringify({amount_paise:paise,idempotency_key:paymentRequestKey}),signal:AbortSignal.timeout(90000)});if(!response.ok){const body=await response.json().catch(()=>null);throw new Error(typeof body?.detail==='string'?body.detail:'Could not save payment.');}setPaymentInvoice(null);await load();}catch(e){setPaymentError(e instanceof Error?e.message:'Could not save payment.');}finally{setBusy(false);}
 }
 const customerName=(id:string)=>customers.find(c=>c.id===id)?.name??'Customer';
 return <div className="workspace-screen">
  <div className="workspace-top"><div className="workspace-brand"><FileText size={23}/> CashPilot</div><span className="eyebrow">{workspace.name}</span></div>
  <div className="workspace-content"><button className="workspace-back" onClick={onBack}><ArrowLeft size={16}/>Back to overview</button>
   <div className="workspace-heading"><div><span className="eyebrow">INVOICE WORKSPACE</span><h1>Invoices</h1><p>Review issued invoices, opening receivables and recorded payments.</p></div>{canWrite&&<button className="primary" disabled={!customers.length} onClick={()=>{setCustomerId(customers[0]?.id??'');setShowForm(true);}}><Plus size={17}/>New invoice</button>}</div>
   {error&&<div className="error" role="alert">{error}<button aria-label="Retry" onClick={()=>void load()}><RefreshCw size={16}/></button></div>}
   {summary&&<div className="invoice-metrics"><div><span>Total invoiced</span><strong>{inr(summary.total_invoiced_paise)}</strong></div><div><span>Received</span><strong>{inr(summary.paid_paise)}</strong></div><div><span>Outstanding</span><strong>{inr(summary.outstanding_paise)}</strong></div><div><span>Overdue</span><strong>{inr(summary.overdue_paise)}</strong></div></div>}
   {collectionPlan&&collectionPlan.actions.length>0&&<section className="panel collections-panel"><div className="panel-heading"><div><h2>Collections priorities</h2><p>Suggested next steps for unpaid invoices · Human review required</p></div><button className="workspace-secondary" onClick={()=>setShowCollections(v=>!v)}>{showCollections?'Hide priorities':'View priorities'}</button></div>{showCollections&&<><div className="collection-list">{collectionPlan.actions.map(action=><div className="collection-row" key={action.invoice_id}><div><strong>{action.customer_name}</strong><p>{action.reason}</p></div><div className="collection-meta"><strong>{inr(action.outstanding_paise)}</strong><span>{action.action==='resolve_dispute'?'Resolve dispute':action.action==='review_followup'?'Review follow-up':action.action==='wait'?'Wait':'Monitor'}</span></div></div>)}</div><p className="collection-disclaimer">{collectionPlan.disclaimer}</p></>}</section>}
   {loading?<div className="workspace-empty">Loading invoices…</div>:invoices.length===0?<div className="workspace-empty">{customers.length?'No invoices yet. Create your first invoice.':'Add a customer before creating invoices.'}</div>:<section className="panel"><div className="table-wrap"><table><thead><tr><th>INVOICE</th><th>CUSTOMER</th><th>DUE DATE</th><th>AMOUNT</th><th>ACTIONS</th></tr></thead><tbody>{invoices.map(inv=><tr key={inv.id}><td>{inv.invoice_number}{inv.opening_receivable?' (opening balance)':''}</td><td>{customerName(inv.customer_id)}</td><td>{inv.due_date}</td><td>{inr(inv.total_paise)}</td><td><button className="workspace-secondary" onClick={()=>void openPayment(inv)}>Payments</button></td></tr>)}</tbody></table></div></section>}
  </div>
  {paymentInvoice&&<dialog className="receipt-dialog" ref={paymentDialog} aria-labelledby="receipt-dialog-title" onCancel={e=>{e.preventDefault();if(!busy)setPaymentInvoice(null);}}>
   <form className="dialog" onSubmit={submitPayment}>
    <div className="dialog-head"><h2 id="receipt-dialog-title">Invoice payments</h2><button autoFocus className="icon-button" type="button" aria-label="Close" disabled={busy} onClick={()=>setPaymentInvoice(null)}><X size={20}/></button></div>
    <p>{paymentInvoice.invoice_number} · {inr(paymentInvoice.outstanding_paise??paymentInvoice.total_paise)} outstanding</p>
    {paymentHistory.loading&&<p role="status">Loading payment history…</p>}
    {paymentHistory.error&&<div role="alert"><p>{paymentHistory.error}</p><button type="button" onClick={()=>setPaymentRevision(v=>v+1)}>Retry payment history</button></div>}
    {paymentHistory.data&&<div className="payment-history">{paymentHistory.data.payments.map(p=><div key={p.id}>{new Date(p.created_at).toLocaleDateString()} · {inr(p.amount_paise)}</div>)}{paymentHistory.data.payments.length===0&&<p>No payments recorded.</p>}</div>}
    {paymentError&&<p className="error" role="alert">{paymentError}</p>}
    {canWrite&&paymentHistory.data&&paymentInvoice.outstanding_paise!==0&&<><label>New payment (INR)<input required inputMode="decimal" value={paymentAmount} disabled={busy} onChange={e=>setPaymentAmount(e.target.value)}/></label><button disabled={busy} className="primary submit">{busy?'Saving…':'Record payment'}</button></>}
   </form>
  </dialog>}
  {showForm&&<div className="overlay" onMouseDown={e=>{if(e.target===e.currentTarget)setShowForm(false)}}><form className="dialog" onSubmit={submit}><div className="dialog-head"><h2>Create invoice</h2><button className="icon-button" type="button" aria-label="Close" onClick={()=>setShowForm(false)}><X size={20}/></button></div>
   <label>Customer<select required value={customerId} onChange={e=>setCustomerId(e.target.value)}>{customers.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
   <label>Invoice number<input required maxLength={64} value={number} onChange={e=>setNumber(e.target.value)}/></label>
   <label>Due date<input type="date" required value={dueDate} onChange={e=>setDueDate(e.target.value)}/></label>
   <label>Amount (INR)<input type="number" required min="0.01" step="0.01" value={amount} onChange={e=>setAmount(e.target.value)}/></label>
   <button className="primary submit" disabled={busy}>{busy?'Creating…':'Create invoice'}</button>
  </form></div>}
 </div>;
}
