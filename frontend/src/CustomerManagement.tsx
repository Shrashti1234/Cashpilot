import React, { useEffect, useState } from 'react';
import { ArrowLeft, FileText, Plus, RefreshCw, Users, X } from 'lucide-react';
import { languageNames, readLanguage, type Language } from './i18n';
import { InvoiceManagement } from './InvoiceManagement';

export type BusinessWorkspace = {id:string;name:string;mode:'micro'|'b2b';role:string};
type Customer = {id:string;name:string};
type Props = {apiUrl:string;accessToken:string;workspace:BusinessWorkspace;onBack:()=>void};
const labels = {
 en:{back:'Switch business',customers:'Customers',subtitle:'Manage customer records for this business.',add:'Add customer',name:'Customer name',save:'Save customer',cancel:'Cancel',empty:'No customers yet. Add your first customer.',loading:'Loading customers…',failed:'Could not load customers.',saveFailed:'Could not save customer.',retry:'Retry',readonly:'Your role has read-only access.'},
 hi:{back:'व्यवसाय बदलें',customers:'ग्राहक',subtitle:'इस व्यवसाय के ग्राहक प्रबंधित करें।',add:'ग्राहक जोड़ें',name:'ग्राहक का नाम',save:'ग्राहक सहेजें',cancel:'रद्द करें',empty:'अभी कोई ग्राहक नहीं है। पहला ग्राहक जोड़ें।',loading:'ग्राहक लोड हो रहे हैं…',failed:'ग्राहक लोड नहीं हो सके।',saveFailed:'ग्राहक सहेजा नहीं जा सका।',retry:'दोबारा कोशिश करें',readonly:'आपके पास केवल देखने की अनुमति है।'}
};
export function CustomerManagement({apiUrl,accessToken,workspace,onBack}:Props) {
 const [invoiceView,setInvoiceView] = useState(false);
 const [language,setLanguage] = useState<Language>(readLanguage);
 const t = labels[language==='hi'?'hi':'en'];
 const [customers,setCustomers] = useState<Customer[]>([]);
 const [loading,setLoading] = useState(true);
 const [error,setError] = useState('');
 const [showForm,setShowForm] = useState(false);
 const [name,setName] = useState('');
 const [busy,setBusy] = useState(false);
 const base = apiUrl+'/api/v1/organizations/'+encodeURIComponent(workspace.id)+'/customers';
 const canWrite = workspace.role !== 'viewer';
 useEffect(()=>{document.documentElement.lang=language;},[language]);
 async function load(signal?:AbortSignal) {
  setLoading(true);setError('');
  try {
   const response = await fetch(base,{headers:{Authorization:'Bearer '+accessToken},signal});
   if(!response.ok)throw new Error(t.failed);
   const data:{customers:Customer[]} = await response.json();
   if(!signal?.aborted)setCustomers(data.customers);
  }catch(e){if(!signal?.aborted)setError(e instanceof Error?e.message:t.failed);}
  finally{if(!signal?.aborted)setLoading(false);}
 }
 useEffect(()=>{const controller=new AbortController();void load(controller.signal);return()=>controller.abort();},[base,accessToken]);
 async function submit(event:React.FormEvent){
  event.preventDefault();if(!canWrite||!name.trim()||busy)return;
  setBusy(true);setError('');
  try{
   const response=await fetch(base,{method:'POST',headers:{Authorization:'Bearer '+accessToken,'Content-Type':'application/json'},body:JSON.stringify({name:name.trim()})});
   if(!response.ok)throw new Error(t.saveFailed);
   const created:Customer=await response.json();
   setCustomers(current=>[...current,created].sort((a,b)=>a.name.localeCompare(b.name)));
   setName('');setShowForm(false);
  }catch(e){setError(e instanceof Error?e.message:t.saveFailed);}
  finally{setBusy(false);}
 }
 if(invoiceView)return <InvoiceManagement apiUrl={apiUrl} accessToken={accessToken} workspace={workspace} onBack={()=>setInvoiceView(false)}/>;
 return <div className="workspace-screen">
  <div className="workspace-top"><div className="workspace-brand"><Users size={23}/> CashPilot</div><select aria-label="Language" value={language} onChange={e=>{const next=e.target.value as Language;setLanguage(next);try{localStorage.setItem('cashpilot-language',next)}catch{}}}>{(Object.keys(languageNames) as Language[]).map(code=><option key={code} value={code}>{languageNames[code]}</option>)}</select></div>
  <div className="workspace-content">
   <button className="workspace-back" onClick={onBack}><ArrowLeft size={16}/>{t.back}</button>
   <div className="workspace-heading"><div><span className="eyebrow">{workspace.name}</span><h1>{t.customers}</h1><p>{t.subtitle}</p></div><div className="workspace-actions"><button className="workspace-secondary" onClick={()=>setInvoiceView(true)}><FileText size={17}/>Invoices</button>{canWrite&&<button className="primary" onClick={()=>setShowForm(true)}><Plus size={17}/>{t.add}</button>}</div></div>
   {error&&<div className="error" role="alert">{error}<button onClick={()=>void load()} aria-label={t.retry}><RefreshCw size={17}/></button></div>}
   {loading?<div className="workspace-empty">{t.loading}</div>:customers.length===0?<div className="workspace-empty">{t.empty}</div>:<section className="panel"><div className="customer-list">{customers.map(customer=><div className="customer-row" key={customer.id}><span className="customer-avatar">{customer.name.charAt(0).toUpperCase()}</span><span>{customer.name}</span></div>)}</div></section>}
   {!canWrite&&<p>{t.readonly}</p>}
  </div>
  {showForm&&<div className="overlay" onMouseDown={e=>{if(e.target===e.currentTarget)setShowForm(false)}}><form className="dialog" onSubmit={submit}><div className="dialog-head"><h2>{t.add}</h2><button className="icon-button" type="button" aria-label={t.cancel} onClick={()=>setShowForm(false)}><X size={20}/></button></div><label>{t.name}<input required maxLength={160} value={name} onChange={e=>setName(e.target.value)}/></label><button disabled={busy} className="primary submit">{busy?'…':t.save}</button></form></div>}
 </div>;
}
