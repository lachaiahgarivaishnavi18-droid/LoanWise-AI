// @vitest-environment jsdom
import { afterEach, describe, it, expect, vi } from 'vitest'
import { cleanup, render, screen, fireEvent, waitFor,configure } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import App from './App'
import { api } from './api'

afterEach(()=>{cleanup();vi.restoreAllMocks()})
configure({asyncUtilTimeout:5000})
const user={id:1,name:'Demo Analyst',email:'analyst@example.test',role:'analyst'}
function mount(route='/dashboard'){return render(<MemoryRouter initialEntries={[route]}><App/></MemoryRouter>)}

describe('Workspace integration states',()=>{
  it('requires authentication before displaying applicant data',async()=>{
    vi.spyOn(api,'get').mockRejectedValue(new Error('Not authenticated'))
    mount('/applications')
    expect(await screen.findByRole('heading',{name:'Welcome to LoanWise'})).toBeTruthy()
    expect(screen.queryByRole('heading',{name:'Application workspace'})).toBeNull()
  })
  it('validates the applicant name before creating any records',async()=>{
    vi.spyOn(api,'get').mockImplementation(async url=>({data:url==='/auth/me'?user:url==='/products'?[{id:1,name:'Synthetic product'}]:{status:'ok'}}) as any)
    const post=vi.spyOn(api,'post')
    mount('/applications/new')
    fireEvent.click(await screen.findByRole('button',{name:'Save application'}))
    await waitFor(()=>expect(screen.getAllByText('Enter the applicant’s name').length).toBeGreaterThan(0))
    expect(post).not.toHaveBeenCalled()
  })
  it('shows the backend error for a failed application load',async()=>{
    vi.spyOn(api,'get').mockImplementation(async url=>{if(url==='/applications')throw new Error('Application service unavailable');return {data:url==='/auth/me'?user:{status:'ok'}} as any})
    mount('/applications')
    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(screen.getByText('Application service unavailable')).toBeTruthy()
  })
})
