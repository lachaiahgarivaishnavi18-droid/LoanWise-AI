import { useEffect, useState, useCallback, lazy, Suspense, type ReactNode } from 'react'
import { Routes, Route, Navigate, NavLink, Link, useNavigate, useLocation } from 'react-router-dom'
import { LayoutDashboard, Users, FileText, ScanLine, ChartNoAxesCombined, ShieldCheck, Network, Library, MessagesSquare, Settings2, ArrowUpRight, ArrowRight, Plus, Search, Bell, ChevronDown, LogOut, Download, Loader2, Check, CircleHelp, Menu, X, Sparkles, Clock3, Activity, Landmark, SlidersHorizontal, RefreshCw, Upload, CheckCircle2 } from 'lucide-react'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, PieChart, Pie, Cell, AreaChart, Area, ReferenceLine } from 'recharts'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { api, errorText, money, exportJSON } from './api'
import type { User, Product, Application, Assessment, Doc, Risk, Evidence } from './types'

import { Busy, Badge } from './components/ui'
const Auth = lazy(() => import('./pages/Auth').then(m => ({default: m.Auth})))
const Dashboard = lazy(() => import('./pages/Dashboard').then(m => ({default: m.Dashboard})))
const Applications = lazy(() => import('./pages/Applications').then(m => ({default: m.Applications})))
const Applicants = lazy(() => import('./pages/Applicants').then(m => ({default: m.Applicants})))
const ApplicationForm = lazy(() => import('./pages/ApplicationForm').then(m => ({default: m.ApplicationForm})))
const AssessmentWorkspace = lazy(() => import('./pages/AssessmentWorkspace').then(m => ({default: m.AssessmentWorkspace})))
const Analysis = lazy(() => import('./pages/Analysis').then(m => ({default: m.Analysis})))
const Documents = lazy(() => import('./pages/Documents').then(m => ({default: m.Documents})))
const Assistant = lazy(() => import('./pages/Assistant').then(m => ({default: m.Assistant})))
const Reviews = lazy(() => import('./pages/Reviews').then(m => ({default: m.Reviews})))
const Reports = lazy(() => import('./pages/Reports').then(m => ({default: m.Reports})))
const Agents = lazy(() => import('./pages/Agents').then(m => ({default: m.Agents})))
const Settings = lazy(() => import('./pages/Settings').then(m => ({default: m.Settings})))
const navigation = [
  {label:'Overview',items:[['Dashboard','/dashboard',LayoutDashboard],['Applicants','/applicants',Users],['Applications','/applications',FileText]]},
  {label:'Intelligence',items:[['Document intelligence','/documents',ScanLine],['Financial analysis','/financial',ChartNoAxesCombined],['Credit risk','/risk',ShieldCheck],['Explainability','/explainability',Sparkles],['Knowledge base','/knowledge',Library],['AI assessment','/assessment',Network],['Financial assistant','/assistant',MessagesSquare]]},
  {label:'Governance',items:[['Human review','/reviews',CheckCircle2],['Reports & analytics','/reports',ChartNoAxesCombined],['Agent monitoring','/agents',Activity],['Settings','/settings',Settings2]]},
]
function SystemHealth() {
  const [healthy,setHealthy]=useState<boolean|null>(null),[demo,setDemo]=useState<boolean|null>(null)
  useEffect(()=>{const check=()=>api.get('/health').then(r=>{setHealthy(r.data.status==='ok');setDemo(Boolean(r.data.demo_mode))}).catch(()=>setHealthy(false));check();const timer=setInterval(check,60000);return()=>clearInterval(timer)},[])
  return <><span className="live-dot" style={{background:healthy===false?'#bd8c65':undefined}}/>{healthy===null?'Checking system health':healthy?'Backend operational':'Backend unavailable'}<Badge tone={demo?'amber':'neutral'}>{demo?'SYNTHETIC DEMO':'RESEARCH PROTOTYPE'}</Badge></>
}

export default function App() {
  const [user,setUser]=useState<User|null>(null),[loading,setLoading]=useState(true),[mobile,setMobile]=useState(false)
  const location=useLocation()
  useEffect(()=>{api.get('/auth/me').then(r=>setUser(r.data)).finally(()=>setLoading(false)).catch(()=>{})},[])
  useEffect(()=>setMobile(false),[location.pathname])
  if(loading)return <Busy/>
  if(!user)return <Suspense fallback={<Busy/>}><Auth onLogin={setUser}/></Suspense>
  const title=navigation.flatMap(n=>n.items).find(i=>i[1]===location.pathname)?.[0]||'Dashboard'
  return <div className="app"><aside className={'sidebar '+(mobile?'open':'')}><Link to="/dashboard" className="brand"><span className="brand-icon"><Landmark size={24}/></span><span>loanwise<span className="brand-ai">AI</span><small>CREDIT INTELLIGENCE</small></span></Link><div className="workspace"><span className="workspace-logo">LW</span><span>Research workspace<small>Research environment</small></span></div><nav>{navigation.map(group=><div className="nav-group" key={group.label}><p>{group.label}</p>{group.items.map(([label,path,Icon])=><NavLink key={String(path)} to={String(path)}><Icon size={18}/><span>{String(label)}</span>{label==='AI assessment'&&<span className="nav-new">AI</span>}</NavLink>)}</div>)}</nav><div className="sidebar-bottom"><div className="oversight"><ShieldCheck size={19}/><b>Human judgment, amplified.</b><p>Evidence to support every review. Final decisions stay with you.</p></div><button className="user" onClick={()=>api.post('/auth/logout').then(()=>setUser(null))}><span className="avatar">{user.name.split(' ').map(s=>s[0]).slice(0,2).join('')}</span><span><b>{user.name}</b><small>{user.role}</small></span><LogOut size={16}/></button></div></aside>{mobile&&<div className="scrim" onClick={()=>setMobile(false)}/>}<div className="main-shell"><header><button className="icon-button mobile-menu" onClick={()=>setMobile(!mobile)} aria-label="Toggle navigation"><Menu/></button><div className="breadcrumb">Workspace <span>/</span> <b>{String(title)}</b></div><div className="header-right"><SystemHealth/><Link to="/reviews" className="icon-button" aria-label="Review notifications"><Bell size={19}/></Link><span className="avatar small">{user.name[0]}</span></div></header><main><Suspense fallback={<Busy/>}><Routes><Route path="/" element={<Navigate to="/dashboard" replace/>}/><Route path="/dashboard" element={<Dashboard user={user}/>}/><Route path="/applications" element={<Applications/>}/><Route path="/applications/new" element={<ApplicationForm/>}/><Route path="/applicants" element={<Applicants/>}/><Route path="/documents" element={<Documents/>}/><Route path="/knowledge" element={<Documents policy/>}/><Route path="/financial" element={<Analysis mode="financial"/>}/><Route path="/risk" element={<Analysis mode="risk"/>}/><Route path="/explainability" element={<Analysis mode="explainability"/>}/><Route path="/assessment" element={<AssessmentWorkspace user={user}/>}/><Route path="/assistant" element={<Assistant/>}/><Route path="/reviews" element={<Reviews user={user}/>}/><Route path="/reports" element={<Reports/>}/><Route path="/agents" element={<Agents/>}/><Route path="/settings" element={<Settings user={user}/>}/><Route path="*" element={<Dashboard user={user}/>}/></Routes></Suspense><footer><span>LoanWise AI <span> / </span> Explainable credit decision support</span><span>Research prototype · Human review required</span></footer></main></div></div>
}

