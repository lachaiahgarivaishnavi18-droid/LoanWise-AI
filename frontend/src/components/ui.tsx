import { useEffect, useState, useCallback, type ReactNode } from 'react'
import { Routes, Route, NavLink, Link, useNavigate, useLocation } from 'react-router-dom'
import { LayoutDashboard, Users, FileText, ScanLine, ChartNoAxesCombined, ShieldCheck, Network, Library, MessagesSquare, Settings2, ArrowUpRight, ArrowRight, Plus, Search, Bell, ChevronDown, LogOut, Download, Loader2, Check, CircleHelp, Menu, X, Sparkles, Clock3, Activity, Landmark, SlidersHorizontal, RefreshCw, Upload, CheckCircle2 } from 'lucide-react'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, PieChart, Pie, Cell, AreaChart, Area, ReferenceLine } from 'recharts'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { api, errorText, money, exportJSON } from '../api'
import type { User, Product, Application, Assessment, Doc, Risk, Evidence } from '../types'

export const colors=['#245e4c','#7fae96','#c2d8bc','#e5ba79','#a0b4b0']
export function Badge({children,tone='neutral'}:{children:ReactNode;tone?:string}) {return <span className={'badge '+tone}>{children}</span>}
export function Empty({children}:{children:ReactNode}) {return <div className="empty"><CircleHelp size={25}/><p>{children}</p></div>}
export function Busy() {return <div className="empty"><Loader2 className="spin"/>Loading workspace…</div>}
export function ErrorBox({text}:{text:string}) {return text ? <div className="error" role="alert">{text}</div> : null}
export function Panel({title,subtitle,children,action,className=''}:{title:string;subtitle?:string;children:ReactNode;action?:ReactNode;className?:string}) {return <section className={'panel '+className}><div className="panel-head"><div><h2>{title}</h2>{subtitle&&<p>{subtitle}</p>}</div>{action}</div>{children}</section>}
export function Heading({eyebrow='WORKSPACE',title,description,action}:{eyebrow?:string;title:string;description:string;action?:ReactNode}) {return <div className="page-heading"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{action}</div>}
export function Stat({label,value,detail,icon}:{label:string;value:ReactNode;detail:string;icon:ReactNode}) {return <div className="stat"><div className="stat-top">{label}{icon}</div><strong>{value}</strong><span>{detail}</span></div>}
export function statusTone(status:string) {return status==='SATISFIED'||status==='completed'?'green':status.includes('CONFLICT')||status==='NOT_SATISFIED'?'red':'amber'}
export function ApplicationTable({items}:{items:Application[]}) {return <div className="table-scroll"><table><thead><tr><th>Applicant</th><th>Loan product</th><th>Requested amount</th><th>Assessment status</th><th/></tr></thead><tbody>{items.map(a=><tr key={a.id}><td><Link className="person" to={'/assessment?application='+a.id}><span className="avatar small">{a.applicant_name.split(' ').map(s=>s[0]).slice(0,2).join('')}</span><span><b>{a.applicant_name}</b><small>{a.reference} · Synthetic</small></span></Link></td><td>{a.product_name}</td><td className="tabular">{money(a.amount)}</td><td><Badge tone={statusTone(a.status)}>{a.status.replace('ELIGIBILITY CONDITIONS SATISFIED — HUMAN REVIEW REQUIRED','Conditions satisfied · Review required').replaceAll('_',' ')}</Badge></td><td><Link aria-label={'Open application '+a.id} to={'/assessment?application='+a.id}><ArrowUpRight size={17}/></Link></td></tr>)}</tbody></table>{!items.length&&<Empty>No applications match your search.</Empty>}</div>}
export function EvidenceCards({items}:{items:Evidence[]}) {return <div className="evidence-list">{items.map(e=><div className="evidence" key={e.chunk_id}><div><FileText size={17}/><b>{e.title}</b><Badge tone="green">Source {e.chunk_id}</Badge></div><p>{e.text}</p><small>Page {e.page} · {e.version} · Effective {e.effective_date} · {e.synthetic?'Synthetic policy':'Reviewed policy'}</small></div>)}{!items.length&&<Empty>No supporting policy evidence found.</Empty>}</div>}

