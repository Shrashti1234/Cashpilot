// @vitest-environment jsdom
import React from 'react';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {ContactControls} from './ContactControls';
const fetchMock=vi.fn(),props={apiUrl:'https://api.test',accessToken:'member-token',workspace:{id:'org',name:'Shop',mode:'b2b' as const,role:'owner'},onBack:vi.fn()};
beforeEach(()=>{vi.stubGlobal('fetch',fetchMock);fetchMock.mockReset();fetchMock.mockImplementation(async(url:string,args?:RequestInit)=>({ok:true,json:async()=>url.endsWith('/customers')?{customers:[{id:'buyer',name:'Buyer'}]}:url.endsWith('/invoices')?{invoices:[{id:'inv',customer_id:'buyer',invoice_number:'INV-1'}]}:url.endsWith('/preview')?{eligible:false,reasons:['No recorded active consent for this channel.'],draft:null,as_of:'2026-10-26',note:'Draft only. No message is sent.'}:args?.method==='POST'?{}:{preferences:[],history:[],consent_changes:[],last_contact_date:null,cooldown_days:3} }));});
afterEach(()=>{cleanup();vi.unstubAllGlobals();});
async function select(){await screen.findByRole('option',{name:'Buyer'});fireEvent.change(screen.getByLabelText('Customer'),{target:{value:'buyer'}});await screen.findByRole('option',{name:'INV-1'});fireEvent.change(screen.getByLabelText('Invoice'),{target:{value:'inv'}});}
it('shows blocked reminders without a copy control or recorded contact',async()=>{
 render(<ContactControls {...props}/>);await select();fireEvent.click(screen.getByRole('button',{name:'Check reminder eligibility'}));await screen.findByText('No recorded active consent for this channel.');expect(screen.queryByRole('button',{name:'Copy reviewed draft'})).toBeNull();expect(fetchMock.mock.calls.filter(([u,args])=>args?.method==='POST').map(([u])=>u)).toEqual(['https://api.test/api/v1/organizations/org/contacts/preview']);
});
it('requires an explicit completed-contact confirmation and keeps the chosen channel',async()=>{
 render(<ContactControls {...props}/>);await select();fireEvent.change(screen.getByLabelText('Channel'),{target:{value:'phone'}});fireEvent.change(screen.getByLabelText('Contact note'),{target:{value:'Actual call logged externally'}});expect((screen.getByRole('button',{name:'Record completed contact'}) as HTMLButtonElement).disabled).toBe(true);fireEvent.click(screen.getByLabelText('This contact already happened outside CashPilot.'));fireEvent.click(screen.getByRole('button',{name:'Record completed contact'}));await waitFor(()=>expect(fetchMock.mock.calls.some(([u])=>u.endsWith('/records'))).toBe(true));const call=fetchMock.mock.calls.find(([u])=>u.endsWith('/records'))!;expect(JSON.parse(call[1].body)).toMatchObject({invoice_id:'inv',channel:'phone',note:'Actual call logged externally',confirmed_external_contact:true});expect(call[1].headers.Authorization).toBe('Bearer member-token');
});
it('accountants can review drafts but cannot grant consent',async()=>{
 render(<ContactControls {...props} workspace={{...props.workspace,role:'accountant'}}/>);await select();expect(screen.queryByLabelText('Recorded consent status')).toBeNull();expect(screen.getByRole('button',{name:'Check reminder eligibility'})).toBeDefined();
});
