// @vitest-environment jsdom
import React from 'react';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {FinancialApprovals} from './FinancialApprovals';
const fetchMock=vi.fn(),props={apiUrl:'https://api.test',accessToken:'owner-token',workspace:{id:'org',name:'Shop',mode:'b2b' as const,role:'owner'},onBack:vi.fn()};
const own={id:'request',invoice_id:'inv',operation:'memo',payload:{kind:'credit',number:'CR-1',amount_paise:1234,reason:'Adjustment'},status:'pending',requested_by:'owner',decided_by:null,decision_note:null,decided_at:null};
beforeEach(()=>{vi.stubGlobal('fetch',fetchMock);fetchMock.mockReset();fetchMock.mockImplementation(async(url:string,args?:RequestInit)=>({ok:true,json:async()=>args?.method==='POST'?{id:'request'}:url.endsWith('/policy')?{require_approval:true,active_approvers:2,actor_id:'owner'}:url.endsWith('/invoices')?{invoices:[{id:'inv',invoice_number:'INV-1'}]}:{requests:[own]}}));});
afterEach(()=>{cleanup();vi.unstubAllGlobals();});
it('does not offer self-approval but allows the requester to cancel',async()=>{
 render(<FinancialApprovals {...props}/>);await screen.findByRole('button',{name:'Review request'});fireEvent.click(screen.getByRole('button',{name:'Review request'}));expect(screen.queryByRole('option',{name:'Approve and post record'})).toBeNull();expect(screen.getByRole('option',{name:'Cancel request'})).toBeDefined();expect(screen.getByText(/You cannot approve your own request/)).toBeDefined();
});
it('submits exact-paise memo details without directly posting a ledger record',async()=>{
 render(<FinancialApprovals {...props}/>);await screen.findByRole('option',{name:'INV-1'});fireEvent.change(screen.getByLabelText('Approval invoice'),{target:{value:'inv'}});fireEvent.change(screen.getByLabelText('Memo number'),{target:{value:'CR-NEW'}});fireEvent.change(screen.getByLabelText('Amount (INR)'),{target:{value:'12.34'}});fireEvent.change(screen.getByLabelText('Financial request reason'),{target:{value:'Review adjustment'}});fireEvent.click(screen.getByRole('button',{name:'Submit for independent review'}));await waitFor(()=>expect(fetchMock.mock.calls.some(([,args])=>args?.method==='POST')).toBe(true));const call=fetchMock.mock.calls.find(([,args])=>args?.method==='POST')!;expect(call[0]).toMatch(/\/financial-approvals$/);expect(JSON.parse(call[1].body)).toMatchObject({invoice_id:'inv',operation:'memo',memo:{kind:'credit',number:'CR-NEW',amount_paise:1234,reason:'Review adjustment'}});expect(fetchMock.mock.calls.some(([u])=>u.endsWith('/memos'))).toBe(false);
});
it('viewers cannot submit requests, change policy or decide pending records',async()=>{
 render(<FinancialApprovals {...props} workspace={{...props.workspace,role:'viewer'}}/>);await screen.findByText('Latest 200 requests');expect(screen.queryByRole('button',{name:'Submit for independent review'})).toBeNull();expect(screen.queryByRole('button',{name:'Require independent approval'})).toBeNull();expect(screen.queryByRole('button',{name:'Review request'})).toBeNull();
});
