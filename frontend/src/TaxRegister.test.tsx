// @vitest-environment jsdom
import React from 'react';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {TaxRegister} from './TaxRegister';
const fetchMock=vi.fn(),props={apiUrl:'https://api.test',accessToken:'member-token',workspace:{id:'org',name:'Shop',mode:'b2b' as const,role:'viewer'},onBack:vi.fn()};
const totals={subtotal_paise:10000,discount_paise:0,taxable_paise:10000,cgst_paise:900,sgst_paise:0,utgst_paise:900,igst_paise:0,cess_paise:0,total_paise:11800};
const report={start:'2026-10-01',end:'2026-10-26',document_count:1,line_count:1,totals,available_supplier_gstins:['38ABCDE1234F1Z5'],registration_totals:[{supplier_gstin:'38ABCDE1234F1Z5',...totals}],documents:[],lines:[],hsn_summary:[],unclassified_invoice_count_all_dates:1,warnings:['One invoice has no source tax document.'],sources:[]};
beforeEach(()=>{vi.stubGlobal('fetch',fetchMock);fetchMock.mockReset();fetchMock.mockResolvedValue({ok:true,json:async()=>report});});
afterEach(()=>{cleanup();vi.unstubAllGlobals();});
it('shows recorded tax warnings and queries supplier registration independently',async()=>{
 render(<TaxRegister {...props}/>);await screen.findByText('One invoice has no source tax document.');expect(screen.getByRole('heading',{name:'Portal integration status'})).toBeDefined();expect(screen.getByText(/does not file returns, generate an IRN/)).toBeDefined();fireEvent.change(screen.getByLabelText('Supplier GSTIN filter'),{target:{value:'38ABCDE1234F1Z5'}});await waitFor(()=>expect(fetchMock.mock.calls.some(([u])=>u.includes('supplier_gstin=38ABCDE1234F1Z5'))).toBe(true));expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe('Bearer member-token');expect(fetchMock.mock.calls.every(([,args])=>!args.method||args.method==='GET')).toBe(true);
});
it('does not replace a failed register with estimated taxes',async()=>{
 fetchMock.mockResolvedValue({ok:false,json:async()=>({detail:'Use a narrower reporting period'})});render(<TaxRegister {...props}/>);await screen.findByRole('alert');expect(screen.queryByRole('button',{name:'Export review CSV'})).toBeNull();
});
