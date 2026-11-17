import { useState } from 'react'
import { Sparkles } from 'lucide-react'
import { api } from '../api/client'
import { useToast } from '../context/ToastContext'
import { useTaskPoller } from '../hooks/useAsync'
import { Button, Card, Field, Input, Select, Toggle } from './ui'
import { DIFFICULTIES, formatDuration } from '../utils/format'

/** Admin tool: generate new questions for one topic (background task with progress). */
export default function GenerationPanel({ topicId, hasContent, onGenerated, defaultDifficulty = 'medium' }) {
  const toast = useToast()
  const poll = useTaskPoller()
  const [count, setCount] = useState(5)
  const [difficulty, setDifficulty] = useState(defaultDifficulty)
  const [webFallback, setWebFallback] = useState(true)
  const [running, setRunning] = useState(false)
  const [progress, setProgress] = useState(null)

  const finish = (result) => {
    const n = result?.generated ?? 0
    if (n > 0) toast.success(`Added ${n} question${n === 1 ? '' : 's'} (${result.source}${result.context_source === 'web_search' ? ', from web research' : ''}).`)
    else toast.info('Only duplicates of existing questions came back. Try another difficulty.')
    onGenerated?.(result)
  }

  const run = async () => {
    setRunning(true)
    setProgress({ state: 'QUEUED', elapsed: 0 })
    const body = { count: Number(count), difficulty, use_web_fallback: webFallback }
    try {
      let accepted
      try {
        accepted = await api.generate(topicId, { ...body, run_async: true })
      } catch (err) {
        if (err.status !== 503) throw err
        setProgress({ state: 'RUNNING', elapsed: 0 })
        finish(await api.generate(topicId, { ...body, run_async: false }))
        return
      }
      finish(await poll(accepted.task_id, { onUpdate: (s, elapsed) => setProgress({ state: s.state, elapsed }) }))
    } catch (err) {
      toast.error(err.message || 'Generation failed')
    } finally {
      setRunning(false)
      setProgress(null)
    }
  }

  return (
    <Card className="h-fit p-5">
      <div className="flex items-center gap-2">
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-violet-50 text-violet-600"><Sparkles className="h-4 w-4" /></span>
        <h2 className="font-semibold text-ink-900">Generate questions</h2>
      </div>
      <p className="mb-4 mt-2 text-xs leading-relaxed text-ink-500">
        {hasContent ? 'Written from this topic’s notes and research.' : 'No notes yet. The topic will be researched on the web first.'}{' '}
        Cloud AI first; falls back to the local model when limits are reached.
      </p>
      <div className="grid grid-cols-2 gap-3">
        <Field label="How many"><Input type="number" min={1} max={25} value={count} onChange={(e) => setCount(e.target.value)} disabled={running} /></Field>
        <Field label="Difficulty">
          <Select value={difficulty} onChange={(e) => setDifficulty(e.target.value)} disabled={running}>
            {DIFFICULTIES.map((d) => <option key={d} value={d}>{d}</option>)}
          </Select>
        </Field>
      </div>
      {!hasContent && <div className="mt-4"><Toggle checked={webFallback} onChange={setWebFallback} label="Research the web if needed" /></div>}
      <Button className="mt-5 w-full" variant="dark" onClick={run} loading={running}>{running ? 'Generating…' : 'Generate'}</Button>
      {progress && (
        <p className="mt-2 text-center text-xs text-ink-500">
          {progress.state.toLowerCase()} · {formatDuration(progress.elapsed)}
        </p>
      )}
    </Card>
  )
}
