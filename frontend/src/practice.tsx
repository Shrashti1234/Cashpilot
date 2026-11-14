import React, {useState} from 'react';
import {createRoot} from 'react-dom/client';
import {ReceivableImport} from './ReceivableImport';
import {CollectionsWorklist} from './CollectionsWorklist';
import {InvoiceManagement} from './InvoiceManagement';
import {BankReconciliation} from './BankReconciliation';
import {download} from './operationsTypes';
import './style.css';
import './buyer.css';

const props = {apiUrl:'http://127.0.0.1:18081', accessToken:'cashpilot-disposable-demo',
 workspace:{id:'local-practice',name:'CashPilot practice',mode:'b2b' as const,role:'owner'}};
const sections = {import:ReceivableImport,collections:CollectionsWorklist,receipts:InvoiceManagement,bank:BankReconciliation};

function Practice(){
 const [section,setSection]=useState<keyof typeof sections|null>(null);
 const Screen=section?sections[section]:null;
 return <>
  <div className="workspace-top"><strong>CashPilot local practice · Sample data only · Resets when the API stops</strong></div>
  {Screen?<Screen {...props} onBack={()=>setSection(null)}/>:<main className="buyer-content">
   <h1>Practice the collections workflow</h1>
   <p>Use the sample CSVs below. Record a sample ₹1,000 receipt for PILOT-100, then match it to the sample bank transfer. This exercise never moves money. Do not enter real customer or bank data.</p>
   <ol>
    <li><button onClick={()=>download('open-receivables.csv','customer,reference,due,amount\nPilot Buyer,PILOT-100,2026-10-01,1000.00\n','text/csv')}>Download invoice CSV</button> <button onClick={()=>setSection('import')}>Import open invoices</button></li>
    <li><button onClick={()=>setSection('collections')}>Review and assign follow-up</button></li>
    <li><button onClick={()=>setSection('receipts')}>Record the sample receipt</button></li>
    <li><button onClick={()=>download('bank-statement.csv','booked_date,reference,description,amount_inr,currency\n2026-10-01,PILOT-BANK-1,Sample incoming transfer,1000.00,INR\n','text/csv')}>Download bank CSV</button> <button onClick={()=>setSection('bank')}>Match the bank transfer</button></li>
   </ol>
  </main>}
 </>;
}

createRoot(document.getElementById('root')!).render(import.meta.env.DEV&&location.hostname==='127.0.0.1'
 ? <Practice/> : <p>Practice mode is available only on the local development server.</p>);
