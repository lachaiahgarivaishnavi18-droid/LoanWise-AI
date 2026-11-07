import { describe, it, expect } from 'vitest'
import { money, errorText } from './api'
describe('Financial display',()=>{
  it('preserves unknown values rather than displaying zero',()=>{expect(money(null)).toBe('Unavailable');expect(money(0)).toContain('0')})
  it('formats INR without losing the currency indicator',()=>{expect(money(125000)).toContain('1,25,000')})
  it('shows an actionable error',()=>{expect(errorText(new Error('Check income'))).toBe('Check income')})
})
