// @vitest-environment jsdom
import React from 'react';
import {act,cleanup,fireEvent,render,renderHook,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {FinanceWorkspace} from './FinanceWorkspace';
import {useAuthenticatedResource} from './useAuthenticatedResource';
import {csvCell} from './operationsTypes';

const position={effective_total_paise:5000,gross_paid_paise:8000,refunded_paise:0,paid_paise:8000,credit_paise:5000,debit_paise:0,outstanding_paise:0,credit_balance_paise:3000};
const invoice={id:'i1',invoice_number:'INV-1',customer_id:'c1',due_date:'2026-10-26',original_total_paise:10000,...position};
const ledger={invoice_id:'i1',invoice_number:'INV-1',original_total_paise:10000,...position,memos:[],refunds:[],payments:[]};
const props={apiUrl:'https://api.test',accessToken:'fixture-token',workspace:{id:'a',name:'Shop',mode:'b2b' as const,role:'owner'},onBack:vi.fn()};
const fetchMock=vi.fn();
beforeEach(()=>{
 vi.stubGlobal('fetch',fetchMock);fetchMock.mockReset();
 fetchMock.mockImplementation(async(url:string)=>({ok:true,json:async()=>url.endsWith('/invoices')?{invoices:[invoice]}:url.endsWith('/customers')?{customers:[{id:'c1',name:'Buyer'}]}:url.endsWith('/ledger')?ledger:url.endsWith('/statement')?{customer:{id:'c1',name:'Buyer'},totals:{...position,net_due_paise:-3000},invoices:[invoice]}:{id:'saved'}}));
});
afterEach(()=>{cleanup();vi.unstubAllGlobals();});

async function selectInvoice(){
 await screen.findByRole('option',{name:/INV-1/});
 await waitFor(()=>expect((screen.getByLabelText('Choose an invoice') as HTMLSelectElement).closest('fieldset')?.disabled).toBe(false));
 fireEvent.change(screen.getByLabelText('Choose an invoice'),{target:{value:'i1'}});
 await screen.findByText('Record an internal adjustment');
}

it('hides direct financial posting when independent approval is required',async()=>{
 const usual=fetchMock.getMockImplementation()!;fetchMock.mockImplementation((url:string,args?:RequestInit)=>url.endsWith('/financial-approvals/policy')?Promise.resolve({ok:true,json:async()=>({require_approval:true})}):usual(url,args));
 render(<FinanceWorkspace {...props}/>);await screen.findByRole('option',{name:/INV-1/});fireEvent.change(screen.getByLabelText('Choose an invoice'),{target:{value:'i1'}});await screen.findByText(/Independent approval is required for memos/);expect(screen.queryByRole('button',{name:'Record adjustment'})).toBeNull();expect(screen.queryByRole('button',{name:'Record completed refund'})).toBeNull();
});

it('posts exact adjustment amounts without posting a payment or refund',async()=>{
 render(<FinanceWorkspace {...props}/>);await selectInvoice();
 fireEvent.change(screen.getByLabelText('Memo number'),{target:{value:'CR-LOCAL'}});fireEvent.change(screen.getByLabelText('Adjustment amount (INR)'),{target:{value:'12.34'}});fireEvent.change(screen.getByLabelText('Adjustment reason'),{target:{value:'Agreed reduction'}});
 fireEvent.click(screen.getByRole('button',{name:'Record adjustment'}));
 await waitFor(()=>expect(fetchMock.mock.calls.filter(([,args])=>args.method==='POST')).toHaveLength(1));
 const call=fetchMock.mock.calls.find(([,args])=>args.method==='POST')!;expect(call[0]).toMatch(/\/invoices\/i1\/memos$/);expect(JSON.parse(call[1].body)).toMatchObject({kind:'credit',number:'CR-LOCAL',amount_paise:1234});
});

it('requires confirmation before recording a completed external refund',async()=>{
 render(<FinanceWorkspace {...props}/>);await selectInvoice();
 const button=screen.getByRole('button',{name:'Record completed refund'}) as HTMLButtonElement;expect(button.disabled).toBe(true);
 fireEvent.change(screen.getByLabelText('Completed refund amount (INR)'),{target:{value:'10.25'}});fireEvent.change(screen.getByLabelText('Refund reference / reason'),{target:{value:'External bank reference'}});
 fireEvent.click(screen.getByLabelText('I confirm this refund has already been completed outside CashPilot'));fireEvent.click(button);
 await waitFor(()=>expect(fetchMock.mock.calls.filter(([,args])=>args.method==='POST')).toHaveLength(1));const call=fetchMock.mock.calls.find(([,args])=>args.method==='POST')!;
 expect(call[0]).toMatch(/\/refunds$/);expect(JSON.parse(call[1].body)).toMatchObject({amount_paise:1025,confirmed_external_refund:true});
});

it('viewers see statements but no adjustment or refund forms',async()=>{
 render(<FinanceWorkspace {...props} workspace={{...props.workspace,role:'viewer'}}/>);await screen.findByRole('option',{name:/INV-1/});
 fireEvent.change(screen.getByLabelText('Choose an invoice'),{target:{value:'i1'}});await screen.findByText('Invoice activity');
 expect(screen.queryByRole('button',{name:'Record adjustment'})).toBeNull();expect(screen.queryByRole('button',{name:'Record completed refund'})).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'Customer statements'}));fireEvent.change(screen.getByLabelText('Statement customer'),{target:{value:'c1'}});await screen.findByRole('button',{name:'Export statement CSV'});
 expect(fetchMock.mock.calls.some(([,args])=>args.method==='POST')).toBe(false);
});

it('ignores a late response from the previous tenant',async()=>{
 const pending=new Map<string,(value:unknown)=>void>();fetchMock.mockImplementation((url:string)=>new Promise(resolve=>pending.set(url,resolve)));
 const {result,rerender}=renderHook(({url})=>useAuthenticatedResource<{tenant:string}>(url,'token'),{initialProps:{url:'https://api.test/a'}});
 rerender({url:'https://api.test/b'});expect(result.current.data).toBeNull();
 await act(async()=>pending.get('https://api.test/b')!({ok:true,json:async()=>({tenant:'B'})}));expect(result.current.data?.tenant).toBe('B');
 await act(async()=>pending.get('https://api.test/a')!({ok:true,json:async()=>({tenant:'A'})}));expect(result.current.data?.tenant).toBe('B');
});

it('neutralizes spreadsheet formulas in exported user text',()=>{
 expect(csvCell('=HYPERLINK("unsafe")')).toBe('"\'=HYPERLINK(""unsafe"")"');expect(csvCell('-12.50')).toBe('"-12.50"');expect(csvCell(-12.5)).toBe('"-12.5"');
});
