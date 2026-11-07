import {useState} from 'react'
import {api,errorText} from '../api'
import type {Product} from '../types'
import {Panel,ErrorBox} from './ui'

export function ProductProvisioner({onCreated}:{onCreated:(product:Product)=>void}) {
  const [error,setError]=useState(''),[busy,setBusy]=useState(false)
  return <Panel title="Add a loan product" subtitle="A product remains unconfigured until reviewed, versioned policy criteria are assigned."><form className="form-grid padded" onSubmit={async e=>{e.preventDefault();const form=e.currentTarget;setBusy(true);setError('');try{const result=await api.post('/products',Object.fromEntries(new FormData(form)));onCreated(result.data);form.reset()}catch(e){setError(errorText(e))}finally{setBusy(false)}}}><label>Product name<input name="name" required minLength={2} maxLength={100}/></label><label>Jurisdiction<input name="jurisdiction" required minLength={2} maxLength={100}/></label><label>Initial policy version<input name="policy_version" defaultValue="1" required maxLength={100}/></label><label>Product description<input name="description" required minLength={5} maxLength={1000}/></label><div><button className="primary" disabled={busy}>Create loan product</button></div><ErrorBox text={error}/></form></Panel>
}
