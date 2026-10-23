// @vitest-environment jsdom
import React from 'react';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {DecisionLab} from './DecisionLab';

vi.mock('./IntelligenceViews',()=>({SimulationViews:()=> <div>Simulation result</div>,ModelEvidence:()=> <div>Synthetic model evidence</div>}));
const point={date:'2026-10-23',p10_paise:0,median_paise:1000,p90_paise:2000};
const projection={points:[point],closing_median_paise:1000,minimum_median_paise:0,shortfall_frequency:.3,first_median_shortfall_date:null,deferred_beyond_horizon_paise:0};
const result={as_of:'2026-10-23',baseline:projection,scenario:projection,invoice_risks:[{invoice_id:'i-1',customer_name:'Aster',outstanding_paise:10000}],planned_expenses:[],warnings:[],recommended_reviews:[]};
const fetchMock=vi.fn();
const props={apiUrl:'https://api.test',accessToken:'user-token',workspace:{id:'a',name:'Shop',mode:'micro' as const,role:'owner'},onBack:vi.fn()};
beforeEach(()=>{
 vi.stubGlobal('fetch',fetchMock);fetchMock.mockReset();
 fetchMock.mockImplementation(async(url:string)=>({ok:true,json:async()=>url.endsWith('/simulate')?result:url.endsWith('/cash-entries')?{entries:[]}:{version:'synthetic-v1'}}));
});
afterEach(()=>{cleanup();vi.unstubAllGlobals();});

it('starts in an explicitly synthetic read-only demo and sends authenticated simulations',async()=>{
 render(<DecisionLab {...props}/>);
 await screen.findByText('Simulation result');
 expect(screen.getByText('Synthetic demo workspace')).toBeTruthy();
 const call=fetchMock.mock.calls.find(([url])=>url.endsWith('/simulate'));
 expect(call?.[1].headers.Authorization).toBe('Bearer user-token');
 expect(JSON.parse(call?.[1].body).use_demo).toBe(true);
 expect(fetchMock.mock.calls.filter(([,args])=>args?.method==='POST').map(([url])=>url)).toEqual(['https://api.test/api/v1/organizations/a/decision-lab/simulate']);
});

it('submits the selected receipt date and preserves cash amount in paise',async()=>{
 render(<DecisionLab {...props}/>);await screen.findByText('Simulation result');
 fireEvent.change(screen.getByLabelText('Opening available cash (INR)'),{target:{value:'1234.56'}});
 fireEvent.change(screen.getByLabelText('Assume an invoice is collected'),{target:{value:'i-1'}});
 fireEvent.change(screen.getByLabelText('Assumed receipt date'),{target:{value:'2026-10-24'}});
 fireEvent.click(screen.getByRole('button',{name:'Compare scenario'}));
 await waitFor(()=>expect(fetchMock.mock.calls.filter(([url])=>url.endsWith('/simulate')).length).toBe(2));
 const calls=fetchMock.mock.calls.filter(([url])=>url.endsWith('/simulate'));
 expect(JSON.parse(calls[1][1].body)).toMatchObject({opening_balance_paise:123456,receipt_overrides:[{invoice_id:'i-1',receipt_date:'2026-10-24'}]});
 expect(fetchMock.mock.calls.some(([url,args])=>url.includes('/payments')||url.endsWith('/cash-entries')&&args?.method==='POST')).toBe(false);
});

it('switches to real workspace records without writing demo records',async()=>{
 render(<DecisionLab {...props}/>);await screen.findByText('Simulation result');
 fireEvent.click(screen.getByRole('button',{name:'Use my business data'}));
 await screen.findByText('Your workspace records');
 await waitFor(()=>expect(fetchMock.mock.calls.filter(([url])=>url.endsWith('/simulate')).length).toBe(2));
 const call=fetchMock.mock.calls.filter(([url])=>url.endsWith('/simulate'))[1];
 expect(JSON.parse(call[1].body).use_demo).toBe(false);
 expect(JSON.parse(call[1].body).receipt_overrides).toEqual([]);
});

it('hides cash write controls for a viewer and shows model evidence',async()=>{
 render(<DecisionLab {...props} workspace={{...props.workspace,role:'viewer'}}/>);await screen.findByText('Simulation result');
 fireEvent.click(screen.getByRole('button',{name:'Cash history'}));
 expect(screen.queryByRole('button',{name:'Save cash entry'})).toBeNull();
 expect(screen.queryByLabelText('Import cash-history CSV')).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'Model evidence'}));
 expect(screen.getByText('Synthetic model evidence')).toBeTruthy();
});

it('reports server failures instead of inventing a projection',async()=>{
 fetchMock.mockResolvedValue({ok:false,json:async()=>({detail:'Forbidden'})});
 render(<DecisionLab {...props}/>);
 expect((await screen.findByRole('alert')).textContent).toContain('Forbidden');
 expect(screen.queryByText('Simulation result')).toBeNull();
});
