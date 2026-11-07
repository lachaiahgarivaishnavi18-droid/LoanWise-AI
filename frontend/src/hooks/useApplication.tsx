import { useEffect, useState, useCallback, type ReactNode } from 'react'
import { Routes, Route, NavLink, Link, useNavigate, useLocation } from 'react-router-dom'
import { LayoutDashboard, Users, FileText, ScanLine, ChartNoAxesCombined, ShieldCheck, Network, Library, MessagesSquare, Settings2, ArrowUpRight, ArrowRight, Plus, Search, Bell, ChevronDown, LogOut, Download, Loader2, Check, CircleHelp, Menu, X, Sparkles, Clock3, Activity, Landmark, SlidersHorizontal, RefreshCw, Upload, CheckCircle2 } from 'lucide-react'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, PieChart, Pie, Cell, AreaChart, Area, ReferenceLine } from 'recharts'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { api, errorText, money, exportJSON } from '../api'
import type { User, Product, Application, Assessment, Doc, Risk, Evidence } from '../types'

export function useApplication() {
  const location=useLocation(),navigate=useNavigate(),id=new URLSearchParams(location.search).get('application')
  const [apps,setApps]=useState<Application[]>([]),[selected,setSelected]=useState<Application|null>(null),[error,setError]=useState('')
  useEffect(()=>{api.get('/applications',{params:{limit:100}}).then(r=>setApps(r.data.items)).catch(e=>setError(errorText(e)))},[])
  useEffect(()=>{if(id)api.get('/applications/'+id).then(r=>setSelected(r.data)).catch(e=>setError(errorText(e)));else setSelected(null)},[id])
  const picker=<div className="application-picker"><FileText size={18}/><select aria-label="Select application" value={id||''} onChange={e=>navigate(location.pathname+'?application='+e.target.value)}><option value="">Select an application to begin</option>{selected&&!apps.find(a=>a.id===selected.id)&&<option value={selected.id}>{selected.reference} · {selected.applicant_name}</option>}{apps.map(a=><option key={a.id} value={a.id}>{a.reference} · {a.applicant_name} · {a.product_name}</option>)}</select>{selected&&<Link className="subtle-link" to={'/applications/new?edit='+selected.id}>Edit profile<ArrowUpRight size={15}/></Link>}</div>
  return {selected,picker,error}
}

