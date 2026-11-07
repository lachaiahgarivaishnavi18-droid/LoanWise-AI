import { useEffect, useState, useCallback, type ReactNode } from 'react'
import { Routes, Route, NavLink, Link, useNavigate, useLocation } from 'react-router-dom'
import { LayoutDashboard, Users, FileText, ScanLine, ChartNoAxesCombined, ShieldCheck, Network, Library, MessagesSquare, Settings2, ArrowUpRight, ArrowRight, Plus, Search, Bell, ChevronDown, LogOut, Download, Loader2, Check, CircleHelp, Menu, X, Sparkles, Clock3, Activity, Landmark, SlidersHorizontal, RefreshCw, Upload, CheckCircle2 } from 'lucide-react'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, PieChart, Pie, Cell, AreaChart, Area, ReferenceLine } from 'recharts'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { api, errorText, money, exportJSON } from '../api'
import type { User, Product, Application, Assessment, Doc, Risk, Evidence } from '../types'

import { Badge, Empty, Busy, ErrorBox, Panel, Heading, Stat, ApplicationTable, EvidenceCards, statusTone, colors } from '../components/ui'
export function Applications() {
  const [items,setItems]=useState<Application[]>([]),[q,setQ]=useState(''),[page,setPage]=useState(1),[total,setTotal]=useState(0),[error,setError]=useState(''),[loading,setLoading]=useState(true)
  useEffect(()=>{setLoading(true);api.get('/applications',{params:{q,page}}).then(r=>{setItems(r.data.items);setTotal(r.data.total)}).catch(e=>setError(errorText(e))).finally(()=>setLoading(false))},[q,page])
  return <><Heading title="Application workspace" description="Manage applications and trace each assessment to its evidence." action={<Link className="primary" to="/applications/new"><Plus size={17}/>New application</Link>}/><Panel title="All applications" subtitle={`${total} authorized records · Synthetic demo`} action={<div className="search"><Search size={16}/><input aria-label="Search applications" placeholder="Search name or reference" value={q} onChange={e=>{setQ(e.target.value);setPage(1)}}/></div>}><ErrorBox text={error}/>{loading?<Busy/>:<ApplicationTable items={items}/>}<div className="pagination"><span>Page {page} · {total} records</span><button disabled={page===1} onClick={()=>setPage(page-1)}>Previous</button><button disabled={page*25>=total} onClick={()=>setPage(page+1)}>Next</button></div></Panel></>
}

