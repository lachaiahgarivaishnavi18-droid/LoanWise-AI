import {useEffect,useState} from 'react'
import {api,errorText} from '../api'
import type {Risk} from '../types'
import {Panel,Empty,ErrorBox,Badge} from './ui'

interface Snapshot extends Risk {prediction_id:number;timestamp:string;assessment_id:number|null}
export function PredictionHistory({applicationId,onSelect}:{applicationId:number;onSelect:(risk:Risk)=>void}) {
  const [rows,setRows]=useState<Snapshot[]>([]),[error,setError]=useState('')
  useEffect(()=>{api.get(`/credit-risk/${applicationId}/history`).then(r=>setRows(r.data)).catch(e=>setError(errorText(e)))},[applicationId])
  return <Panel title="Prediction & explanation history" subtitle="Persisted model snapshots · Selecting a row does not rerun a model"><ErrorBox text={error}/>{!rows.length?<Empty>No stored predictions yet. Run an assessment to create a snapshot.</Empty>:<div className="list">{rows.map(row=><button key={row.prediction_id} onClick={()=>onSelect(row)}><span><b>{row.model_name} · {row.version}</b><small>{new Date(row.timestamp).toLocaleString()} · {row.assessment_id?'Assessment #'+row.assessment_id:'Standalone prediction'}</small></span><Badge tone="amber">{row.category}</Badge><b>{row.score==null?'Unavailable':row.score.toFixed(3)}</b></button>)}</div>}</Panel>
}
