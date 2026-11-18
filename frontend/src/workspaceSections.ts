export const workspaceGroups = [
 {label:'Receivables',items:[
  {id:'customers',label:'Customers'},
  {id:'invoices',label:'Invoices & receipts'},
  {id:'collections',label:'Collections worklist'},
  {id:'buyers',label:'Buyer links & promises'},
  {id:'contacts',label:'Contact preferences'},
  {id:'disputes',label:'Disputes & activity'},
  {id:'import',label:'Import open invoices',admin:true},
 ]},
 {label:'Operations',items:[
  {id:'operations',label:'Products & documents'},
  {id:'finance',label:'Ledger & statements'},
  {id:'banking',label:'Bank reconciliation'},
  {id:'tax',label:'Tax register'},
 ]},
 {label:'Cash planning',items:[
  {id:'cash',label:'Cash history'},
  {id:'decision',label:'Decision Lab'},
  {id:'journal',label:'Forecast journal'},
 ]},
 {label:'Administration',items:[
  {id:'approvals',label:'Financial approvals'},
  {id:'team',label:'Team & access',admin:true},
  {id:'evidence',label:'Invoice evidence export',admin:true},
 ]},
] as const;

export type WorkspaceSection = typeof workspaceGroups[number]['items'][number]['id'];
export type Destination = 'overview' | WorkspaceSection;

export function accessibleWorkspaceGroups(role:string){
 const admin=role==='owner'||role==='admin';
 return workspaceGroups.map(group=>({
  label:group.label,
  items:group.items.filter(item=>!('admin' in item)||admin),
 }));
}
