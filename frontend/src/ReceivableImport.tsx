import React,{useState} from 'react';
import type {BusinessWorkspace} from './CustomerManagement';
import {download,money} from './operationsTypes';
import './buyer.css';

const fields={customer:'Customer name',reference:'Invoice reference',due:'Due date',amount:'Outstanding amount (INR)'};
type Columns=Record<keyof typeof fields,string>;
const empty:Columns={customer:'',reference:'',due:'',amount:''};
type Preview={rows:{row:number;customer?:string;reference?:string;due_date?:string;amount_paise?:number;status:string;errors:string[]}[];ready:number;duplicates:number;errors:number;ready_paise:number;preview_digest:string;blocked_by_approval:boolean};

export function ReceivableImport({apiUrl,accessToken,workspace,onBack}:{apiUrl:string;accessToken:string;workspace:BusinessWorkspace;onBack:()=>void}){
 const base=apiUrl+'/api/v1/organizations/'+encodeURIComponent(workspace.id)+'/receivable-import';
 const [content,setContent]=useState(''),[headers,setHeaders]=useState<string[]>([]),[columns,setColumns]=useState<Columns>(empty);
 const [preview,setPreview]=useState<Preview|null>(null),[error,setError]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false);
 async function post<T>(path:string,body:object):Promise<T>{
  const r=await fetch(base+path,{method:'POST',headers:{Authorization:'Bearer '+accessToken,'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(90000)});
  const result=await r.json().catch(()=>null);
  if(!r.ok)throw new Error(typeof result?.detail==='string'?result.detail:'Could not process the file. Check its size and format.');
  return result;
 }
 async function run(action:()=>Promise<void>){
  setBusy(true);setError('');setMessage('');
  try{await action();}catch(e){setError(e instanceof Error?e.message:'Import failed.');}finally{setBusy(false);}
 }
 return <div className="workspace-screen"><main className="buyer-content">
  <button onClick={onBack}>Back to business</button><h1>Import open invoices</h1>
  <p>Use a bill-wise Tally export saved as UTF-8 CSV, or a CSV from Excel. Include one row per open invoice with a unique reference. Map the pending amount, not the original invoice total. This adds opening receivables only.</p>
  <button onClick={()=>download('opening-receivables-template.csv','customer,reference,due,amount\r\n','text/csv')}>Download CSV template</button>
  {error&&<p className="error" role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
  <section className="panel"><label>Receivables CSV<input type="file" accept=".csv,text/csv" disabled={busy} onChange={e=>{
   const file=e.currentTarget.files?.[0];e.currentTarget.value='';if(!file)return;
   setContent('');setHeaders([]);setColumns(empty);setPreview(null);
   void run(async()=>{if(file.size>1_000_000)throw new Error('Choose a CSV under 1 MB.');const content=await file.text();const data=await post<{headers:string[]}>('/inspect',{content});setContent(content);setHeaders(data.headers);setColumns(Object.fromEntries(Object.keys(fields).map(k=>[k,data.headers.includes(k)?k:''])) as Columns);});
  }}/></label>
  {headers.length>0&&<form onSubmit={e=>{e.preventDefault();setPreview(null);void run(async()=>setPreview(await post<Preview>('/preview',{content,columns})));}}>
   {(Object.keys(fields) as (keyof Columns)[]).map(key=><label key={key}>{fields[key]}<select aria-label={fields[key]} required disabled={busy} value={columns[key]} onChange={e=>{setColumns({...columns,[key]:e.target.value});setPreview(null);}}><option value="">Choose a column</option>{headers.map(h=><option key={h}>{h}</option>)}</select></label>)}
   <button disabled={busy||Object.values(columns).some(v=>!v)}>Preview import</button>
  </form>}</section>
  {preview&&<section className="panel"><h2>Review opening receivables</h2>
   <p>{preview.ready} ready · {preview.duplicates} already imported · {preview.errors} need correction · {money(preview.ready_paise)} new outstanding</p>
   {preview.blocked_by_approval&&<p>Import is blocked because your business requires independent invoice approval.</p>}
   {preview.errors>0&&<button onClick={()=>download('receivables-errors.json',JSON.stringify(preview.rows.filter(r=>r.errors.length),null,2))}>Download row errors</button>}
   <div className="table-wrap" tabIndex={0} role="region" aria-label="Import preview"><table><thead><tr><th>Row</th><th>Customer / reference</th><th>Due</th><th>Outstanding</th><th>Result</th></tr></thead><tbody>{preview.rows.map(r=><tr key={r.row}><td>{r.row}</td><td>{r.customer} / {r.reference}</td><td>{r.due_date}</td><td>{r.amount_paise===undefined?'—':money(r.amount_paise)}</td><td>{r.errors.join(' ')||r.status}</td></tr>)}</tbody></table></div>
   <button disabled={busy||preview.blocked_by_approval||preview.errors>0||!preview.ready} onClick={()=>void run(async()=>{const data=await post<{imported:number;duplicates:number}>('/commit',{content,columns,preview_digest:preview.preview_digest});setPreview(null);setContent('');setHeaders([]);setMessage(`${data.imported} opening balances imported. ${data.duplicates} duplicates skipped.`);})}>Confirm import</button>
  </section>}
 </main></div>;
}
