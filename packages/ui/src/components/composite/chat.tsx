import { Bot, CircleStop, Paperclip, Send, Store, User, type LucideIcon } from 'lucide-react'
import * as React from 'react'

import { cn } from '../../lib/utils.js'
import { Button } from '../button.js'
import { Icon } from '../icon.js'

import { Thinking } from './thinking.js'

export type ChatRole = 'agent' | 'seller' | 'human'

export interface ChatMessage {
  id: string
  role: ChatRole
  /** Nombre visible del autor (agente, vendedor, persona). */
  author: string
  text: string
  /** Hora ya formateada. */
  time?: string
}

export interface ChatLabels {
  input: string
  placeholder?: string
  send: string
  stop: string
  /** Si se pasa junto a `onAttach`, aparece el botón de adjuntar. */
  attach?: string
  /** «Intro enviar · Mayús + Intro nueva línea». */
  hint?: string
}

export interface ChatProps {
  messages?: ChatMessage[]
  labels: ChatLabels
  /** Mientras el agente trabaja: halo intenso, textos rotatorios y «Parar» en vez de «Enviar». */
  thinking?: boolean
  phrases?: string[]
  onSend: (text: string) => void
  onStop?: () => void
  onAttach?: () => void
  className?: string
}

const ROLE: Record<ChatRole, { icon: LucideIcon; cls: string }> = {
  agent: { icon: Bot, cls: 'border-accent-line bg-accent-subtle' },
  seller: { icon: Store, cls: 'border-line bg-panel' },
  human: { icon: User, cls: 'border-line-strong bg-raised' },
}

export function Chat({ messages = [], labels, thinking = false, phrases = [], onSend, onStop, onAttach, className }: ChatProps) {
  const [text, setText] = React.useState('')
  const [focus, setFocus] = React.useState(false)
  const [hidden, setHidden] = React.useState(false)
  React.useEffect(() => {
    const sync = () => setHidden(document.visibilityState === 'hidden')
    sync()
    document.addEventListener('visibilitychange', sync)
    return () => document.removeEventListener('visibilitychange', sync)
  }, [])

  const open = focus || thinking || text.length > 0
  const submit = () => {
    if (!text.trim()) return
    onSend(text)
    setText('')
  }

  return (
    <div className={cn('flex flex-col gap-3', className)}>
      {messages.length > 0 && (
        <ol className="m-0 flex list-none flex-col gap-2 p-0" aria-live="polite">
          {messages.map((m) => (
            <li key={m.id} className={cn('flex max-w-[80%] flex-col gap-1 border p-3 motion-safe:animate-[ap-msg_160ms_var(--easing)_both]', ROLE[m.role].cls, m.role === 'human' && 'self-end')}>
              <span className="inline-flex items-center gap-1.5 text-[13px] text-ink-muted">
                <Icon icon={ROLE[m.role].icon} />
                {m.author}
                {m.time && <time className="ml-1">{m.time}</time>}
              </span>
              <span className="whitespace-pre-wrap">{m.text}</span>
            </li>
          ))}
        </ol>
      )}
      <div className="ap-halo" data-halo={thinking ? 'thinking' : focus ? 'focus' : 'idle'} data-paused={hidden}>
        <div className={cn('border bg-panel', open ? 'border-control-border' : 'border-line-strong')}>
          {/* Crece hacia arriba: la fila extra se despliega sobre el textarea, sin rebote. */}
          <div className={cn('grid transition-[grid-template-rows] duration-(--overlay) ease-apex motion-reduce:transition-none', open ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]')}>
            <div className="min-h-0 overflow-hidden">
              {thinking && (
                <div className="px-4 pt-2">
                  <Thinking phrases={phrases} />
                </div>
              )}
              <div className="flex flex-wrap items-center justify-between gap-2 px-2 pt-2">
                {onAttach && labels.attach ? (
                  <Button variant="ghost" size="sm" onClick={onAttach}>
                    <Icon icon={Paperclip} />
                    {labels.attach}
                  </Button>
                ) : (
                  <span />
                )}
                {labels.hint && <span className="text-[13px] text-ink-muted">{labels.hint}</span>}
              </div>
            </div>
          </div>
          <div className="flex items-end gap-2 p-2">
            <textarea
              rows={1}
              value={text}
              aria-label={labels.input}
              placeholder={labels.placeholder}
              onChange={(e) => setText(e.target.value)}
              onFocus={() => setFocus(true)}
              onBlur={() => setFocus(false)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault()
                  submit()
                }
              }}
              className={cn(
                'min-h-11 min-w-0 flex-1 resize-none border border-transparent bg-bg px-3 py-2.5 text-ink transition-[height,border-color] duration-(--overlay) ease-apex placeholder:text-ink-muted focus:border-accent motion-reduce:transition-none',
                open ? 'h-24' : 'h-11',
              )}
            />
            <Button
              variant={thinking ? 'sec' : 'pri'}
              size="lg"
              className="w-11 min-w-11 px-0"
              aria-label={thinking ? labels.stop : labels.send}
              onClick={thinking ? onStop : submit}
            >
              <Icon icon={thinking ? CircleStop : Send} />
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
