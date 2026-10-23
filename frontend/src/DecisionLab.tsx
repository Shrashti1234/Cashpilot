import React,{useEffect,useState} from 'react';
import {ArrowLeft,ArrowUpRight,FlaskConical,RefreshCw,ShieldCheck,Upload} from 'lucide-react';
import type {BusinessWorkspace} from './CustomerManagement';
import {ModelEvidence,SimulationViews} from './IntelligenceViews';
import {inr,type Entry,type ModelReport,type ScenarioRequest,type Simulation} from './intelligenceTypes';
import './decision-lab.css';

const defaults:ScenarioRequest={opening_balance_paise:1500000,horizon_days:30,use_demo:true,receipt_overrides:[],expense_overrides:[]};
export function DecisionLab({apiUrl,accessToken,workspace,onBack}:{apiUrl:string;accessToken:string;workspace:BusinessWorkspace;onBack:()=>void}){
 const [request,setRequest]=useState(defaults);
 const [result,setResult]=useState<Simulation|null>(null);
 const [model,setModel]=useState<ModelReport|null>(null);
 const [entries,setEntries]=useState<Entry[]>([]);
 const [busy,setBusy]=useState(true);
 const [error,setError]=useState('');
 const [notice,setNotice]=useState('');
 const [balance,setBalance]=useState('15000');
 const [horizon,setHorizon]=useState(30);
 const [invoiceId,setInvoiceId]=useState('');
 const [receiptDate,setReceiptDate]=useState('');
 const [expenseId,setExpenseId]=useState('');
 const [expenseDate,setExpenseDate]=useState('');
 const [tab,setTab]=useState<'lab'|'history'|'models'>('lab');
 const [entryDate,setEntryDate]=useState(new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Kolkata'}).format(new Date()));
 const [entryAmount,setEntryAmount]=useState('');
 const [entryDirection,setEntryDirection]=useState('out');
 const [entryStatus,setEntryStatus]=useState('actual');
 const [entryDescription,setEntryDescription]=useState('');
 const [editingEntry,setEditingEntry]=useState('');
 const base=`${apiUrl}/api/v1/organizations/${encodeURIComponent(workspace.id)}`;
 const canWrite=workspace.role!=='viewer';

 useEffect(()=>{
  const controller=new AbortController(); let active=true;
  const timer=window.setTimeout(()=>controller.abort(),90000);
  setBusy(true);setError('');
  async function load(){
   try{
    const headers={Authorization:`Bearer ${accessToken}`};
    const responses=await Promise.all([
     fetch(base+'/decision-lab/simulate',{method:'POST',headers:{...headers,'Content-Type':'application/json'},body:JSON.stringify(request),signal:controller.signal}),
     fetch(base+'/intelligence/model',{headers,signal:controller.signal}),
     fetch(base+'/cash-entries',{headers,signal:controller.signal})]);
    for(const response of responses)if(!response.ok){const body=await response.json().catch(()=>null);throw new Error(typeof body?.detail==='string'?body.detail:'Could not load financial intelligence. Please retry.');}
    const [simulation,evidence,ledger]=await Promise.all(responses.map(r=>r.json()));
    if(active){setResult(simulation);setModel(evidence);setEntries(ledger.entries);}
   }catch(e){if(active)setError(controller.signal.aborted?'The backend is taking too long. Please retry.':e instanceof Error?e.message:'Could not load Decision Lab.');}
   finally{window.clearTimeout(timer);if(active)setBusy(false);}
  }
  void load();return()=>{active=false;window.clearTimeout(timer);controller.abort();};
 },[base,accessToken,request]);

 function recalculate(reset=false,demo=request.use_demo){
  const paise=Math.round(Number(balance)*100);
  if(!Number.isSafeInteger(paise)||Math.abs(paise)>1e12||!balance.trim()){setError('Enter a valid opening cash balance.');return;}
  if(!reset&&((invoiceId&&!receiptDate)||(expenseId&&!expenseDate))){setError('Choose a date for each scenario change.');return;}
  setRequest({opening_balance_paise:paise,horizon_days:horizon,use_demo:demo,
   receipt_overrides:!reset&&invoiceId?[{invoice_id:invoiceId,receipt_date:receiptDate}]:[],
   expense_overrides:!reset&&expenseId?[{entry_id:expenseId,expense_date:expenseDate}]:[]});
  if(reset){setInvoiceId('');setReceiptDate('');setExpenseId('');setExpenseDate('');}
 }
 async function write(path:string,body:unknown){
  const controller=new AbortController();const timer=window.setTimeout(()=>controller.abort(),90000);
  try{const r=await fetch(base+path,{method:'POST',headers:{Authorization:`Bearer ${accessToken}`,'Content-Type':'application/json'},body:JSON.stringify(body),signal:controller.signal});
   const data=await r.json();if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:'Invalid cash entry. Check the date, amount and description.');return data;
  }finally{window.clearTimeout(timer);}
 }
 async function saveEntry(e:React.FormEvent){
  e.preventDefault();if(busy||!canWrite)return;
  const amount=Math.round(Number(entryAmount)*100);if(!Number.isSafeInteger(amount)||amount<=0){setError('Enter a positive cash amount.');return;}
  setBusy(true);setError('');setNotice('');
  try{await write('/cash-entries'+(editingEntry?'/'+encodeURIComponent(editingEntry):''),{entry_date:entryDate,direction:entryDirection,status:entryStatus,amount_paise:amount,description:entryDescription});setEditingEntry('');setEntryAmount('');setEntryDescription('');setNotice('Cash entry saved.');setRequest(r=>({...r}));}
  catch(e){setError(e instanceof Error?e.message:'Could not save entry.');setBusy(false);}
 }
 async function importCsv(file?:File){
  if(!file||busy||!canWrite)return;if(file.size>300000){setError('CSV must be smaller than 300 KB.');return;}
  setBusy(true);setError('');setNotice('');
  try{const data=await write('/cash-entries/import',{csv_text:await file.text()});setNotice(`Imported ${data.imported} entries. ${data.note}`);setRequest(r=>({...r}));}
  catch(e){setError(e instanceof Error?e.message:'Import failed.');setBusy(false);}
 }

 return <div className="workspace-screen"><div className="workspace-top"><div className="workspace-brand"><FlaskConical size={24}/>CashPilot</div><span className="eyebrow">{workspace.name}</span></div><main className="decision-content">
  <button className="workspace-back" onClick={onBack}><ArrowLeft size={16}/>Back to customers</button>
  <div className="workspace-heading"><div><span className="eyebrow">SEE THE SHORTFALL BEFORE IT HAPPENS</span><h1>Decision Lab<span className="lab-dot">.</span></h1><p>Explore cash timing. Understand uncertainty. Review your next move.</p></div><span className="lab-badge"><ShieldCheck size={16}/>Read-only scenarios</span></div>
  <div className="lab-disclosure"><strong>Experimental · trained on synthetic data</strong><span>Unvalidated on real businesses. Scenario frequencies depend on assumptions; they are not promised outcomes or credit scores.</span></div>
  <nav className="lab-tabs" aria-label="Financial intelligence views">{(['lab','history','models'] as const).map(t=><button key={t} className={tab===t?'active':''} onClick={()=>setTab(t)}>{t==='lab'?'Scenarios':t==='history'?'Cash history':'Model evidence'}</button>)}</nav>
  {error&&<div className="error" role="alert">{error}<button aria-label="Retry Decision Lab" onClick={()=>setRequest(r=>({...r}))}><RefreshCw size={16}/></button></div>}{notice&&<p role="status" className="lab-notice">{notice}</p>}{busy&&<p className="lab-loading" role="status"><RefreshCw size={15}/>Computing financial intelligence…</p>}
  {tab==='lab'&&<><div className="lab-source"><div><strong>{request.use_demo?'Synthetic demo workspace':'Your workspace records'}</strong><p>{request.use_demo?'A labelled example. Demo records are never saved to your business.':'Uses your invoices, settled payments and operating cash entries.'}</p></div><button className="workspace-secondary" disabled={busy} onClick={()=>recalculate(true,!request.use_demo)}>{request.use_demo?'Use my business data':'Explore synthetic demo'}</button></div>
   <form className="lab-controls panel" onSubmit={e=>{e.preventDefault();recalculate();}}>
    <label>Opening available cash (INR)<input type="number" required step=".01" value={balance} disabled={busy} onChange={e=>setBalance(e.target.value)}/></label>
    <label>Forecast horizon<select disabled={busy} value={horizon} onChange={e=>setHorizon(Number(e.target.value))}>{[7,30,90].map(d=><option key={d} value={d}>{d} days</option>)}</select></label>
    <label>Assume an invoice is collected<select disabled={busy} value={invoiceId} onChange={e=>setInvoiceId(e.target.value)}><option value="">No receipt change</option>{result?.invoice_risks.map(r=><option key={r.invoice_id} value={r.invoice_id}>{r.customer_name} · {inr(r.outstanding_paise)}</option>)}</select></label>
    <label>Assumed receipt date<input type="date" min={result?.as_of} value={receiptDate} disabled={busy||!invoiceId} onChange={e=>setReceiptDate(e.target.value)}/></label>
    <label>Reschedule a planned outflow<select disabled={busy} value={expenseId} onChange={e=>setExpenseId(e.target.value)}><option value="">No expense change</option>{result?.planned_expenses.map(e=><option key={e.id} value={e.id}>{e.description} · {inr(e.amount_paise)}</option>)}</select></label>
    <label>Assumed expense date<input type="date" min={result?.as_of} value={expenseDate} disabled={busy||!expenseId} onChange={e=>setExpenseDate(e.target.value)}/></label>
    <div className="lab-control-actions"><button className="primary" disabled={busy}>Compare scenario<ArrowUpRight size={16}/></button><button type="button" className="workspace-secondary" disabled={busy} onClick={()=>recalculate(true)}>Reset changes</button></div>
    <p className="lab-control-note">Opening cash is your entered assumption. A planned outflow is that day's total operating expense and replaces the learned estimate. A simulation never records a payment or moves cash.</p>
   </form>{result&&<SimulationViews result={result} busy={busy} onTry={(id,date)=>{setInvoiceId(id);setReceiptDate(date);window.scrollTo({top:200,behavior:'smooth'});}}/>}</>}
  {tab==='history'&&<section className="panel"><h2>Operating cash history & plans</h2><p>Record expenses and non-invoice cash movements. Do not enter invoice receipts twice. Missing expense days are treated as zero.</p><p className="lab-caution">A planned outflow replaces that date's total learned operating expense estimate.</p>
   {canWrite&&<><form className="lab-ledger-form" onSubmit={e=>void saveEntry(e)}><label>Date<input type="date" required value={entryDate} onChange={e=>setEntryDate(e.target.value)}/></label><label>Direction<select value={entryDirection} onChange={e=>setEntryDirection(e.target.value)}><option value="out">Expense / outflow</option><option value="in">Other income / inflow</option></select></label><label>Record type<select value={entryStatus} onChange={e=>setEntryStatus(e.target.value)}><option value="actual">Actual</option><option value="planned">Planned</option><option value="void">Voided / excluded</option></select></label><label>Amount (INR)<input type="number" min=".01" step=".01" required value={entryAmount} onChange={e=>setEntryAmount(e.target.value)}/></label><label>Description<input required maxLength={160} value={entryDescription} onChange={e=>setEntryDescription(e.target.value)}/></label><button className="primary" disabled={busy}>{editingEntry?'Save entry changes':'Save cash entry'}</button>{editingEntry&&<button type="button" className="workspace-secondary" onClick={()=>{setEditingEntry('');setEntryDescription('');setEntryAmount('');}}>Cancel edit</button>}</form><div className="lab-csv"><Upload size={18}/><label>Import CSV<input aria-label="Import cash-history CSV" type="file" accept=".csv,text/csv" disabled={busy} onChange={e=>{void importCsv(e.target.files?.[0]);e.target.value='';}}/></label><p>Columns: date,direction,status,amount_inr,description. Maximum 1,000 rows. Imports append all rows; review duplicates first.</p></div></>}
   <div className="table-wrap"><table><thead><tr><th>DATE</th><th>DESCRIPTION</th><th>TYPE</th><th>AMOUNT</th><th></th></tr></thead><tbody>{entries.slice(0,100).map(e=><tr key={e.id}><td>{e.entry_date}</td><td>{e.description}</td><td>{e.status} · {e.direction}</td><td>{inr(e.amount_paise)}</td><td>{canWrite&&<button className="workspace-secondary" disabled={busy} onClick={()=>{setEditingEntry(e.id);setEntryDate(e.entry_date);setEntryAmount(String(e.amount_paise/100));setEntryDescription(e.description);setEntryDirection(e.direction);setEntryStatus(e.status);}}>Edit</button>}</td></tr>)}</tbody></table>{!entries.length&&<p className="workspace-empty">No cash entries yet. Demo data is separate and never saved here.</p>}</div></section>}
  {tab==='models'&&model&&<ModelEvidence model={model}/>}
 </main></div>;
}
