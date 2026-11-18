export type Profile={legal_name:string;address:string;gstin:string;state_code:string;require_approval:boolean};
export type Product={id:string;sku:string;name:string;unit:string;hsn_sac:string;unit_price_paise:number;tax_rate_bps:number;track_stock:boolean;reorder_milliunits:number;active:boolean;stock_milliunits:number;low_stock:boolean};
export type Party={name:string;address:string;gstin:string;state_code:string;place_of_supply:string};
export type Line={product_id:string|null;description:string;hsn_sac:string;unit:string;quantity_milliunits:number;unit_price_paise:number;discount_paise:number;tax_rate_bps:number;cess_rate_bps:number};
export type Totals={subtotal_paise:number;discount_paise:number;taxable_paise:number;cgst_paise:number;state_tax_paise:number;igst_paise:number;cess_paise:number;total_paise:number;tax_regime:string;state_tax_label:string};
export type TradeDoc={id:string;kind:string;number:string;status:string;customer_id:string|null;invoice_id:string|null;issue_date:string;due_date:string;party:Party;supplier:Profile;lines:(Line&{total_paise:number;track_stock:boolean})[];totals:Totals;received:Record<string,number>;notes:string;created_by:string;approved_by:string|null};
export type Movement={id:string;product_id:string;quantity_milliunits:number;reason:string;reference:string;created_at:string};
export const money=(paise:number)=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',minimumFractionDigits:2,maximumFractionDigits:2}).format(paise/100);
export const indiaDate=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Kolkata'}).format(new Date());
export const kindTitle=(kind:string)=>({invoice:'Invoice',estimate:'Estimate',purchase_order:'Purchase order'}[kind]??kind);
export function scaled(value:string,digits:number):number{
 const normalized=value.trim().replace(/^(-?)\./,(_match,sign:string)=>sign+'0.');
 const match=normalized.match(/^(-?)(\d+)(?:\.(\d+))?$/);
 if(!match||(match[3]?.length??0)>digits)throw new Error(`Use at most ${digits} decimal places.`);
 const result=Number(match[2])*10**digits+Number((match[3]??'').padEnd(digits,'0'));
 if(!Number.isSafeInteger(result))throw new Error('The amount is too large.');
 return match[1]?-result:result;
}
export function previewTotals(lines:Line[],supplierState:string,place:string):Totals{
 const totals:Totals={subtotal_paise:0,discount_paise:0,taxable_paise:0,cgst_paise:0,state_tax_paise:0,igst_paise:0,cess_paise:0,total_paise:0,tax_regime:supplierState===place?'intrastate':'interstate',state_tax_label:['04','26','31','35','38'].includes(supplierState)?'UTGST':'SGST'};
 for(const line of lines){
  const gross=Math.floor((line.quantity_milliunits*line.unit_price_paise+500)/1000),taxable=gross-line.discount_paise;
  const central=supplierState===place?Math.floor((taxable*line.tax_rate_bps+10000)/20000):0;
  const integrated=supplierState!==place?Math.floor((taxable*line.tax_rate_bps+5000)/10000):0;
  const cess=Math.floor((taxable*line.cess_rate_bps+5000)/10000);
  totals.subtotal_paise+=gross;totals.discount_paise+=line.discount_paise;totals.taxable_paise+=taxable;
  totals.cgst_paise+=central;totals.state_tax_paise+=central;totals.igst_paise+=integrated;totals.cess_paise+=cess;
  totals.total_paise+=taxable+central*2+integrated+cess;
 }
 return totals;
}
export function download(filename:string,data:string,type='application/json'){
 const url=URL.createObjectURL(new Blob([data],{type}));const a=document.createElement('a');a.href=url;a.download=filename;a.click();window.setTimeout(()=>URL.revokeObjectURL(url),1000);
}
export function csvCell(value:unknown):string{
 let text=String(value);
 if(typeof value!=='number'&&/^[=+\-@\t\r]/.test(text)&&!/^[-+]?\d+(?:\.\d+)?$/.test(text))text="'"+text;
 return '"'+text.replace(/"/g,'""')+'"';
}
