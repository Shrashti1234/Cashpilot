// @vitest-environment jsdom
import React from 'react';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {BusinessOverview} from './BusinessOverview';

vi.mock('recharts',()=>({ResponsiveContainer:()=>null,Bar:()=>null,BarChart:()=>null,CartesianGrid:()=>null,Legend:()=>null,Tooltip:()=>null,XAxis:()=>null,YAxis:()=>null}));
const summary={customer_count:1,invoice_count:2,outstanding_paise:6000,overdue_paise:6000,due_next_7_days_paise:0,customer_credit_paise:2000,recorded_inflow_paise:8500,recorded_outflow_paise:3000,net_recorded_cash_paise:5500,open_disputes:1,drafts_to_review:1,low_stock_count:1};
const data={as_of:'2026-10-26',window_start:'2026-09-27',summary,aging:{not_due:0,'1_30':6000,'31_60':0,'61_90':0,over_90:0},top_customers:[{id:'c',name:'Buyer',outstanding_paise:6000,share:1}],cash_activity:[],operating_expenses_by_month:[],expense_dates_in_window:1,low_stock:[{id:'p',sku:'LOW',name:'Widget',stock_milliunits:0,reorder_milliunits:1000,unit:'NOS'}],attention:[{code:'stock',title:'Stock ledger needs attention',detail:'One product needs review.',section:'operations'}],notes:['Only recorded actual cash is included.']};
const props={apiUrl:'https://api.test',accessToken:'fixture-token',workspace:{id:'a',name:'Shop',mode:'b2b' as const,role:'owner'},onBack:vi.fn(),onOpen:vi.fn()};
const fetchMock=vi.fn();
beforeEach(()=>{fetchMock.mockReset();vi.stubGlobal('fetch',fetchMock);fetchMock.mockResolvedValue({ok:true,json:async()=>data});});
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.clearAllMocks();});

it('shows recorded cash changes and actual receivables rather than inventing a bank balance',async()=>{
 render(<BusinessOverview {...props}/>);await screen.findByText('₹55.00');expect(screen.getByText(/not a reconciled bank balance/)).toBeTruthy();expect(screen.getByText('Buyer')).toBeTruthy();expect(screen.getByText('1–30 days overdue')).toBeTruthy();
 expect(fetchMock.mock.calls[0][0]).toBe('https://api.test/api/v1/organizations/a/dashboard');expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe('Bearer fixture-token');
});

it('opens the relevant workspace module and keeps team controls hidden from viewers',async()=>{
 render(<BusinessOverview {...props} workspace={{...props.workspace,role:'viewer'}}/>);await screen.findByText('₹55.00');
 expect(screen.queryByRole('button',{name:/Team & access/})).toBeNull();fireEvent.click(screen.getByRole('button',{name:'Manage cash records'}));expect(props.onOpen).toHaveBeenLastCalledWith('cash');
 fireEvent.click(screen.getByRole('button',{name:/Stock ledger needs attention/}));expect(props.onOpen).toHaveBeenLastCalledWith('operations');
});

it('does not render made-up metrics after an API failure',async()=>{
 fetchMock.mockResolvedValue({ok:false,json:async()=>({detail:'Forbidden'})});render(<BusinessOverview {...props}/>);expect((await screen.findByRole('alert')).textContent).toContain('Forbidden');expect(screen.queryByText('₹55.00')).toBeNull();
});
