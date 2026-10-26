// @vitest-environment jsdom
import React from 'react';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {BuyerPortal} from './BuyerPortal';
import {BuyerAccessManager} from './BuyerAccessManager';
const token='a'.repeat(43),fetchMock=vi.fn();
const invoice={invoice_number:'INV-1',due_date:'2026-11-01',adjusted_total_paise:10000,net_received_paise:0,outstanding_paise:10000,customer_credit_paise:0,seller:{legal_name:'Seller',address:'Delhi',gstin:''},recipient_name:'Buyer',lines:[],as_of:'2026-10-26',expires_at:'2090-01-01T00:00:00Z',permissions:{can_dispute:true,can_promise:true},dispute:null,promises:[]};
beforeEach(()=>{vi.stubGlobal('fetch',fetchMock);fetchMock.mockReset();fetchMock.mockResolvedValue({ok:true,json:async()=>invoice});history.replaceState(null,'','/buyer#buyer='+token);});
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.clearAllMocks();});
it('keeps private access out of subsequent URLs and sends no account credentials',async()=>{
 render(<BuyerPortal apiUrl="https://api.test" initialToken={token}/>);await screen.findByText('INV-1');expect(location.hash).toBe('');
 const [url,args]=fetchMock.mock.calls[0];expect(url).toBe('https://api.test/api/v1/buyer/inspect');expect(args.credentials).toBe('omit');expect(args.headers.Authorization).toBeUndefined();expect(JSON.parse(args.body)).toEqual({token});expect(localStorage.getItem('buyer')).toBeNull();
 fireEvent.change(screen.getByLabelText('Amount (INR)'),{target:{value:'12.34'}});fireEvent.change(screen.getByLabelText('Promised date'),{target:{value:'2026-11-01'}});fireEvent.click(screen.getByRole('button',{name:'Record payment promise'}));
 await waitFor(()=>expect(fetchMock.mock.calls.some(([u])=>u.endsWith('/promise'))).toBe(true));const call=fetchMock.mock.calls.find(([u])=>u.endsWith('/promise'))!;expect(JSON.parse(call[1].body)).toMatchObject({token,amount_paise:1234,promised_date:'2026-11-01'});
});
it('respects viewing permissions and clears invoice data after revocation',async()=>{
 fetchMock.mockResolvedValueOnce({ok:true,json:async()=>({...invoice,permissions:{can_dispute:false,can_promise:false}})}).mockResolvedValue({ok:false,status:404,json:async()=>({detail:'Private invoice access is invalid or expired'})});
 render(<BuyerPortal apiUrl="https://api.test" initialToken={token}/>);await screen.findByText('INV-1');expect(screen.queryByRole('button',{name:'Record payment promise'})).toBeNull();expect(screen.queryByRole('button',{name:'Raise invoice issue'})).toBeNull();fireEvent.click(screen.getByRole('button',{name:'Refresh invoice'}));await screen.findByRole('alert');expect(screen.queryByText('Seller')).toBeNull();
});
it('does not substitute a sample invoice for missing access',async()=>{render(<BuyerPortal apiUrl="https://api.test" initialToken=""/>);await screen.findByRole('alert');expect(fetchMock).not.toHaveBeenCalled();expect(screen.queryByText('INV-1')).toBeNull();});
it('viewers see commitments but cannot create private links or promises',async()=>{
 fetchMock.mockImplementation(async(url:string)=>({ok:true,json:async()=>url.endsWith('/invoices')?{invoices:[{id:'inv',invoice_number:'INV-1',outstanding_paise:10000}]}:{promises:[]}}));
 render(<BuyerAccessManager apiUrl="https://api.test" accessToken="account-token" workspace={{id:'org',name:'Shop',mode:'b2b',role:'viewer'}} onBack={()=>{}}/>);await screen.findByText('No promises recorded.');expect(screen.queryByRole('button',{name:'Create private link'})).toBeNull();expect(screen.queryByRole('button',{name:'Record promise'})).toBeNull();expect(fetchMock.mock.calls.some(([url])=>url.endsWith('/buyer-access'))).toBe(false);
});
