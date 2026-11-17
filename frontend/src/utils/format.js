// The API returns UTC timestamps; MySQL drops the zone, so naive strings are treated as UTC.
export function parseDate(value) {
  if (!value) return null
  if (typeof value === 'string' && /T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(value)) return new Date(`${value}Z`)
  return new Date(value)
}

export function formatDate(value) {
  if (!value) return '—'
  const d = parseDate(value)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export function timeAgo(value) {
  if (!value) return '—'
  const diff = (Date.now() - parseDate(value).getTime()) / 1000
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} d ago`
  return formatDate(value)
}

export function formatDuration(seconds) {
  if (seconds === null || seconds === undefined) return '—'
  const s = Math.max(0, Math.round(seconds))
  const m = Math.floor(s / 60)
  const rem = s % 60
  return m ? `${m}m ${String(rem).padStart(2, '0')}s` : `${rem}s`
}

export function formatBytes(bytes) {
  if (!bytes) return '—'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let n = bytes
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024
    i++
  }
  return `${n.toFixed(i ? 1 : 0)} ${units[i]}`
}

export function scoreTone(percent) {
  if (percent >= 80) return 'text-emerald-600 dark:text-emerald-400'
  if (percent >= 50) return 'text-amber-600 dark:text-amber-400'
  return 'text-rose-600 dark:text-rose-400'
}

export const LETTERS = ['A', 'B', 'C', 'D']
export const DIFFICULTIES = ['easy', 'medium', 'hard']

/** "Paper I: Information Technology I" -> "Paper I" (short label for chips and tables). */
export function paperShort(paper) {
  if (!paper) return 'Full exam'
  const m = paper.match(/^((?:paper|part)\s+[ivx\d]+)/i)
  return m ? m[1] : paper
}

/** Group a course's chapters by paper, keeping syllabus order. */
export function groupByPaper(chapters) {
  const groups = []
  for (const ch of chapters) {
    const last = groups[groups.length - 1]
    if (last && last.paper === (ch.paper || null)) last.chapters.push(ch)
    else groups.push({ paper: ch.paper || null, chapters: [ch] })
  }
  return groups
}

export function papersOf(chapters) {
  return [...new Set(chapters.map((c) => c.paper).filter(Boolean))]
}

/** Human label for where a question came from. */
export function sourceLabel(source, reference) {
  if (source === 'past_paper') return { tone: 'violet', text: `Past paper${reference ? ` · ${reference}` : ''}` }
  if (source === 'online') return { tone: 'blue', text: 'Old question (online)' }
  if (source === 'notes') return { tone: 'green', text: 'Study notes' }
  return { tone: 'slate', text: `AI-written${source ? ` · ${source}` : ''}` }
}
