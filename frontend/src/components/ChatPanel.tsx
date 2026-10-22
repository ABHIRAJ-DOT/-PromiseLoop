import { Check, Loader2, Send, TriangleAlert, X } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { MicButton } from "@/components/MicButton"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/input"
import { formatDeadline } from "@/lib/format"
import type { ChatMessage, PendingConfirmation } from "@/types"

interface Props {
  messages: ChatMessage[]
  confirmation: PendingConfirmation | null
  sending: boolean
  error: string | null
  onSend: (text: string) => void
  onConfirm: () => void
  onDiscard: () => void
}

const SUGGESTIONS = [
  "I promised Abhishek that I'll send him our project demo by tomorrow evening.",
  "What should I do next?",
  "How many commitments are overdue?",
]

export function ChatPanel({
  messages,
  confirmation,
  sending,
  error,
  onSend,
  onConfirm,
  onDiscard,
}: Props) {
  const [text, setText] = useState("")
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, confirmation])

  const submit = () => {
    const value = text.trim()
    if (!value || sending) return
    onSend(value)
    setText("")
  }

  return (
    <div className="flex h-full min-h-[520px] flex-col rounded-xl border bg-card shadow-sm">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div>
          <p className="text-sm font-semibold">PromiseLoop Assistant</p>
          <p className="text-xs text-muted-foreground">Alexa+ style voice &amp; chat demo</p>
        </div>
        <Badge variant="muted">MCP tools</Badge>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {messages.length === 0 && (
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">
              Tell me a promise you made. I will extract the who, the what and the when, then
              confirm before saving.
            </p>
            <div className="space-y-1.5 pt-1">
              {SUGGESTIONS.map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => onSend(suggestion)}
                  className="block w-full rounded-lg border bg-muted/40 px-3 py-2 text-left text-xs text-muted-foreground transition-colors hover:bg-accent cursor-pointer"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((message, index) => (
          <div
            key={index}
            className={
              "flex " +
              (message.role === "user" ? "justify-end" : "justify-start") +
              " pl-fade-in"
            }
          >
            <div
              className={
                "max-w-[85%] rounded-2xl px-3 py-2 text-sm " +
                (message.role === "user"
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-foreground")
              }
            >
              {message.content}
            </div>
          </div>
        ))}

        {confirmation && (
          <div className="rounded-xl border border-primary/40 bg-primary/5 p-3 pl-fade-in">
            <p className="flex items-center gap-1.5 text-xs font-semibold text-primary">
              <TriangleAlert className="size-3.5" /> Please confirm
            </p>
            <p className="mt-1 text-sm">{confirmation.question}</p>
            <dl className="mt-2 space-y-1 text-xs">
              <Row label="Task" value={confirmation.draft.title} />
              <Row label="Who" value={confirmation.draft.recipient || "not specified"} />
              <Row
                label="Deadline"
                value={formatDeadline(
                  confirmation.draft.due_at,
                  confirmation.draft.timezone,
                  confirmation.draft.due_local_date,
                  confirmation.draft.due_local_time,
                )}
              />
              <Row label="Timezone" value={confirmation.draft.timezone} />
            </dl>
            <div className="mt-3 flex gap-2">
              <Button size="sm" onClick={onConfirm} disabled={sending}>
                <Check className="size-3" /> Save it
              </Button>
              <Button size="sm" variant="outline" onClick={onDiscard} disabled={sending}>
                <X className="size-3" /> Discard
              </Button>
            </div>
          </div>
        )}

        {sending && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin" /> Thinking…
          </div>
        )}

        {error && (
          <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-3 py-2 text-xs text-destructive">
            {error}
          </div>
        )}

        <div ref={endRef} />
      </div>

      <div className="border-t p-3">
        <div className="flex items-end gap-2">
          <Textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault()
                submit()
              }
            }}
            placeholder="I promised Abhishek that I'll send the demo by tomorrow evening…"
            className="min-h-10 resize-none"
          />
          <MicButton onTranscript={onSend} disabled={sending} />
          <Button size="icon" onClick={submit} disabled={sending || !text.trim()}>
            <Send className="size-4" />
          </Button>
        </div>
        <p className="mt-2 text-[11px] text-muted-foreground">
          Enter to send · Shift+Enter for a new line · the microphone works in Chrome and Edge.
        </p>
      </div>
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2">
      <dt className="w-16 shrink-0 text-muted-foreground">{label}</dt>
      <dd className="font-medium">{value}</dd>
    </div>
  )
}
