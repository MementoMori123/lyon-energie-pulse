import type { PulseResponse } from '../types/pulse'

const base = () => (import.meta.env.VITE_API_BASE as string | undefined) ?? ''

export async function fetchPulse(): Promise<PulseResponse> {
  const res = await fetch(`${base()}/api/pulse`, {
    cache: 'no-store',
    headers: { Accept: 'application/json' },
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = (await res.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') detail = body.detail
      else if (body.detail != null) detail = JSON.stringify(body.detail)
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<PulseResponse>
}
