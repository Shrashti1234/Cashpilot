import React,{useEffect,useState} from 'react';
import {ArrowLeft,Boxes} from 'lucide-react';
import type {BusinessWorkspace} from './CustomerManagement';
import {DocumentWorkbench} from './DocumentWorkbench';
import {RecurringDocuments,type RecurringSeries} from './RecurringDocuments';
import {money,scaled,download,csvCell,type Movement,type Product,type Profile,type TradeDoc} from './operationsTypes';
import './operations.css';

export type OperationsWrite=(path:string,data:unknown,onSaved?:(body:{id?:string})=>void)=>Promise<void>;
type Props={apiUrl:string;accessToken:string;workspace:BusinessWorkspace;onBack:()=>void};
const emptyProfile:Profile={legal_name:'',address:'',gstin:'',state_code:'',require_approval:false};
const emptyProduct={sku:'',name:'',unit:'NOS',hsn_sac:'',price:'',rate:'0',track:true,reorder:'0',active:true};

export function OperationsWorkspace({apiUrl,accessToken,workspace,onBack}:Props){
 const [tab,setTab]=useState<'documents'|'products'|'stock'|'profile'|'recurring'>('documents');
 const [rules,setRules]=useState<RecurringSeries[]>([]);
 const [profile,setProfile]=useState<Profile|null>(null),[profileForm,setProfileForm]=useState(emptyProfile);
 const [products,setProducts]=useState<Product[]>([]),[documents,setDocuments]=useState<TradeDoc[]>([]),[movements,setMovements]=useState<Movement[]>([]);
 const [customers,setCustomers]=useState<{id:string;name:string}[]>([]);
 const [busy,setBusy]=useState(true),[error,setError]=useState(''),[notice,setNotice]=useState(''),[revision,setRevision]=useState(0);
 const [productForm,setProductForm]=useState(emptyProduct),[editingProduct,setEditingProduct]=useState('');
 const [stockProduct,setStockProduct]=useState(''),[stockQuantity,setStockQuantity]=useState(''),[stockReference,setStockReference]=useState(''),[stockKey,setStockKey]=useState(()=>crypto.randomUUID());
 const base=`${apiUrl}/api/v1/organizations/${encodeURIComponent(workspace.id)}`;
 const canWrite=workspace.role!=='viewer',canAdmin=['owner','admin'].includes(workspace.role);
 useEffect(()=>{
  const controller=new AbortController();let active=true;setBusy(true);setError('');
  const timer=window.setTimeout(()=>controller.abort(),90000);
  async function load(){try{
   const paths=['/operations/profile','/operations/products','/operations/documents','/operations/stock','/customers','/operations/recurring'];
   const results=await Promise.all(paths.map(path=>fetch(base+path,{headers:{Authorization:`Bearer ${accessToken}`},signal:controller.signal})));
   if(results.some(r=>!r.ok))throw new Error('Could not load business operations. Please retry.');
   const [p,c,d,s,b,r]=await Promise.all(results.map(r=>r.json()));
   if(active){setProfile(p.profile);setProfileForm(p.profile??emptyProfile);setProducts(c.products);setDocuments(d.documents);setMovements(s.movements);setCustomers(b.customers);setRules(r.rules);}
  }catch(e){if(active)setError(controller.signal.aborted?'The request timed out. Please retry.':e instanceof Error?e.message:'Could not load operations.');}
  finally{window.clearTimeout(timer);if(active)setBusy(false);}}
  void load();return()=>{active=false;controller.abort();window.clearTimeout(timer);};
 },[base,accessToken,revision]);
 const write:OperationsWrite=async(path,data,onSaved)=>{
  if(busy)return;setBusy(true);setError('');setNotice('');const controller=new AbortController();const timer=window.setTimeout(()=>controller.abort(),90000);
  try{const response=await fetch(base+'/operations'+path,{method:'POST',headers:{Authorization:`Bearer ${accessToken}`,'Content-Type':'application/json'},body:JSON.stringify(data),signal:controller.signal});
   const body=await response.json();if(!response.ok)throw new Error(typeof body.detail==='string'?body.detail:'Check the form values and retry.');
   onSaved?.(body);setNotice('Saved successfully.');setRevision(v=>v+1);
  }catch(e){setError(controller.signal.aborted?'The request timed out. Refresh to check whether it saved before retrying.':e instanceof Error?e.message:'Could not save.');setBusy(false);}
  finally{window.clearTimeout(timer);}
 };
 function saveProduct(e:React.FormEvent){e.preventDefault();try{
  void write('/products'+(editingProduct?'/'+editingProduct:''),{sku:productForm.sku,name:productForm.name,unit:productForm.unit,hsn_sac:productForm.hsn_sac,unit_price_paise:scaled(productForm.price,2),tax_rate_bps:scaled(productForm.rate,2),track_stock:productForm.track,reorder_milliunits:scaled(productForm.reorder,3),active:productForm.active},()=>{setEditingProduct('');setProductForm(emptyProduct);});
 }catch(e){setError((e as Error).message);}}
 function exportCatalogue(){const rows=[['sku','name','unit','price_inr','tax_percent','stock_units'],...products.map(p=>[p.sku,p.name,p.unit,(p.unit_price_paise/100).toFixed(2),(p.tax_rate_bps/100).toFixed(2),p.track_stock?(p.stock_milliunits/1000).toFixed(3):'not tracked'])];download('catalogue.csv',rows.map(row=>row.map(csvCell).join(',')).join('\r\n'),'text/csv');}
 return <div className="workspace-screen"><div className="workspace-top"><div className="workspace-brand"><Boxes size={24}/>CashPilot</div><span className="eyebrow">{workspace.name}</span></div><main className="decision-content ops-content">
  <button className="workspace-back" onClick={onBack}><ArrowLeft size={16}/>Back to customers</button><div className="workspace-heading"><div><span className="eyebrow">FROM QUOTE TO CASH</span><h1>Business operations</h1><p>Products, stock, estimates, purchase orders and line-item invoices.</p></div></div>
  <fieldset disabled={busy} className="ops-fieldset"><nav className="lab-tabs" aria-label="Business operations">{(['documents','products','stock','recurring','profile'] as const).map(t=><button key={t} className={tab===t?'active':''} onClick={()=>{setTab(t);setError('');}}>{({documents:'Documents',products:'Products',stock:'Stock ledger',recurring:'Recurring',profile:'Business profile'})[t]}</button>)}</nav>
  {error&&<div role="alert" className="error">{error}<button onClick={()=>setRevision(v=>v+1)}>Reload</button></div>}{notice&&<p role="status" className="lab-notice">{notice}</p>}{busy&&<p role="status" className="lab-loading">Loading business records…</p>}
  {tab==='documents'&&<DocumentWorkbench {...{documents,products,customers,profile,busy,canWrite,canAdmin,write}}/>}
  {tab==='recurring'&&<RecurringDocuments {...{documents,rules,busy,canWrite,canAdmin,write}}/>}
  {tab==='profile'&&<section className="panel"><h2>Supplier details & approval policy</h2><p>Snapshots are stored with every document. GSTIN checks cover format and state prefix, not registry status.</p><form className="lab-ledger-form" onSubmit={e=>{e.preventDefault();void write('/profile',profileForm);}}>
   <label>Legal business name<input required maxLength={160} disabled={!canAdmin} value={profileForm.legal_name} onChange={e=>setProfileForm({...profileForm,legal_name:e.target.value})}/></label><label>Business address<input required maxLength={1000} disabled={!canAdmin} value={profileForm.address} onChange={e=>setProfileForm({...profileForm,address:e.target.value})}/></label><label>State / UT code<input required pattern="[0-9]{2}" placeholder="e.g. 27" disabled={!canAdmin} value={profileForm.state_code} onChange={e=>setProfileForm({...profileForm,state_code:e.target.value})}/></label><label>GSTIN (if registered)<input maxLength={15} disabled={!canAdmin} value={profileForm.gstin} onChange={e=>setProfileForm({...profileForm,gstin:e.target.value.toUpperCase()})}/></label><label className="ops-checkbox"><input type="checkbox" disabled={!canAdmin} checked={profileForm.require_approval} onChange={e=>setProfileForm({...profileForm,require_approval:e.target.checked})}/>Require a different owner/admin to approve before issue</label>{canAdmin&&<button disabled={busy} className="primary">Save business profile</button>}
  </form>{!canAdmin&&<p>Only owners and administrators can change the profile or approval policy.</p>}</section>}
  {tab==='products'&&<section className="panel"><div className="panel-heading"><div><h2>Product & service catalogue</h2><p>Amounts include paise. Quantities support three decimal places.</p></div><button className="workspace-secondary" onClick={exportCatalogue}>Export CSV</button></div>
   {canWrite&&<form className="lab-ledger-form" onSubmit={saveProduct}><label>SKU<input required maxLength={60} value={productForm.sku} onChange={e=>setProductForm({...productForm,sku:e.target.value})}/></label><label>Product / service name<input required maxLength={160} value={productForm.name} onChange={e=>setProductForm({...productForm,name:e.target.value})}/></label><label>Unit<input required maxLength={16} value={productForm.unit} onChange={e=>setProductForm({...productForm,unit:e.target.value})}/></label><label>Unit price (INR)<input required type="number" min="0" step=".01" value={productForm.price} onChange={e=>setProductForm({...productForm,price:e.target.value})}/></label><label>GST rate (%)<input required type="number" min="0" max="100" step=".01" value={productForm.rate} onChange={e=>setProductForm({...productForm,rate:e.target.value})}/></label><label>HSN / SAC<input pattern="[0-9]{4,8}" value={productForm.hsn_sac} onChange={e=>setProductForm({...productForm,hsn_sac:e.target.value})}/></label><label>Reorder threshold (units)<input type="number" min="0" step=".001" required value={productForm.reorder} onChange={e=>setProductForm({...productForm,reorder:e.target.value})}/></label><label className="ops-checkbox"><input type="checkbox" checked={productForm.track} onChange={e=>setProductForm({...productForm,track:e.target.checked})}/>Track stock</label><label className="ops-checkbox"><input type="checkbox" checked={productForm.active} onChange={e=>setProductForm({...productForm,active:e.target.checked})}/>Active in catalogue</label><button disabled={busy} className="primary">{editingProduct?'Save product changes':'Add product'}</button>{editingProduct&&<button type="button" className="workspace-secondary" onClick={()=>{setEditingProduct('');setProductForm(emptyProduct);}}>Cancel edit</button>}</form>}
   <div className="table-wrap"><table><thead><tr><th>SKU / PRODUCT</th><th>PRICE</th><th>GST</th><th>STOCK</th><th>STATUS</th><th></th></tr></thead><tbody>{products.map(p=><tr key={p.id}><td>{p.sku} · {p.name}</td><td>{money(p.unit_price_paise)}</td><td>{p.tax_rate_bps/100}%</td><td>{p.track_stock?`${p.stock_milliunits/1000} ${p.unit}`:'Not tracked'}</td><td>{p.active?(p.low_stock?'Reorder needed':'Active'):'Archived'}</td><td>{canWrite&&<button className="workspace-secondary" onClick={()=>{setEditingProduct(p.id);setProductForm({sku:p.sku,name:p.name,unit:p.unit,hsn_sac:p.hsn_sac,price:(p.unit_price_paise/100).toFixed(2),rate:String(p.tax_rate_bps/100),reorder:String(p.reorder_milliunits/1000),track:p.track_stock,active:p.active});}}>Edit {p.sku}</button>}</td></tr>)}</tbody></table>{!products.length&&<p className="workspace-empty">Add your first product or service.</p>}</div>
  </section>}
  {tab==='stock'&&<section className="panel"><h2>Stock movement ledger</h2><p>Correct mistakes with a compensating adjustment and a reason. Negative stock is rejected.</p>{canAdmin&&<form className="lab-ledger-form" onSubmit={e=>{e.preventDefault();try{void write('/stock',{product_id:stockProduct,quantity_milliunits:scaled(stockQuantity,3),reference:stockReference,request_key:stockKey},()=>{setStockQuantity('');setStockReference('');setStockKey(crypto.randomUUID());});}catch(err){setError((err as Error).message);}}}><label>Stock product<select required value={stockProduct} onChange={e=>setStockProduct(e.target.value)}><option value="">Choose a product</option>{products.filter(p=>p.track_stock).map(p=><option key={p.id} value={p.id}>{p.sku} · {p.name}</option>)}</select></label><label>Quantity change (signed units)<input required type="number" step=".001" value={stockQuantity} onChange={e=>setStockQuantity(e.target.value)}/></label><label>Adjustment reason / reference<input required maxLength={160} value={stockReference} onChange={e=>setStockReference(e.target.value)}/></label><button disabled={busy} className="primary">Record stock adjustment</button></form>}
   <div className="table-wrap"><table><thead><tr><th>WHEN</th><th>PRODUCT</th><th>QUANTITY</th><th>REASON</th><th>REFERENCE</th></tr></thead><tbody>{movements.map(m=><tr key={m.id}><td>{new Date(m.created_at).toLocaleString()}</td><td>{products.find(p=>p.id===m.product_id)?.sku??m.product_id}</td><td>{m.quantity_milliunits>0?'+':''}{m.quantity_milliunits/1000}</td><td>{m.reason.replace(/_/g,' ')}</td><td>{m.reference}</td></tr>)}</tbody></table>{!movements.length&&<p className="workspace-empty">No stock movements recorded.</p>}</div>
  </section>}
 </fieldset></main></div>;
}
