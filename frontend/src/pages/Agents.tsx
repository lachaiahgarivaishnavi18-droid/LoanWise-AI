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
export function Agents() {
  const [items,setItems]=useState<any[]>([]),[error,setError]=useState(''),[selected,setSelected]=useState<any>(null)
  const load=()=>api.get('/agents/executions').then(r=>setItems(r.data)).catch(e=>setError(errorText(e)))
  useEffect(()=>{load()},[])
  return <><Heading title="Agent operations" description="Inspect LangGraph execution traces, structured outputs, retries, and timing." action={<button className="secondary" onClick={load}><RefreshCw size={16}/>Refresh</button>}/><ErrorBox text={error}/><Panel title="Assessment workflow" subtitle="Sequential, evidence-preserving orchestration"><div className="workflow">{['Understand','Documents','Financial profile','Credit history','Retrieve policies','Risk model','Explain SHAP','Evaluate criteria','Validate evidence','Generate report','Human review','Orchestrate'].map((n,i)=><div key={n}><span>{String(i+1).padStart(2,'0')}</span>{n}<ArrowRight size={14}/></div>)}</div></Panel><div className="two-col"><Panel title="Execution history" subtitle="Most recent 100 agent executions"><div className="list">{items.map(a=><button key={a.id} onClick={()=>setSelected(a)}><span className="file-icon"><Network size={18}/></span><span><b>{a.name}</b><small>Application #{a.application_id} · {a.duration_ms} ms · {a.retries} retries</small></span><Badge tone={statusTone(a.status)}>{a.status}</Badge></button>)}</div>{!items.length&&<Empty>Run an assessment to populate execution history.</Empty>}</Panel><Panel title="Structured agent output" subtitle="Only authorized application traces are visible">{selected?<pre className="json-output">{JSON.stringify(selected,null,2)}</pre>:<Empty>Select an execution to inspect its output.</Empty>}</Panel></div></>
}

