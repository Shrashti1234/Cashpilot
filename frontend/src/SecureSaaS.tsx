import {UserManager,WebStorageStateStore,type User} from 'oidc-client-ts';
import React,{useEffect,useState} from 'react';
import {LogIn,LogOut,RefreshCw} from 'lucide-react';
import {WorkspaceOnboarding} from './WorkspaceOnboarding';
import {CustomerManagement,type BusinessWorkspace} from './CustomerManagement';

type Config={apiUrl:string;issuer:string;clientId:string;scope:string};
function managerFor(config:Config){
 return new UserManager({
  authority:config.issuer,client_id:config.clientId,
  redirect_uri:window.location.origin+window.location.pathname,
  post_logout_redirect_uri:window.location.origin+window.location.pathname,
  response_type:'code',scope:config.scope,
  // Tokens remain in memory; PKCE transaction state is temporary session storage.
  userStore:new WebStorageStateStore({store:new InMemoryStore()}),
  stateStore:new WebStorageStateStore({store:window.sessionStorage}),
  automaticSilentRenew:false,
 });
}
class InMemoryStore implements Storage{
 private values=new Map<string,string>();
 get length(){return this.values.size;}
 clear(){this.values.clear();}
 getItem(key:string){return this.values.get(key)??null;}
 key(index:number){return Array.from(this.values.keys())[index]??null;}
 removeItem(key:string){this.values.delete(key);}
 setItem(key:string,value:string){this.values.set(key,value);}
}
export function SecureSaaS({config}: {config:Config}){
 const [manager]=useState(()=>managerFor(config));
 const [user,setUser]=useState<User|null>(null);
 const [workspace,setWorkspace]=useState<BusinessWorkspace|null>(null);
 const [loading,setLoading]=useState(true);
 const [error,setError]=useState('');
 useEffect(()=>{
  let active=true;
  async function initialize(){
   try{
    if(window.location.search.includes('code=')&&window.location.search.includes('state=')){
     const result=await manager.signinRedirectCallback();
     window.history.replaceState({},document.title,window.location.pathname);
     if(active)setUser(result);
    }else{
     const existing=await manager.getUser();
     if(active)setUser(existing&&!existing.expired?existing:null);
    }
   }catch(e){if(active)setError(e instanceof Error?e.message:'Login failed');}
   finally{if(active)setLoading(false);}
  }
  void initialize();
  return()=>{active=false;};
 },[manager]);
 async function login(){
  setError('');
  try{await manager.signinRedirect();}catch(e){setError(e instanceof Error?e.message:'Login failed');}
 }
 async function logout(){
  setWorkspace(null);setUser(null);
  try{await manager.removeUser();await manager.signoutRedirect();}catch(e){setError(e instanceof Error?e.message:'Logout failed');}
 }
 if(loading)return <div className="workspace-screen"><div className="workspace-content"><RefreshCw size={22}/> Establishing secure session…</div></div>;
 if(!user||user.expired)return <div className="workspace-screen"><div className="workspace-top"><div className="workspace-brand">CashPilot</div></div><div className="workspace-content"><span className="eyebrow">SECURE WORKSPACE</span><h1>Welcome to CashPilot</h1><p>Sign in securely to manage your businesses, customers and invoices.</p>{error&&<div className="error" role="alert">{error}</div>}<button className="primary" onClick={()=>void login()}><LogIn size={17}/>Sign in</button></div></div>;
 return <><div className="saas-session-bar"><span>Signed in securely</span><button className="workspace-secondary" onClick={()=>void logout()}><LogOut size={16}/>Sign out</button></div>{workspace
  ?<CustomerManagement apiUrl={config.apiUrl} accessToken={user.access_token} workspace={workspace} onBack={()=>setWorkspace(null)}/>
  :<WorkspaceOnboarding apiUrl={config.apiUrl} accessToken={user.access_token} onSelect={setWorkspace}/>}</>;
}
