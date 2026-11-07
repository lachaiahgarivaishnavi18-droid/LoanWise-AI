import {useEffect,useState} from 'react'
import {api,errorText} from '../api'
import type {Doc} from '../types'
import {ErrorBox} from './ui'

export function PolicyPermissions({document,onUpdate}:{document:Doc;onUpdate:(document:Doc)=>void}) {
  const [admin,setAdmin]=useState(false),[selected,setSelected]=useState<string[]>(document.permissions||[]),[error,setError]=useState(''),[saved,setSaved]=useState(false)
  useEffect(()=>{api.get('/auth/me').then(r=>setAdmin(r.data.role==='admin')).catch(()=>{})},[])
  if(!admin)return null
  return <div className="evidence"><h3>Policy source access</h3><p>Source permissions apply to retrieval and historical evidence. Administrators retain access.</p><div className="checks">{['analyst','reviewer'].map(role=><label key={role}><input type="checkbox" checked={selected.includes(role)} onChange={e=>{setSaved(false);setSelected(v=>e.target.checked?[...v,role]:v.filter(r=>r!==role))}}/>{role}</label>)}</div><button className="secondary" style={{marginTop:12}} onClick={async()=>{try{const r=await api.put(`/documents/${document.id}/permissions`,{roles:['admin',...selected.filter(r=>r!=='admin')]});onUpdate({...document,permissions:r.data.roles});setSaved(true)}catch(e){setError(errorText(e))}}}>Save source access</button>{saved&&<p role="status">Source permissions saved and audited.</p>}<ErrorBox text={error}/></div>
}
