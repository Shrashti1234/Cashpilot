import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { AreaChart, Area, ResponsiveContainer, Tooltip, XAxis, CartesianGrid } from 'recharts';
import { Activity, ArrowDownLeft, ArrowUpRight, Plus, RefreshCw, Wallet, X } from 'lucide-react';
import './style.css';

type Tx = { id: string; title: string; amount: string; kind: 'income' | 'expense'; category: string; created_at: string };
type Summary = { income: string; expenses: string; balance: string; count: number };
const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const money = (v: string | number) => new Intl.NumberFormat('en-IN', {style:'currency',currency:'INR',maximumFractionDigits:0}).format(Number(v));
function App() {
 const [items,setItems] = useState<Tx[]>([]);
 const [summary,setSummary] = useState<Summary>({income:'0',expenses:'0',balance:'0',count:0});
 const [connected,setConnected] = useState(false);
 const [modal,setModal] = useState(false);
 const [filter,setFilter] = useState('all');
 const [query,setQuery] = useState('');
 const [title,setTitle] = useState('');
 const [amount,setAmount] = useState('');
 const [kind,setKind] = useState<'income'|'expense'>('expense');
 const [category,setCategory] = useState('Operations');
 const [busy,setBusy] = useState(false);
 const [error,setError] = useState('');
 async function refresh() {
  try { const r=await fetch(API+'/transactions'); if(!r.ok) throw new Error('API unavailable'); const d=await r.json();setItems(d.transactions);setSummary(d.summary);setError('');}
  catch {setError('Backend is unavailable. Start FastAPI on port 8000.');}
 }
 useEffect(()=>{
  let ws:WebSocket|null=null, timer:number, stopped=false;
  const connect=()=>{
   ws=new WebSocket(API.replace(/^http/,'ws')+'/ws');
   ws.onopen=()=>{setConnected(true);refresh();};
   ws.onmessage=(e)=>{const event=JSON.parse(e.data);if(event.type==='transaction.created')refresh();};
   ws.onclose=()=>{setConnected(false);if(!stopped)timer=window.setTimeout(connect,2500);};
   ws.onerror=()=>ws?.close();
  };
  refresh();connect();
  return ()=>{stopped=true;window.clearTimeout(timer);ws?.close();};
 },[]);
 const visible=items.filter(t=>(filter==='all'||t.kind===filter)&&t.title.toLowerCase().includes(query.toLowerCase()));
 const chart=items.slice().reverse().reduce<{label:string,balance:number}[]>((a,t)=>{const previous=a.length?a[a.length-1].balance:0;return [...a,{label:new Date(t.created_at).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}),balance:previous+(t.kind==='income'?1:-1)*Number(t.amount)}]},[]);
 async function submit(e:React.FormEvent){
  e.preventDefault();setBusy(true);
  try {const r=await fetch(API+'/transactions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title,amount:Number(amount),kind,category})});if(!r.ok)throw new Error('Could not save transaction');await refresh();setModal(false);setTitle('');setAmount('');setError('');}
  catch(err){setError(err instanceof Error?err.message:'Something went wrong');}
  finally{setBusy(false);}
 }
 return <div className="app"><aside className="sidebar"><div className="brand"><span className="brand-icon"><Activity size={23}/></span> CashPilot<span className="brand-dot">.</span></div><div className="side-label">WORKSPACE</div><div className="nav active"><Wallet size={18}/> Overview</div><div className="nav"><Activity size={18}/> Transactions</div><div className="side-footer">MVP 0.1 · Demo environment</div></aside><main className="main"><header><div><div className="eyebrow">FINANCIAL WORKSPACE</div><h1>Financial overview</h1><p>Track every movement. Stay ahead of your cash flow.</p></div><div className="header-actions"><span className={'status '+(connected?'online':'offline')}><span className="status-dot"/>{connected?'Live sync':'Reconnecting'}</span><button className="primary" onClick={()=>setModal(true)}><Plus size={17}/> Add transaction</button></div></header>{error&&<div className="error">{error}<button onClick={refresh}><RefreshCw size={16}/></button></div>}<section className="stats"><div className="stat"><span>Total balance</span><strong>{money(summary.balance)}</strong><small>Net cash position</small></div><div className="stat"><span>Income</span><strong className="green">{money(summary.income)}</strong><small><ArrowUpRight size={14}/> Recorded inflows</small></div><div className="stat"><span>Expenses</span><strong>{money(summary.expenses)}</strong><small><ArrowDownLeft size={14}/> Recorded outflows</small></div></section><section className="panel chart-panel"><div className="panel-heading"><div><h2>Cash flow activity</h2><p>Balance after each transaction</p></div><span className="chip">Live</span></div><div className="chart">{chart.length?<ResponsiveContainer width="100%" height="100%"><AreaChart data={chart}><defs><linearGradient id="fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#36d5ac" stopOpacity={.3}/><stop offset="100%" stopColor="#36d5ac" stopOpacity={0}/></linearGradient></defs><CartesianGrid stroke="#27344b" vertical={false}/><XAxis dataKey="label" stroke="#8894a9" tickLine={false}/><Tooltip contentStyle={{background:'#182439',border:'1px solid #34435b',borderRadius:12}} formatter={(v)=>money(Number(v))}/><Area type="monotone" dataKey="balance" stroke="#36d5ac" fill="url(#fill)" strokeWidth={3}/></AreaChart></ResponsiveContainer>:<div className="empty">Add your first transaction to see the cash-flow chart.</div>}</div></section><section className="panel"><div className="panel-heading"><div><h2>Recent transactions</h2><p>{summary.count} transactions recorded</p></div><div className="filters"><input aria-label="Search transactions" placeholder="Search transactions..." value={query} onChange={e=>setQuery(e.target.value)}/><select aria-label="Filter transaction type" value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">All types</option><option value="income">Income</option><option value="expense">Expenses</option></select></div></div><div className="table-wrap"><table><thead><tr><th>TRANSACTION</th><th>CATEGORY</th><th>DATE</th><th>AMOUNT</th></tr></thead><tbody>{visible.map(t=><tr key={t.id}><td><span className={'tx-icon '+t.kind}>{t.kind==='income'?<ArrowDownLeft size={17}/>:<ArrowUpRight size={17}/>}</span>{t.title}</td><td>{t.category}</td><td>{new Date(t.created_at).toLocaleString()}</td><td className={t.kind==='income'?'green':''}>{t.kind==='income'?'+':'−'}{money(t.amount)}</td></tr>)}</tbody></table>{!visible.length&&<div className="empty">No matching transactions yet.</div>}</div></section></main>{modal&&<div className="overlay" onMouseDown={e=>{if(e.target===e.currentTarget)setModal(false)}}><form className="dialog" onSubmit={submit}><div className="dialog-head"><h2>New transaction</h2><button type="button" className="icon-button" onClick={()=>setModal(false)}><X size={20}/></button></div><label>Description<input required maxLength={100} placeholder="e.g. Client payment" value={title} onChange={e=>setTitle(e.target.value)}/></label><label>Amount (INR)<input required type="number" min="0.01" step="0.01" value={amount} onChange={e=>setAmount(e.target.value)} placeholder="0.00"/></label><label>Type<select value={kind} onChange={e=>setKind(e.target.value as 'income'|'expense')}><option value="expense">Expense</option><option value="income">Income</option></select></label><label>Category<input required value={category} onChange={e=>setCategory(e.target.value)}/></label><button className="primary submit" disabled={busy}>{busy?'Saving...':'Save transaction'}</button></form></div>}</div>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
