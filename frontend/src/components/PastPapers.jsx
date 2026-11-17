import { useCallback, useEffect, useState } from 'react'
import { ExternalLink, FileText, Loader2, RotateCcw, Search, Trash2, UploadCloud } from 'lucide-react'
import { api, getToken } from '../api/client'
import { useToast } from '../context/ToastContext'
import { useInterval } from '../hooks/useAsync'
import { Badge, Button, Card, CardHeader, ConfirmModal, Field, Input, Modal, ProgressBar, cx } from './ui'

const SOURCE = { psc: ['PSC', 'violet'], nrb: ['NRB', 'blue'], web: ['Web', 'slate'], upload: ['Uploaded', 'green'] }
const STATUS = {
  found: ['Queued', 'slate'],
  processing: ['Reading…', 'violet'],
  done: ['MCQs extracted', 'green'],
  no_mcq: ['Subjective / no MCQs', 'amber'],
  failed: ['Failed', 'red'],
}

/** Open a stored paper with the auth header (uploads and downloaded copies). */
export async function openStoredPaper(id) {
  const res = await fetch(api.paperFileUrl(id), { headers: { Authorization: `Bearer ${getToken()}` } })
  if (!res.ok) throw new Error('File not available')
  const url = URL.createObjectURL(await res.blob())
  window.open(url, '_blank', 'noopener')
}

export function PaperLink({ paper, className }) {
  const toast = useToast()
  if (paper.file_url) {
    return (
      <a href={paper.file_url} target="_blank" rel="noreferrer" className={cx('inline-flex items-center gap-1 font-semibold text-brand-700 hover:underline', className)}>
        Open <ExternalLink className="h-3.5 w-3.5" />
      </a>
    )
  }
  if (paper.has_file) {
    return (
      <button onClick={() => openStoredPaper(paper.id).catch((e) => toast.error(e.message))}
        className={cx('inline-flex items-center gap-1 font-semibold text-brand-700 hover:underline', className)}>
        Open <FileText className="h-3.5 w-3.5" />
      </button>
    )
  }
  return null
}

export default function PastPapers({ course, papers: paperLabels = [], onChange }) {
  const toast = useToast()
  const [data, setData] = useState(null)
  const [starting, setStarting] = useState(false)
  const [upload, setUpload] = useState(false)
  const [file, setFile] = useState(null)
  const [label, setLabel] = useState('')
  const [paper, setPaper] = useState('')
  const [busy, setBusy] = useState(false)
  const [confirm, setConfirm] = useState(null)

  const load = useCallback(() => api.pastPapers(course.id).then(setData).catch(() => {}), [course.id])
  useEffect(() => { load() }, [load])

  const job = data?.job
  const jobRunning = job && ['PENDING', 'STARTED', 'PROGRESS', 'RETRY'].includes(job.state)
  const anyBusy = (data?.papers || []).some((p) => p.status === 'found' || p.status === 'processing')
  useInterval(() => { load(); onChange?.() }, 3000, Boolean(jobRunning || anyBusy))

  const find = async () => {
    setStarting(true)
    try {
      await api.findPastPapers(course.id)
      toast.info('Searching PSC, NRB and the web for past papers…')
      await load()
    } catch (err) {
      toast.error(err.message)
    } finally {
      setStarting(false)
    }
  }

  const submitUpload = async (e) => {
    e.preventDefault()
    setBusy(true)
    try {
      await api.uploadPastPaper(course.id, file, label, paper)
      toast.success('Paper uploaded. It is being read now.')
      setUpload(false)
      setFile(null)
      setLabel('')
      load()
    } catch (err) {
      toast.error(err.message)
    } finally {
      setBusy(false)
    }
  }

  const p = job?.progress
  const list = data?.papers || []
  const totals = list.reduce((acc, x) => ({ papers: acc.papers + 1, mcq: acc.mcq + (x.mcq_added || 0) }), { papers: 0, mcq: 0 })

  return (
    <Card>
      <CardHeader
        icon={Search}
        title="Past papers"
        subtitle={`${totals.papers} papers · ${totals.mcq} MCQs extracted. Sources: Lok Sewa Aayog (psc.gov.np), Nepal Rastra Bank archive and the web. Scans are read with OCR.`}
        actions={
          <>
            <Button variant="secondary" size="sm" onClick={() => setUpload(true)}><UploadCloud className="h-4 w-4" /> Upload</Button>
            <Button size="sm" onClick={find} loading={starting} disabled={jobRunning}><Search className="h-4 w-4" /> Find past papers</Button>
          </>
        }
      />
      {jobRunning && (
        <div className="border-b border-ink-100 bg-brand-50/50 px-5 py-3 text-sm">
          <p className="flex items-center gap-2 font-medium text-ink-800">
            <Loader2 className="h-4 w-4 animate-spin text-brand-600" />
            {p?.current || 'Starting…'}
          </p>
          {p?.total ? <ProgressBar className="mt-2" tone="bg-brand-600" value={(100 * (p.done || 0)) / p.total} /> : null}
          {p?.found !== undefined && <p className="mt-1 text-xs text-ink-500">{p.found} papers found · {p.new} new · {p.mcq_added || 0} MCQs added so far</p>}
        </div>
      )}
      {list.length === 0 ? (
        <p className="px-5 py-10 text-center text-sm text-ink-500">
          {jobRunning ? 'Papers will appear here as they are found.' : 'No papers yet. Click “Find past papers” or upload one.'}
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-ink-500">
              <tr><th className="px-5 py-2">Paper</th><th className="px-3 py-2">Year</th><th className="px-3 py-2">Status</th><th className="px-3 py-2">MCQs</th><th className="px-5 py-2 text-right" /></tr>
            </thead>
            <tbody className="divide-y divide-ink-100">
              {list.map((x) => {
                const [srcLabel, srcTone] = SOURCE[x.source] || [x.source, 'slate']
                const [stLabel, stTone] = STATUS[x.status] || [x.status, 'slate']
                return (
                  <tr key={x.id} className="align-top hover:bg-ink-50/60">
                    <td className="px-5 py-3">
                      <div className="flex items-start gap-2">
                        <Badge tone={srcTone}>{srcLabel}</Badge>
                        <div className="min-w-0">
                          <p className="font-medium text-ink-900">{x.title.replace(/^(PSC|NRB|Web) · /, '')}</p>
                          {x.error && <p className="text-xs text-ink-500">{x.error}</p>}
                          {x.ocr && <p className="text-xs text-ink-400">Read with OCR{x.pages ? ` · ${x.pages} page(s)` : ''}</p>}
                        </div>
                      </div>
                    </td>
                    <td className="num px-3 py-3 text-ink-600">{x.year || '—'}</td>
                    <td className="px-3 py-3">
                      <Badge tone={stTone}>{x.status === 'processing' && <Loader2 className="h-3 w-3 animate-spin" />}{stLabel}</Badge>
                    </td>
                    <td className="num px-3 py-3 text-ink-700">{x.status === 'done' ? `${x.mcq_added} / ${x.mcq_found}` : '—'}</td>
                    <td className="whitespace-nowrap px-5 py-3 text-right">
                      <div className="flex items-center justify-end gap-3">
                        <PaperLink paper={x} />
                        {['failed', 'no_mcq', 'done'].includes(x.status) && (
                          <button title="Read again" onClick={() => api.reprocessPaper(x.id).then(load).catch((e) => toast.error(e.message))}
                            className="text-ink-400 hover:text-ink-700"><RotateCcw className="h-4 w-4" /></button>
                        )}
                        <button title="Remove from list" onClick={() => setConfirm(x)} className="text-ink-400 hover:text-rose-600"><Trash2 className="h-4 w-4" /></button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <Modal open={upload} onClose={() => setUpload(false)} title="Upload a past paper"
        footer={<><Button variant="secondary" onClick={() => setUpload(false)}>Cancel</Button>
          <Button type="submit" form="pp-upload" loading={busy} disabled={!file || label.length < 2}>Upload & read</Button></>}>
        <form id="pp-upload" onSubmit={submitUpload} className="space-y-4">
          <label className={cx('flex cursor-pointer flex-col items-center rounded-xl border-2 border-dashed px-4 py-6 text-center',
            file ? 'border-brand-400 bg-brand-50/50' : 'border-ink-300 hover:border-brand-400')}>
            <UploadCloud className="mb-2 h-7 w-7 text-ink-400" />
            <span className="text-sm font-medium text-ink-800">{file ? file.name : 'Choose a PDF or image'}</span>
            <span className="text-xs text-ink-500">PDF · PNG · JPG · TIFF (scans are read with OCR)</span>
            <input type="file" hidden accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.webp,.txt" onChange={(e) => setFile(e.target.files?.[0] || null)} />
          </label>
          <Field label="Title" hint="e.g. “NRB AD (IT) 2081 Paper I”"><Input required minLength={2} value={label} onChange={(e) => setLabel(e.target.value)} /></Field>
          {paperLabels.length > 1 && (
            <Field label="Paper (optional)">
              <select className="block w-full rounded-xl border-0 px-3.5 py-2.5 text-sm shadow-sm ring-1 ring-inset ring-ink-200" value={paper} onChange={(e) => setPaper(e.target.value)}>
                <option value="">Any paper</option>
                {paperLabels.map((l) => <option key={l} value={l}>{l}</option>)}
              </select>
            </Field>
          )}
        </form>
      </Modal>
      <ConfirmModal open={Boolean(confirm)} title="Remove this paper?" confirmLabel="Remove"
        message="It disappears from the list. Questions already extracted from it stay in the question bank."
        onClose={() => setConfirm(null)}
        onConfirm={async () => { try { await api.deletePaper(confirm.id); load() } catch (e) { toast.error(e.message) } setConfirm(null) }} />
    </Card>
  )
}
