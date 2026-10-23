import React, { useEffect, useState } from 'react';
import { Building2, Plus, RefreshCw, ShieldCheck, X } from 'lucide-react';
import { languageNames, readLanguage, type Language } from './i18n';

type Workspace = { id:string; name:string; mode:'micro'|'b2b'; role:string };
type Props = { apiUrl:string; accessToken:string; onSelect:(workspace:Workspace)=>void };
const labels = {
 en:{title:'Your businesses',sub:'Select a business workspace or create a new one.',create:'Create business',name:'Business name',mode:'Business type',micro:'Micro business',b2b:'B2B business',save:'Create workspace',cancel:'Cancel',empty:'No businesses yet.',loading:'Loading workspaces…',retry:'Try again',security:'Only businesses you belong to are shown.',failed:'Could not load your businesses.',saveFailed:'Could not create business.'},
 hi:{title:'आपके व्यवसाय',sub:'व्यवसाय चुनें या नया कार्यस्थल बनाएँ।',create:'व्यवसाय बनाएँ',name:'व्यवसाय का नाम',mode:'व्यवसाय का प्रकार',micro:'छोटा व्यवसाय',b2b:'बी2बी व्यवसाय',save:'कार्यस्थल बनाएँ',cancel:'रद्द करें',empty:'अभी कोई व्यवसाय नहीं है।',loading:'व्यवसाय लोड हो रहे हैं…',retry:'दोबारा कोशिश करें',security:'केवल आपके व्यवसाय दिखाए जाते हैं।',failed:'व्यवसाय लोड नहीं हो सके।',saveFailed:'व्यवसाय नहीं बन सका।'}
};
export function WorkspaceOnboarding({apiUrl,accessToken,onSelect}:Props) {
 const [language,setLanguage] = useState<Language>(readLanguage);
 const [workspaces,setWorkspaces] = useState<Workspace[]>([]);
 const [loading,setLoading] = useState(true);
 const [error,setError] = useState('');
 const [creating,setCreating] = useState(false);
 const [busy,setBusy] = useState(false);
 const [name,setName] = useState('');
 const [mode,setMode] = useState<'micro'|'b2b'>('micro');
 const t = labels[language==='hi'?'hi':'en'];
 useEffect(()=>{document.documentElement.lang=language;},[language]);
 async function load(signal?:AbortSignal) {
  setLoading(true);setError('');
  try {
   const response = await fetch(apiUrl+'/api/v1/organizations',{headers:{Authorization:'Bearer '+accessToken},signal});
   if (!response.ok) throw new Error(t.failed);
   const data: {organizations:Workspace[]} = await response.json();
   if (!signal?.aborted) setWorkspaces(data.organizations);
  } catch(e) { if(!signal?.aborted) setError(e instanceof Error?e.message:t.failed); }
  finally { if(!signal?.aborted) setLoading(false); }
 }
 useEffect(()=>{const controller=new AbortController();void load(controller.signal);return()=>controller.abort();},[apiUrl,accessToken]);
 async function submit(event:React.FormEvent) {
  event.preventDefault();if(!name.trim()||busy)return;
  setBusy(true);setError('');
  try {
   const response=await fetch(apiUrl+'/api/v1/organizations',{
    method:'POST',headers:{Authorization:'Bearer '+accessToken,'Content-Type':'application/json'},
    body:JSON.stringify({name:name.trim(),mode})
   });
   if(!response.ok)throw new Error(t.saveFailed);
   const created:Workspace=await response.json();
   setWorkspaces(current=>[...current,created]);setCreating(false);setName('');
   onSelect(created);
  } catch(e) {setError(e instanceof Error?e.message:t.saveFailed);}
  finally {setBusy(false);}
 }
 return <div className="workspace-screen">
  <div className="workspace-top"><div className="workspace-brand"><Building2 size={23}/> CashPilot</div><select aria-label="Language" value={language} onChange={e=>{const value=e.target.value as Language;setLanguage(value);try{localStorage.setItem('cashpilot-language',value);}catch{}}}>{(Object.keys(languageNames) as Language[]).map(code=><option value={code} key={code}>{languageNames[code]}</option>)}</select></div>
  <div className="workspace-content"><div className="workspace-heading"><div><span className="eyebrow">BUSINESS WORKSPACES</span><h1>{t.title}</h1><p>{t.sub}</p></div><button className="primary" onClick={()=>setCreating(true)}><Plus size={17}/>{t.create}</button></div>
  {error&&<div className="error" role="alert">{error}<button onClick={()=>void load()} aria-label={t.retry}><RefreshCw size={17}/></button></div>}
  {loading?<div className="workspace-empty">{t.loading}</div>:workspaces.length===0?<div className="workspace-empty">{t.empty}</div>:<div className="workspace-grid">{workspaces.map(workspace=><button className="workspace-card" key={workspace.id} onClick={()=>onSelect(workspace)}><span className="workspace-card-icon"><Building2 size={22}/></span><strong>{workspace.name}</strong><small>{workspace.mode==='micro'?t.micro:t.b2b} · {workspace.role}</small></button>)}</div>}
  <p className="workspace-security"><ShieldCheck size={15}/>{t.security}</p></div>
  {creating&&<div className="overlay" onMouseDown={e=>{if(e.target===e.currentTarget)setCreating(false)}}><form className="dialog" onSubmit={submit}><div className="dialog-head"><h2>{t.create}</h2><button type="button" className="icon-button" onClick={()=>setCreating(false)} aria-label={t.cancel}><X size={20}/></button></div><label>{t.name}<input autoFocus required minLength={1} maxLength={160} value={name} onChange={e=>setName(e.target.value)}/></label><label>{t.mode}<select value={mode} onChange={e=>setMode(e.target.value as 'micro'|'b2b')}><option value="micro">{t.micro}</option><option value="b2b">{t.b2b}</option></select></label><button disabled={busy} className="primary submit">{busy?'…':t.save}</button></form></div>}
 </div>;
}
