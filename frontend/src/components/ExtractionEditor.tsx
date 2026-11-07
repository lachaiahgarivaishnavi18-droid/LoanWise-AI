import { useState } from 'react'
import { api, errorText } from '../api'
import type { Doc } from '../types'
import { ErrorBox } from './ui'

export function ExtractionEditor({document,onUpdate}:{document:Doc;onUpdate:(document:Doc)=>void}) {
  const [error,setError]=useState(''),[editing,setEditing]=useState<number|null>(null),[value,setValue]=useState(''),[reason,setReason]=useState(''),[busy,setBusy]=useState(false)
  return <div>{document.extraction.entities.map((entity,index)=><div className="evidence" key={index}><div><b>{entity.field}: {entity.value}</b>{document.kind==='financial'&&<button className="secondary" onClick={()=>{setEditing(index);setValue(String(entity.value));setReason('')}}>Correct candidate</button>}</div><small>Page {entity.page} · Original source quote: {entity.quote} · Not verified application data</small>{editing===index&&<form className="stack" style={{marginTop:16}} onSubmit={async e=>{e.preventDefault();setBusy(true);try{const r=await api.put(`/documents/${document.id}/entities/${index}`,{value:Number(value),reason});onUpdate(r.data);setEditing(null)}catch(e){setError(errorText(e))}finally{setBusy(false)}}}><label>Corrected candidate value<input type="number" value={value} onChange={e=>setValue(e.target.value)} min="0" step="any" required/></label><label>Correction reason<input value={reason} onChange={e=>setReason(e.target.value)} required minLength={5}/></label><button className="primary" disabled={busy}>Save correction & preserve original quote</button></form>}</div>)}<ErrorBox text={error}/></div>
}
