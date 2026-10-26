// @vitest-environment jsdom
import React from 'react';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {RecurringDocuments} from './RecurringDocuments';
import type {TradeDoc} from './operationsTypes';

afterEach(cleanup);
const doc={id:'source',kind:'invoice',number:'INV-T',status:'issued',party:{name:'Buyer'}} as TradeDoc;

it('creates a series against an explicit invoice snapshot and leaves issuance separate',async()=>{
 const write=vi.fn().mockResolvedValue(undefined);render(<RecurringDocuments documents={[doc]} rules={[]} busy={false} canAdmin canWrite write={write}/>);
 fireEvent.change(screen.getByLabelText('Invoice document template'),{target:{value:'source'}});fireEvent.change(screen.getByLabelText('Series name'),{target:{value:'Monthly advisory'}});fireEvent.change(screen.getByLabelText('Unique series prefix'),{target:{value:'AD'}});fireEvent.change(screen.getByLabelText('First scheduled date'),{target:{value:'2026-01-31'}});fireEvent.click(screen.getByRole('button',{name:'Create recurring series'}));
 await waitFor(()=>expect(write).toHaveBeenCalledTimes(1));expect(write.mock.calls[0][0]).toBe('/recurring');expect(write.mock.calls[0][1]).toMatchObject({source_document_id:'source',frequency:'monthly',start_date:'2026-01-31',prefix:'AD'});
 expect(screen.getByText(/There is no background scheduler running yet/)).toBeTruthy();
});

it('runs only the bounded generation endpoint and hides mutation controls for viewers',async()=>{
 const write=vi.fn().mockResolvedValue(undefined);const {rerender}=render(<RecurringDocuments documents={[doc]} rules={[]} busy={false} canAdmin={false} canWrite write={write}/>);
 expect(screen.queryByRole('button',{name:'Create recurring series'})).toBeNull();fireEvent.click(screen.getByRole('button',{name:'Generate due drafts'}));
 expect(write.mock.calls[0][0]).toBe('/recurring/generate');rerender(<RecurringDocuments documents={[doc]} rules={[]} busy={false} canAdmin={false} canWrite={false} write={write}/>);expect(screen.queryByRole('button',{name:'Generate due drafts'})).toBeNull();
});
