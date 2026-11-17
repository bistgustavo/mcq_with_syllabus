import { useEffect, useState } from 'react'
import { Palette, RotateCcw } from 'lucide-react'
import { api } from '../../api/client'
import { applyColors, useBranding } from '../../context/BrandingContext'
import { useToast } from '../../context/ToastContext'
import { Button, Card, CardHeader, Field, Input, PageHeader, Toggle } from '../../components/ui'

const PRESETS = [
  ['Royal blue', '#1d4ed8', '#e11d48'],
  ['Crimson', '#b91c1c', '#1d4ed8'],
  ['Emerald', '#047857', '#d97706'],
  ['Indigo', '#4338ca', '#db2777'],
  ['Teal', '#0f766e', '#ea580c'],
  ['Slate', '#334155', '#2563eb'],
]

function ColorField({ label, value, onChange }) {
  return (
    <Field label={label}>
      <div className="flex items-center gap-2">
        <input type="color" value={value} onChange={(e) => onChange(e.target.value)} className="h-10 w-12 cursor-pointer rounded-lg border border-ink-200 bg-white p-1" />
        <Input value={value} onChange={(e) => onChange(e.target.value)} maxLength={7} />
      </div>
    </Field>
  )
}

export default function AdminSettings() {
  const { branding, setBranding } = useBranding()
  const toast = useToast()
  const [f, setF] = useState(branding)
  const [busy, setBusy] = useState(false)
  useEffect(() => setF(branding), [branding])

  // Live preview while editing; restore when leaving without saving.
  useEffect(() => {
    applyColors(f.primary_color, f.accent_color)
    return () => applyColors(branding.primary_color, branding.accent_color)
  }, [f.primary_color, f.accent_color, branding])

  const save = async (e) => {
    e.preventDefault()
    setBusy(true)
    try {
      const saved = await api.updateBranding({ ...f, logo_url: f.logo_url || null, support_email: f.support_email || null })
      setBranding(saved)
      toast.success('Branding saved. Students see it immediately.')
    } catch (err) {
      toast.error(err.message)
    } finally {
      setBusy(false)
    }
  }

  const initials = f.institution_name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase()

  return (
    <>
      <PageHeader eyebrow="Administration" title="Branding & settings" subtitle="Make the platform look like your institution. Changes apply across the site." />
      <form onSubmit={save} className="grid gap-6 lg:grid-cols-[1fr_380px]">
        <div className="space-y-6">
          <Card>
            <CardHeader icon={Palette} title="Identity" />
            <div className="space-y-5 p-5">
              <Field label="Institution name"><Input required maxLength={120} value={f.institution_name} onChange={(e) => setF({ ...f, institution_name: e.target.value })} /></Field>
              <Field label="Tagline" hint="Shown on the landing and sign-in pages."><Input maxLength={200} value={f.tagline} onChange={(e) => setF({ ...f, tagline: e.target.value })} /></Field>
              <div className="grid gap-5 sm:grid-cols-2">
                <Field label="Logo URL" hint="Square PNG or SVG, optional."><Input type="url" placeholder="https://…" value={f.logo_url || ''} onChange={(e) => setF({ ...f, logo_url: e.target.value })} /></Field>
                <Field label="Support e-mail"><Input type="email" value={f.support_email || ''} onChange={(e) => setF({ ...f, support_email: e.target.value })} /></Field>
              </div>
            </div>
          </Card>
          <Card>
            <CardHeader title="Colours" subtitle="Pick a preset or choose your own." />
            <div className="space-y-5 p-5">
              <div className="flex flex-wrap gap-2">
                {PRESETS.map(([name, p, a]) => (
                  <button key={name} type="button" onClick={() => setF({ ...f, primary_color: p, accent_color: a })}
                    className="flex items-center gap-2 rounded-xl border border-ink-200 px-3 py-2 text-sm font-medium hover:border-ink-300">
                    <span className="flex"><span className="h-4 w-4 rounded-full" style={{ background: p }} /><span className="-ml-1.5 h-4 w-4 rounded-full ring-2 ring-white" style={{ background: a }} /></span>
                    {name}
                  </button>
                ))}
              </div>
              <div className="grid gap-5 sm:grid-cols-2">
                <ColorField label="Primary colour" value={f.primary_color} onChange={(v) => setF({ ...f, primary_color: v })} />
                <ColorField label="Accent colour" value={f.accent_color} onChange={(v) => setF({ ...f, accent_color: v })} />
              </div>
            </div>
          </Card>
          <Card>
            <CardHeader title="Access" />
            <div className="p-5">
              <Toggle checked={f.allow_signup} onChange={(v) => setF({ ...f, allow_signup: v })} label="Allow students to sign up themselves"
                description="Turn off to make the platform invitation-only; you then create or approve accounts yourself." />
            </div>
          </Card>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => setF(branding)}><RotateCcw className="h-4 w-4" /> Reset</Button>
            <Button type="submit" loading={busy}>Save changes</Button>
          </div>
        </div>

        <div className="lg:sticky lg:top-8 lg:h-fit">
          <p className="mb-2 text-sm font-semibold text-ink-700">Live preview</p>
          <Card className="overflow-hidden">
            <div className="flex items-center gap-2.5 border-b border-ink-100 px-4 py-3">
              {f.logo_url ? <img src={f.logo_url} alt="" className="h-8 w-8 rounded-lg object-contain" /> :
                <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-600 text-xs font-bold text-white">{initials}</span>}
              <span className="truncate text-sm font-bold text-ink-900">{f.institution_name}</span>
            </div>
            <div className="bg-gradient-to-br from-brand-600 to-brand-800 p-5 text-white">
              <p className="text-lg font-bold leading-snug">{f.tagline}</p>
              <span className="mt-4 inline-block rounded-lg bg-white px-3 py-1.5 text-xs font-semibold text-brand-700">Start preparing</span>
            </div>
            <div className="space-y-3 p-4">
              <div className="flex gap-2"><span className="rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-semibold text-white">Primary</span>
                <span className="rounded-lg bg-accent-600 px-3 py-1.5 text-xs font-semibold text-white">Submit exam</span>
                <span className="rounded-lg bg-brand-50 px-3 py-1.5 text-xs font-semibold text-brand-700">Soft</span></div>
              <div className="h-2 overflow-hidden rounded-full bg-ink-100"><div className="h-full w-2/3 rounded-full bg-brand-600" /></div>
            </div>
          </Card>
        </div>
      </form>
    </>
  )
}
