import React from 'react';
import {ArrowLeft, LayoutDashboard} from 'lucide-react';
import {accessibleWorkspaceGroups,type Destination} from './workspaceSections';
import './workspaceNavigation.css';

export function WorkspaceNavigation({name,role,current,onNavigate,onSwitch}:{
 name:string;role:string;current:Destination;onNavigate:(section:Destination)=>void;onSwitch:()=>void;
}){
 const groups=accessibleWorkspaceGroups(role);
 return <aside className="business-nav" aria-label="Current business">
  <div className="business-nav-brand"><LayoutDashboard size={21} aria-hidden="true"/>CashPilot</div>
  <div className="business-nav-context"><strong>{name}</strong><span>{role==='viewer'?'Read only':role}</span></div>
  <nav className="business-nav-links" aria-label="Business sections">
   <button type="button" aria-current={current==='overview'?'page':undefined} onClick={()=>onNavigate('overview')}>Business overview</button>
   {groups.map(group=><div key={group.label} className="business-nav-group">
    <h2>{group.label}</h2>
    {group.items.map(item=><button type="button" key={item.id} aria-current={current===item.id?'page':undefined} onClick={()=>onNavigate(item.id)}>{item.label}</button>)}
   </div>)}
  </nav>
  <label className="business-nav-mobile">Business section<select aria-label="Business section" value={current} onChange={event=>{
   const value=event.currentTarget.value;
   if(value==='overview'){onNavigate(value);return;}
   for(const group of groups){const item=group.items.find(item=>item.id===value);if(item){onNavigate(item.id);return;}}
  }}><option value="overview">Business overview</option>{groups.map(group=><optgroup key={group.label} label={group.label}>{group.items.map(item=><option value={item.id} key={item.id}>{item.label}</option>)}</optgroup>)}</select></label>
  <button type="button" className="business-nav-switch" onClick={onSwitch}><ArrowLeft size={16} aria-hidden="true"/>Switch business</button>
 </aside>;
}
