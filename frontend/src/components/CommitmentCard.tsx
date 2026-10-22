import { Check, Clock, Link2, User } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { formatDeadline, relativeDays } from "@/lib/format"
import type { Commitment } from "@/types"

interface Props {
  commitment: Commitment
  busy?: boolean
  onComplete: (id: string) => void
  onAddDependency?: (id: string) => void
}

const STATUS_VARIANT = {
  pending: "secondary",
  in_progress: "default",
  completed: "success",
  cancelled: "muted",
} as const

export function CommitmentCard({ commitment, busy, onComplete, onAddDependency }: Props) {
  const overdue =
    commitment.status !== "completed" &&
    commitment.status !== "cancelled" &&
    commitment.due_at !== null &&
    new Date(commitment.due_at).getTime() < Date.now()

  return (
    <li className="rounded-lg border bg-card p-3 pl-fade-in">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p
            className={
              "truncate text-sm font-medium " +
              (commitment.status === "completed" ? "text-muted-foreground line-through" : "")
            }
          >
            {commitment.title}
          </p>
          {commitment.recipient && (
            <p className="mt-0.5 flex items-center gap-1 text-xs text-muted-foreground">
              <User className="size-3" /> {commitment.recipient}
            </p>
          )}
          {commitment.details && (
            <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{commitment.details}</p>
          )}
        </div>
        {commitment.status !== "completed" && (
          <Button
            size="sm"
            variant="success"
            disabled={busy}
            onClick={() => onComplete(commitment.id)}
          >
            <Check className="size-3" />
            Done
          </Button>
        )}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <Badge variant={STATUS_VARIANT[commitment.status] ?? "secondary"}>
          {commitment.status.replace("_", " ")}
        </Badge>
        {overdue && <Badge variant="destructive">overdue</Badge>}
        {commitment.blocked_by.length > 0 && (
          <Badge variant="warning">
            <Link2 className="size-3" /> blocked
          </Badge>
        )}
        {commitment.priority !== "normal" && (
          <Badge variant="outline">{commitment.priority} priority</Badge>
        )}
        {commitment.source !== "manual" && (
          <Badge variant="muted">via {commitment.source}</Badge>
        )}
      </div>

      <p className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
        <Clock className="size-3" />
        {formatDeadline(
          commitment.due_at,
          commitment.timezone,
          commitment.due_local_date,
          commitment.due_local_time,
        )}
        {commitment.due_at && (
          <span className="text-foreground/70">({relativeDays(commitment.due_at)})</span>
        )}
      </p>

      {onAddDependency && commitment.status !== "completed" && (
        <Button
          size="sm"
          variant="ghost"
          className="mt-2 h-7 px-2 text-xs"
          onClick={() => onAddDependency(commitment.id)}
        >
          <Link2 className="size-3" /> Add dependency
        </Button>
      )}
    </li>
  )
}
