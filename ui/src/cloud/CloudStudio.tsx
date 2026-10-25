import { useCallback, useEffect, useState } from 'react'
import { Cloud, ExternalLink, LoaderCircle, Power, RefreshCw, ShieldCheck } from 'lucide-react'

interface Settings { connected: boolean; signup_url: string; referral: boolean; image: string; default_gpu: string }
interface GPU { id: string; name: string; memory: number; hourly: number; availability: string; quote: string }
interface Volume { id: string; name: string; size: number; dataCenter: string }
interface Session { pod_id?: string; status?: string; ready?: boolean; creation_unknown?: boolean; elapsed_seconds?: number; estimated_compute_cost?: number; hourly?: number; quoted_hourly?: number; deadline?: number; monitor_error?: string }

async function request<T>(path: string, body?: object): Promise<T> {
  const response = await fetch('/api/cloud/' + path, { method: body ? 'POST' : 'GET', headers: body ? { 'Content-Type': 'application/json', 'X-ImageMaestro-Cloud': '1' } : {}, body: body ? JSON.stringify(body) : undefined, cache: 'no-store' })
  const result = await response.json()
  if (!response.ok) throw new Error(result.error || 'Cloud request failed')
  return result as T
}
const money = (value: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 3 }).format(value)
const input = 'w-full rounded-lg border border-border bg-bg-primary px-3 py-2.5 text-sm outline-none focus:border-orange-500'
const button = 'inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed'

export default function CloudStudio() {
  const [settings, setSettings] = useState<Settings | null>(null)
  const [key, setKey] = useState('')
  const [gpus, setGpus] = useState<GPU[]>([])
  const [gpuId, setGpuId] = useState('')
  const [cloud, setCloud] = useState('SECURE')
  const [volumes, setVolumes] = useState<Volume[]>([])
  const [volumeId, setVolumeId] = useState('')
  const [session, setSession] = useState<Session>({})
  const [hours, setHours] = useState(2)
  const [idle, setIdle] = useState(30)
  const [accepted, setAccepted] = useState(false)
  const [savedOutputs, setSavedOutputs] = useState(false)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const selected = gpus.find(gpu => gpu.id === gpuId)
  const tracked = !!session.pod_id || !!session.creation_unknown
  const stopped = ['STOPPED', 'EXITED', 'MISSING'].includes(session.status || '')

  const refresh = useCallback(async () => {
    setSession(await request<Session>('session'))
  }, [])
  const loadCatalog = useCallback(async () => {
    const result = await request<{gpus: GPU[]}>('catalog?cloud=' + cloud)
    setGpus(result.gpus)
    setGpuId(previous => result.gpus.some(g => g.id === previous) ? previous : result.gpus[0]?.id || '')
    setAccepted(false)
  }, [cloud])
  const act = useCallback(async (name: string, work: () => Promise<void>) => {
    setBusy(name); setError(''); setNotice('')
    try { await work() } catch (e) { setError(e instanceof Error ? e.message : 'Request failed') } finally { setBusy('') }
  }, [])

  useEffect(() => {
    let cancelled = false
    document.title = 'ImageMaestro Cloud'
    void request<Settings>('settings').then(value => { if (!cancelled) setSettings(value) }).catch(e => { if (!cancelled) setError(String(e)) })
    return () => { cancelled = true }
  }, [])
  useEffect(() => {
    if (!settings?.connected) return
    let cancelled = false
    void act('refresh', async () => {
      const [catalog, storage, current] = await Promise.all([request<{gpus: GPU[]}>('catalog?cloud=' + cloud), request<{volumes: Volume[]}>('volumes'), request<Session>('session')])
      if (cancelled) return
      setGpus(catalog.gpus); setGpuId(catalog.gpus[0]?.id || ''); setVolumes(storage.volumes); setSession(current); setAccepted(false)
    })
    return () => { cancelled = true }
  }, [settings?.connected, cloud, act])
  useEffect(() => {
    if (!settings?.connected || !session.pod_id) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout>
    const poll = async () => {
      try { const value = await request<Session>('session'); if (!cancelled) { setSession(value); setError('') } }
      catch (e) { if (!cancelled) setError(String(e)) }
      if (!cancelled) timer = setTimeout(() => { void poll() }, 10000)
    }
    timer = setTimeout(() => { void poll() }, 10000)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [settings?.connected, session.pod_id])

  return <main className="min-h-screen bg-bg-primary text-text-primary overflow-y-auto">
    <div className="mx-auto max-w-5xl px-5 py-8 md:py-12">
      <header className="mb-9 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3"><div className="rounded-xl bg-orange-500/15 p-3 text-orange-400"><Cloud size={25} /></div><div><p className="text-xs uppercase tracking-widest text-text-muted">ImageMaestro</p><h1 className="text-2xl font-semibold">Cloud GPU studio</h1></div></div>
        <a href="https://console.runpod.io/pods" target="_blank" rel="noopener noreferrer" className="text-sm text-text-secondary flex items-center gap-2">Runpod console <ExternalLink size={14}/></a>
      </header>
      <p className="mb-7 max-w-2xl text-text-secondary">Your models, your LoRAs, a rented NVIDIA GPU. Start a private studio in your browser and pay Runpod directly for the time and storage you use.</p>
      {error && <div role="alert" className="mb-5 rounded-xl border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-300">{error}</div>}
      {notice && <p role="status" className="mb-5 rounded-xl border border-border p-4 text-sm">{notice}</p>}
      {!settings ? <p role="status">Loading cloud settings…</p> : <>
        <section className="mb-5 rounded-2xl border border-border bg-bg-secondary p-5 md:p-6">
          <h2 className="mb-2 text-lg font-medium">1. Connect your account</h2>
          {settings.connected ? <div className="flex flex-wrap items-center justify-between gap-3"><p className="flex items-center gap-2 text-sm text-emerald-400"><ShieldCheck size={18}/> Runpod account connected</p><button disabled={!!busy || tracked} className={button + ' border border-border'} onClick={() => void act('disconnect', async () => { setSettings(await request<Settings>('disconnect', {})); setGpus([]) })}>Disconnect</button></div> : <>
            <p className="mb-4 text-sm text-text-secondary">Create or sign in to your Runpod account, add credit, then create an API key with permission to manage Pods and read GPU/storage information.</p>
            <div className="mb-4 flex flex-wrap gap-4 text-sm text-orange-400"><a href={settings.signup_url} target="_blank" rel="noopener noreferrer">Create Runpod account ↗</a><a href="https://console.runpod.io/user/settings" target="_blank" rel="noopener noreferrer">I already have an account ↗</a></div>
            {settings.referral && <p className="mb-4 text-xs text-text-muted">The signup link is a referral link. Eligible referrals may support ImageMaestro through Runpod’s programme.</p>}
            <form className="flex flex-col sm:flex-row gap-3" onSubmit={e => { e.preventDefault(); void act('connect', async () => { setSettings(await request<Settings>('connect', {api_key: key})); setKey('') }) }}>
              <label className="flex-1"><span className="sr-only">Runpod API key</span><input type="password" autoComplete="off" value={key} onChange={e => setKey(e.target.value)} placeholder="Runpod API key" className={input}/></label>
              <button className={button + ' bg-orange-600 text-white'} disabled={!!busy || !key}>{busy === 'connect' ? <LoaderCircle className="animate-spin" size={16}/> : null}Connect account</button>
            </form>
            <p className="mt-3 text-xs text-text-muted">The key is stored in a private file on this computer (not encrypted at rest). It is never sent to the studio container.</p>
          </>}
        </section>
        <div className="grid gap-5 md:grid-cols-[1.15fr_1fr]">
          <section className="rounded-2xl border border-border bg-bg-secondary p-5 md:p-6">
            <div className="flex items-center justify-between mb-4"><h2 className="text-lg font-medium">2. Choose your GPU</h2><button aria-label="Refresh GPU prices" disabled={!settings.connected || !!busy || tracked} onClick={() => void act('prices', loadCatalog)} className="p-2 text-text-muted"><RefreshCw size={17}/></button></div>
            <label className="block mb-4 text-sm">Cloud tier<select className={input + ' mt-2'} value={cloud} disabled={!settings.connected || tracked || !!busy} onChange={e => { setCloud(e.target.value); setAccepted(false); setVolumeId('') }}><option value="SECURE">Secure Cloud</option><option value="COMMUNITY">Community Cloud</option></select></label>
            <label className="block mb-4 text-sm">GPU<select className={input + ' mt-2'} value={gpuId} disabled={!settings.connected || tracked || !!busy} onChange={e => { setGpuId(e.target.value); setAccepted(false) }}><option value="">{settings.connected ? 'Choose an available GPU' : 'Connect to see live prices'}</option>{gpus.map(gpu => <option key={gpu.id} value={gpu.id} disabled={gpu.availability === 'NONE'}>{gpu.name} · {gpu.memory} GB · {money(gpu.hourly)}/hr{gpu.availability === 'NONE' ? ' · Out of stock' : ''}</option>)}</select></label>
            <label className="block mb-4 text-sm">Persistent storage<select className={input + ' mt-2'} value={volumeId} disabled={!settings.connected || tracked || !!busy} onChange={e => { setVolumeId(e.target.value); setAccepted(false) }}><option value="">100 GB Pod disk · retained while Pod exists</option>{cloud === 'SECURE' && volumes.map(volume => <option key={volume.id} value={volume.id}>{volume.name} · {volume.size} GB · {volume.dataCenter}</option>)}</select></label>
            <p className="text-xs text-text-muted">Storage is billed separately, including while a Pod is stopped. Pod disks are deleted when a Pod is released. Network volumes survive release. Download important outputs before finishing.</p>
          </section>
          <section className="rounded-2xl border border-border bg-bg-secondary p-5 md:p-6">
            <h2 className="mb-4 text-lg font-medium">3. Start creating</h2>
            <p className="text-3xl font-semibold">{selected ? money(selected.hourly) : '—'}<span className="text-sm font-normal text-text-muted"> / hour estimate</span></p>
            <p className="mt-2 mb-5 text-xs text-text-muted">GPU price from Runpod; final allocation and storage may change the total. Downloads, startup and idle time are billable.</p>
            <div className="grid grid-cols-2 gap-3 mb-4"><label className="text-sm">Session limit (hours)<input type="number" min="0.25" max="24" step="0.25" className={input + ' mt-2'} value={hours} disabled={tracked} onChange={e => { setHours(Number(e.target.value)); setAccepted(false) }}/></label><label className="text-sm">Idle stop (minutes)<input type="number" min="5" max="120" className={input + ' mt-2'} value={idle} disabled={tracked} onChange={e => setIdle(Number(e.target.value))}/></label></div>
            <p className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-amber-200">Keep the local launcher and computer online for automatic shutdown. Closing this window or losing connectivity does not guarantee the GPU stops. The session limit may interrupt a running job. Always check the Runpod console.</p>
            {!settings.image && <p className="mb-4 text-sm text-amber-300">Cloud deployment is awaiting the publisher’s tested container image. Account connection and GPU pricing are available now.</p>}
            {!tracked && <><label className="mb-4 flex gap-2 text-xs text-text-secondary"><input type="checkbox" checked={accepted} onChange={e => setAccepted(e.target.checked)}/><span>I accept Runpod’s usage and storage charges. {selected ? `The compute estimate for ${hours} hours is ${money(selected.hourly * hours)}.` : ''}</span></label><button className={button + ' w-full bg-orange-600 text-white'} disabled={!settings.connected || !selected || !accepted || !!busy || !settings.image} onClick={() => void act('start', async () => { setSession(await request<Session>('start', {quote: selected?.quote, volume_id: volumeId, max_hours: hours, idle_minutes: idle, accept_charges: accepted})); setAccepted(false) })}>{busy === 'start' ? <LoaderCircle size={17} className="animate-spin"/> : <Cloud size={17}/>}Start cloud studio</button></>}
          </section>
        </div>
        {tracked && <section className="mt-5 rounded-2xl border border-border bg-bg-secondary p-5 md:p-6" aria-label="Cloud session"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-lg font-medium">Your cloud session</h2><p role="status" className="mt-1 text-sm text-orange-400">{session.ready ? 'Studio ready' : session.status === 'RUNNING' ? 'Starting studio…' : session.status || 'Checking status…'}</p><p className="mt-2 text-xs text-text-muted">{session.pod_id || 'Deployment response uncertain — check the Runpod console before creating another Pod.'}</p></div><div><p className="text-xl">{money(session.estimated_compute_cost || 0)}</p><p className="text-xs text-text-muted">Estimated session compute · {Math.floor((session.elapsed_seconds || 0) / 60)} min</p></div></div>
          {session.monitor_error && <p role="alert" className="mt-4 text-red-300 text-sm">{session.monitor_error}</p>}
          <div className="mt-5 flex flex-wrap gap-3"><button className={button + ' bg-orange-600 text-white'} disabled={!session.ready || !!busy} onClick={() => { const popup = window.open('about:blank', '_blank'); if (popup) popup.opener = null; void act('open', async () => { try { const result = await request<{url: string}>('open', {}); if (popup) popup.location.href = result.url; else { setNotice('Allow popups for this local panel, then click Open studio again.'); } } catch (e) { popup?.close(); throw e } }) }}><ExternalLink size={16}/>Open studio</button><button className={button + ' border border-border'} disabled={!!busy || stopped || !session.pod_id || session.status === 'STOPPING'} onClick={() => void act('stop', async () => { setSession(await request<Session>('stop', {})) })}><Power size={16}/>Stop GPU</button><button className={button + ' border border-border'} disabled={!!busy || !session.ready} onClick={() => void act('download', async () => { const result = await request<{downloaded: number; directory: string; total: number}>('download', {}); setSavedOutputs(true); setNotice(`Saved ${result.downloaded} new files (${result.total} gallery outputs) to ${result.directory}`) })}>Download outputs</button><button className={button + ' border border-border'} disabled={!!busy} onClick={() => void act('refresh', refresh)}>Refresh status</button>{session.creation_unknown && <button className={button + ' border border-border'} disabled={!!busy} onClick={() => void act('reconcile', async () => { setSession(await request<Session>('reconcile', {})) })}>Find interrupted deployment</button>}</div>
          {stopped && <div className="mt-5 border-t border-border pt-4"><p className="text-sm text-text-secondary">The GPU is stopped. Storage charges may continue until you release the Pod. Use the Runpod console to resume a stopped session.</p><label className="my-3 flex gap-2 text-xs"><input type="checkbox" checked={savedOutputs} onChange={e => setSavedOutputs(e.target.checked)}/>I have downloaded my outputs and understand that releasing deletes the Pod disk.</label><button className={button + ' border border-red-500/40 text-red-300'} disabled={!savedOutputs || !!busy} onClick={() => void act('release', async () => { setSession(await request<Session>('release', {confirmed: true})); setSavedOutputs(false); setNotice('Pod released. Any attached network volume is retained and still billed separately.') })}>Release Pod</button></div>}
        </section>}
      </>}
    </div>
  </main>
}
