// @vitest-environment jsdom
import React from 'react';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {InvoiceEvidence} from './InvoiceEvidence';
const fetchMock=vi.fn(),props={apiUrl:'https://api.test',accessToken:'owner-token',workspace:{id:'org',name:'Shop',mode:'b2b' as const,role:'owner'},onBack:vi.fn()};
beforeEach(()=>{vi.stubGlobal('fetch',fetchMock);fetchMock.mockReset();fetchMock.mockImplementation(async(url:string)=>({ok:true,json:async()=>url.endsWith('/invoices')?{invoices:[{id:'inv',invoice_number:'INV-1'}]}:{invoice_number:'INV-1',categories:{documents:1,receipts:2},note:'Private current records.'},blob:async()=>new Blob(['fixture'])}));});
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks();});
it('requires preview and explicit private-download confirmation',async()=>{
 const create=vi.fn(()=> 'blob:local'),revoke=vi.fn();Object.defineProperty(URL,'createObjectURL',{configurable:true,value:create});Object.defineProperty(URL,'revokeObjectURL',{configurable:true,value:revoke});vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});
 render(<InvoiceEvidence {...props}/>);await screen.findByRole('option',{name:'INV-1'});fireEvent.change(screen.getByLabelText('Invoice to export'),{target:{value:'inv'}});expect(screen.queryByRole('button',{name:'Download private ZIP bundle'})).toBeNull();fireEvent.click(screen.getByRole('button',{name:'Review included records'}));await screen.findByRole('heading',{name:'INV-1'});expect((screen.getByRole('button',{name:'Download private ZIP bundle'}) as HTMLButtonElement).disabled).toBe(true);fireEvent.click(screen.getByLabelText(/I intend to download these private records/));fireEvent.click(screen.getByRole('button',{name:'Download private ZIP bundle'}));await waitFor(()=>expect(create).toHaveBeenCalledTimes(1));const call=fetchMock.mock.calls.find(([u])=>u.endsWith('/bundle'))!;expect(JSON.parse(call[1].body)).toEqual({confirmed_private_download:true});expect(call[1].headers.Authorization).toBe('Bearer owner-token');
});
it('does not load combined evidence for read-only users',async()=>{
 render(<InvoiceEvidence {...props} workspace={{...props.workspace,role:'viewer'}}/>);await screen.findByText('Only business owners and administrators can export these combined private records.');expect(fetchMock).not.toHaveBeenCalled();
});
