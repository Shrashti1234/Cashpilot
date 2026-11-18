// @vitest-environment jsdom
import React from 'react';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {TeamSettings} from './TeamSettings';
import {JoinBusiness} from './JoinBusiness';

const team={actor_id:'owner',actor_role:'owner',members:[{user_id:'owner',role:'owner',active:true},{user_id:'viewer',role:'viewer',active:true}],invitations:[]};
const token='a'.repeat(43),fetchMock=vi.fn();
const props={apiUrl:'https://api.test',accessToken:'fixture-token',workspace:{id:'a',name:'Shop',mode:'b2b' as const,role:'owner'},onBack:vi.fn(),onOwnAccessChanged:vi.fn()};
beforeEach(()=>{vi.stubGlobal('fetch',fetchMock);fetchMock.mockReset();fetchMock.mockImplementation(async(url:string,options?:RequestInit)=>({ok:true,json:async()=>options?.method==='POST'?{id:'invite',token,target_user_id:'recipient',expires_at:'2030-01-01T00:00:00Z'}:url.endsWith('/me')?{user_id:'recipient'}:team}));});
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.clearAllMocks();});

it('creates a private account-bound invitation without sending a message',async()=>{
 render(<TeamSettings {...props}/>);await screen.findByText('Invite an account');
 fireEvent.change(screen.getByLabelText('Recipient account code'),{target:{value:'recipient'}});fireEvent.change(screen.getByLabelText('Invitation role'),{target:{value:'admin'}});fireEvent.click(screen.getByRole('button',{name:'Create private invitation'}));
 await screen.findByLabelText('Private invitation code');const input=screen.getByLabelText('Private invitation code') as HTMLInputElement;
 expect(input.type).toBe('password');expect(input.value).toBe(token);expect(screen.queryByText(token)).toBeNull();
 const calls=fetchMock.mock.calls.filter(([,args])=>args?.method==='POST');expect(calls).toHaveLength(1);expect(calls[0][0]).toMatch(/\/team\/invitations$/);expect(JSON.parse(calls[0][1].body)).toEqual({target_user_id:'recipient',role:'admin'});
});

it('administrators cannot use owner/admin controls',async()=>{
 fetchMock.mockResolvedValue({ok:true,json:async()=>({...team,actor_id:'admin',actor_role:'admin'})});render(<TeamSettings {...props} workspace={{...props.workspace,role:'admin'}}/>);await screen.findByText('Invite an account');
 expect(screen.queryByLabelText('Role for owner')).toBeNull();const options=Array.from((screen.getByLabelText('Invitation role') as HTMLSelectElement).options).map(o=>o.value);expect(options).toEqual(['accountant','viewer']);
});

it('returns to workspace selection after changing its own access',async()=>{
 render(<TeamSettings {...props}/>);await screen.findByText('Invite an account');fireEvent.change(screen.getByLabelText('Role for owner'),{target:{value:'admin'}});fireEvent.click(screen.getByRole('button',{name:'Save access for owner'}));
 await waitFor(()=>expect(props.onOwnAccessChanged).toHaveBeenCalledTimes(1));
});

it('accepts an invitation with the signed-in account and clears the private code',async()=>{
 const onJoined=vi.fn();fetchMock.mockImplementation(async(url:string)=>({ok:true,json:async()=>url.endsWith('/me')?{user_id:'recipient'}:{organization:{id:'joined',name:'Invited business',mode:'b2b',role:'accountant'}}}));render(<JoinBusiness apiUrl={props.apiUrl} accessToken={props.accessToken} onJoined={onJoined}/>);
 await screen.findByLabelText('Your account code');fireEvent.change(screen.getByLabelText('Invitation code'),{target:{value:token}});fireEvent.click(screen.getByRole('button',{name:'Accept invitation'}));await waitFor(()=>expect(onJoined).toHaveBeenCalledWith({id:'joined',name:'Invited business',mode:'b2b',role:'accountant'}));expect((screen.getByLabelText('Invitation code') as HTMLInputElement).value).toBe('');
 const call=fetchMock.mock.calls.find(([,args])=>args?.method==='POST')!;expect(call[1].headers.Authorization).toBe('Bearer fixture-token');expect(JSON.parse(call[1].body)).toEqual({token});
});
