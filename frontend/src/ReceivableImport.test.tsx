// @vitest-environment jsdom
import React from 'react';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {ReceivableImport} from './ReceivableImport';

afterEach(()=>{cleanup();vi.unstubAllGlobals();});

it('requires a reviewed preview before committing the mapped file',async()=>{
 const file='customer,reference,due,amount\nBuyer,BILL-1,2026-11-01,25.55';
 const mock=vi.fn(async (url:string)=>({ok:true,json:async()=>url.endsWith('/inspect')?{headers:['customer','reference','due','amount']}:url.endsWith('/preview')?{rows:[],ready:1,duplicates:0,errors:0,ready_paise:2555,preview_digest:'fixture',blocked_by_approval:false}:{imported:1,duplicates:0}}));
 vi.stubGlobal('fetch',mock);
 render(<ReceivableImport apiUrl="https://example.test" accessToken="fixture" workspace={{id:'a',name:'Shop',mode:'b2b',role:'owner'}} onBack={()=>{}}/>);
 const upload=new File([file],'report.csv',{type:'text/csv'});
 Object.defineProperty(upload,'text',{value:async()=>file});
 fireEvent.change(screen.getByLabelText('Receivables CSV'),{target:{files:[upload]}});
 fireEvent.click(await screen.findByRole('button',{name:'Preview import'}));
 const confirm=await screen.findByRole('button',{name:'Confirm import'});
 expect(mock.mock.calls.some(([url])=>url.endsWith('/commit'))).toBe(false);
 fireEvent.click(confirm);
 await screen.findByText('1 opening balances imported. 0 duplicates skipped.');
 expect(mock.mock.calls.map(([url])=>url.slice(url.lastIndexOf('/')+1))).toEqual(['inspect','preview','commit']);
});
