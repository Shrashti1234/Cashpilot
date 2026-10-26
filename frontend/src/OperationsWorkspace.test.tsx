// @vitest-environment jsdom
import React from 'react';
import {cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {OperationsWorkspace} from './OperationsWorkspace';
import {DocumentWorkbench} from './DocumentWorkbench';
import {scaled,previewTotals} from './operationsTypes';

const profile={legal_name:'Example business',address:'Test address',gstin:'',state_code:'27',require_approval:false};
const props={apiUrl:'https://api.test',accessToken:'fixture-token',workspace:{id:'a',name:'Shop',mode:'b2b' as const,role:'owner'},onBack:vi.fn()};
const fetchMock=vi.fn();
beforeEach(()=>{
 vi.stubGlobal('fetch',fetchMock);fetchMock.mockReset();
 fetchMock.mockImplementation(async(url:string)=>({ok:true,json:async()=>url.endsWith('/profile')?{profile}:url.endsWith('/products')?{products:[]}:url.endsWith('/documents')?{documents:[]}:url.endsWith('/stock')?{movements:[]}:url.endsWith('/recurring')?{rules:[]}:{customers:[]}}));
});
afterEach(()=>{cleanup();vi.unstubAllGlobals();});

it('preserves fractional paise precision and rejects extra input decimals',()=>{
 expect(scaled('1234.56',2)).toBe(123456);expect(scaled('-1.250',3)).toBe(-1250);expect(scaled('.75',3)).toBe(750);
 expect(()=>scaled('1.001',2)).toThrow();expect(()=>scaled('1e3',2)).toThrow();
 const line={product_id:null,description:'Service',hsn_sac:'9983',unit:'HRS',quantity_milliunits:1500,unit_price_paise:10000,discount_paise:1000,tax_rate_bps:1800,cess_rate_bps:100};
 const a=previewTotals([line],'27','27'),b=previewTotals([line],'27','29');
 expect(a.total_paise).toBe(16660);expect(b.total_paise).toBe(a.total_paise);expect(a.cgst_paise).toBe(a.state_tax_paise);expect(b.igst_paise).toBe(2520);
});

it('authenticates reads and submits product amounts as exact integer units',async()=>{
 render(<OperationsWorkspace {...props}/>);await screen.findByText('No commercial documents yet.');
 expect(fetchMock.mock.calls.every(([,options])=>options.headers.Authorization==='Bearer fixture-token')).toBe(true);
 fireEvent.click(screen.getByRole('button',{name:'Products'}));
 fireEvent.change(screen.getByLabelText('SKU'),{target:{value:'TEST-1'}});fireEvent.change(screen.getByLabelText('Product / service name'),{target:{value:'Example'}});
 fireEvent.change(screen.getByLabelText('Unit price (INR)'),{target:{value:'1234.56'}});fireEvent.change(screen.getByLabelText('GST rate (%)'),{target:{value:'18.25'}});fireEvent.change(screen.getByLabelText('Reorder threshold (units)'),{target:{value:'1.250'}});
 fireEvent.click(screen.getByRole('button',{name:'Add product'}));
 await waitFor(()=>expect(fetchMock.mock.calls.some(([,args])=>args.method==='POST')).toBe(true));
 const post=fetchMock.mock.calls.find(([,args])=>args.method==='POST');expect(JSON.parse(post![1].body)).toMatchObject({unit_price_paise:123456,tax_rate_bps:1825,reorder_milliunits:1250});
});

it('viewers can inspect but cannot draft, modify catalogue or change stock',async()=>{
 render(<OperationsWorkspace {...props} workspace={{...props.workspace,role:'viewer'}}/>);await screen.findByText('No commercial documents yet.');
 expect(screen.queryByRole('button',{name:'New document'})).toBeNull();fireEvent.click(screen.getByRole('button',{name:'Products'}));expect(screen.queryByRole('button',{name:'Add product'})).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'Stock ledger'}));expect(screen.queryByRole('button',{name:'Record stock adjustment'})).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'Business profile'}));expect(screen.queryByRole('button',{name:'Save business profile'})).toBeNull();
});

it('builds a multi-line draft and keeps the document separate from issuance',async()=>{
 const write=vi.fn().mockResolvedValue(undefined);
 render(<DocumentWorkbench documents={[]} products={[]} customers={[]} profile={profile} busy={false} canWrite canAdmin write={write}/>);
 fireEvent.click(screen.getByRole('button',{name:'New document'}));fireEvent.change(screen.getByLabelText('Document number'),{target:{value:'EST-1'}});
 fireEvent.change(screen.getByLabelText('Recipient / supplier name'),{target:{value:'Buyer'}});fireEvent.change(screen.getByLabelText('Recipient / supplier address'),{target:{value:'Recipient address'}});
 let item=within(screen.getByRole('group',{name:'Item 1'}));fireEvent.change(item.getByLabelText('Description'),{target:{value:'Advisory'}});fireEvent.change(item.getByLabelText('Unit price (INR)'),{target:{value:'100.25'}});fireEvent.change(item.getByLabelText('Quantity'),{target:{value:'1.250'}});
 fireEvent.click(screen.getByRole('button',{name:'Add line item'}));item=within(screen.getByRole('group',{name:'Item 2'}));fireEvent.change(item.getByLabelText('Description'),{target:{value:'Delivery'}});fireEvent.change(item.getByLabelText('Unit price (INR)'),{target:{value:'10'}});
 fireEvent.click(screen.getByRole('button',{name:'Save draft'}));
 await waitFor(()=>expect(write).toHaveBeenCalledTimes(1));expect(write.mock.calls[0][0]).toBe('/documents');expect(write.mock.calls[0][1].lines[0]).toMatchObject({quantity_milliunits:1250,unit_price_paise:10025});expect(write.mock.calls[0][1].lines).toHaveLength(2);
});

it('shows a load error without inventing products',async()=>{
 fetchMock.mockResolvedValue({ok:false,json:async()=>({detail:'Forbidden'})});render(<OperationsWorkspace {...props}/>);
 expect((await screen.findByRole('alert')).textContent).toContain('Could not load business operations');
});

it('keeps controls disabled until the initial load finishes',()=>{
 fetchMock.mockImplementation(()=>new Promise(()=>{}));render(<OperationsWorkspace {...props}/>);
 expect((screen.getByRole('button',{name:'Business profile'}) as HTMLButtonElement).closest('fieldset')?.disabled).toBe(true);
});
