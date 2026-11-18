import React, {useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {ArrowLeft,ArrowRight,Check,CircleHelp,Download,FileUp,ListTodo,Receipt,Landmark,RefreshCw,ShieldCheck} from 'lucide-react';
import {ReceivableImport} from './ReceivableImport';
import {CollectionsWorklist} from './CollectionsWorklist';
import {InvoiceManagement} from './InvoiceManagement';
import {BankReconciliation} from './BankReconciliation';
import {download,money} from './operationsTypes';
import invoiceCsv from '../../examples/pilot/open-receivables.csv?raw';
import bankCsv from '../../examples/pilot/bank-statement.csv?raw';
import './style.css';
import './buyer.css';
import './practice.css';

const props = {apiUrl:'http://127.0.0.1:18081', accessToken:'cashpilot-disposable-demo',
 workspace:{id:'local-practice',name:'CashPilot practice',mode:'b2b' as const,role:'owner'}};
const sections = {import:ReceivableImport,collections:CollectionsWorklist,receipts:InvoiceManagement,bank:BankReconciliation};
type Section=keyof typeof sections;
type Snapshot={imported:boolean;follow_up:boolean;outstanding_paise:number|null;received_paise:number;matched_paise:number};
const steps=[
 {key:'import',title:'Import an invoice',action:'Open invoice import',detail:'Upload the sample CSV and confirm the ₹1,000 opening balance.',icon:FileUp,file:{name:'open-receivables.csv',text:invoiceCsv,label:'Invoice CSV'}},
 {key:'collections',title:'Assign a follow-up',action:'Open collections',detail:'Find PILOT-100 and assign its follow-up to yourself.',icon:ListTodo},
 {key:'receipts',title:'Record the receipt',action:'Open invoices',detail:'Open Payments for PILOT-100 and record the sample ₹1,000 receipt.',icon:Receipt},
 {key:'bank',title:'Match the bank transfer',action:'Open bank matching',detail:'Add an account alias, upload the bank CSV, and match the existing receipt.',icon:Landmark,file:{name:'bank-statement.csv',text:bankCsv,label:'Bank CSV'}},
] as const;

function Practice(){
 const [section,setSection]=useState<Section|null>(null);
 const [revision,setRevision]=useState(0);
 const [status,setStatus]=useState<{state:'loading'|'ready'|'offline';data?:Snapshot}>({state:'loading'});
 const main=useRef<HTMLDivElement>(null);
 useEffect(()=>{
  if(section)return;
  const controller=new AbortController();let active=true;
  const timeout=window.setTimeout(()=>controller.abort(),4500);
  setStatus({state:'loading'});
  fetch(props.apiUrl+'/practice/status',{headers:{Authorization:'Bearer '+props.accessToken},cache:'no-store',signal:controller.signal})
   .then(async r=>{if(!r.ok)throw new Error();return await r.json() as Snapshot;})
   .then(data=>{if(active)setStatus({state:'ready',data});})
   .catch(()=>{if(active)setStatus({state:'offline'});})
   .finally(()=>window.clearTimeout(timeout));
  return()=>{active=false;controller.abort();window.clearTimeout(timeout);};
 },[section,revision]);
 function open(next:Section|null){
  if(!next)setStatus({state:'loading'});
  setSection(next);window.scrollTo(0,0);
  requestAnimationFrame(()=>main.current?.focus());
 }
 const Screen=section?sections[section]:null;
 const data=status.data;
 const complete=[!!data?.imported,!!data?.follow_up,data?.outstanding_paise===0&&(data?.received_paise??0)>=100000,(data?.matched_paise??0)>=100000];
 const next=complete.indexOf(false);
 const current=steps.find(s=>s.key===section);
 return <div className="practice-shell">
  <header className="practice-top"><div className="practice-top-inner"><a href="/practice.html" className="practice-brand"><span className="practice-logo"><ShieldCheck size={21}/></span>CashPilot</a><span className="practice-tag">LOCAL PRACTICE</span></div></header>
  <div ref={main} tabIndex={-1} className="practice-focus" aria-label={current?.title??'Practice overview'}>
  {Screen?<><div className="practice-trail"><button className="practice-btn" onClick={()=>open(null)}><ArrowLeft size={16}/> Practice overview</button><span>{current?.title}</span></div><Screen {...props} onBack={()=>open(null)}/></>:<main className="practice-main">
   <section className="practice-hero">
    <div><span className="practice-kicker">GUIDED WORKSPACE / 01</span><h1>From invoice to<br/><em>bank match.</em></h1><p>Follow one ₹1,000 sample invoice through collections, receipt recording, and reconciliation.</p></div>
    <div className="practice-reference"><span>SAMPLE INVOICE</span><strong>PILOT-100</strong><small>Pilot Buyer · INR</small><span className="practice-rule"/><strong>{data?.outstanding_paise!=null?money(data.outstanding_paise):'—'}</strong><small>Outstanding in practice workspace</small></div>
   </section>
   <div className="practice-status"><p role="status"><span className={'practice-dot '+status.state}/>{status.state==='ready'?'Practice API connected':status.state==='loading'?'Checking practice API…':'Practice API unavailable'}</p><button className="practice-btn" disabled={status.state==='loading'} onClick={()=>{setStatus({state:'loading'});setRevision(v=>v+1);}}><RefreshCw size={15}/> {status.state==='offline'?'Retry connection':'Refresh status'}</button></div>
   {status.state==='offline'&&<p role="alert" className="practice-alert">Progress could not be checked. Start the local practice API with <code>python pilot_demo.py</code> from the backend folder, then retry. No completion status is shown while disconnected.</p>}
   <div className="practice-section-title"><div><span className="practice-kicker">WORKFLOW</span><h2>Four steps, one balance</h2></div><span>{data?complete.filter(Boolean).length+' of 4 complete':'Progress unavailable'}</span></div>
   <ol className="practice-steps">
    {steps.map((s,i)=>{const Icon=s.icon;return <li key={s.key} className={'practice-step '+(data&&next===i?'is-next':'')}>
     <div className="practice-step-top"><span className="practice-icon"><Icon size={20}/></span><span className={'practice-badge '+(data&&complete[i]?'is-done':'')}>{data?complete[i]?<><Check size={13}/> Complete</>:next===i?'Next step':'Pending':'Not checked'}</span></div>
     <h3><span>0{i+1} / </span>{s.title}</h3><p>{s.detail}</p>
     <div className="practice-actions"><button className="practice-btn" disabled={!data} onClick={()=>open(s.key)}>{s.action}<ArrowRight size={16}/></button>{'file' in s&&<button className="practice-btn practice-download" onClick={()=>download(s.file.name,s.file.text,'text/csv')}><Download size={15}/>{s.file.label}</button>}</div>
    </li>;})}
   </ol>
   <aside className="practice-note"><CircleHelp size={19}/><p><strong>Sample data only.</strong> No real money moves. Restarting the practice API starts a fresh workspace. Keep real customer and bank data out of this exercise.</p></aside>
  </main>}
  </div>
 </div>;
}

createRoot(document.getElementById('root')!).render(import.meta.env.DEV&&location.hostname==='127.0.0.1'
 ? <Practice/> : <p>Practice mode is available only on the local development server.</p>);
