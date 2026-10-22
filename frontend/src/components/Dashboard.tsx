import { AlertTriangle, CheckCircle2, CircleDot, Loader2, RefreshCw, Sparkles } from "lucide-react"
import { useMemo, useState } from "react"

import { CommitmentCard } from "@/components/CommitmentCard"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { Commitment, Dashboard as DashboardData } from "@/types"

interface Props {
  data: DashboardData | null
  loading: boolean
  error: string | null
  busyId: string | null
  onRetry: () => void
  onComplete: (id: string) => void
  onAddDependency: (id: string) => void
}

type Filter = "all" | "overdue" | "pending" | "upcoming" | "completed"

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "overdue", label: "Overdue" },
  { key: "pending", label: "Pending" },
  { key: "upcoming", label: "Today" },
  { key: "completed", label: "Completed" },
]

function bucketOf(data: DashboardData, commitment: Commitment): Filter {
  if (commitment.status === "completed") return "completed"
  if (data.overdue.some((item) => item.id === commitment.id)) return "overdue"
  if (data.upcoming.some((item) => item.id === commitment.id)) return "upcoming"
  return "pending"
}

export function Dashboard({
  data,
  loading,
  error,
  busyId,
  onRetry,
  onComplete,
  onAddDependency,
}: Props) {
  const [filter, setFilter] = useState<Filter>("all")

  const items = useMemo(() => {
    if (!data) return []
    const all = [...data.overdue, ...data.upcoming, ...data.pending, ...data.completed]
    const seen = new Set<string>()
    const unique = all.filter((item) => (seen.has(item.id) ? false : (seen.add(item.id), true)))
    if (filter === "all") return unique
    return unique.filter((item) => bucketOf(data, item) === filter)
  }, [data, filter])

  if (error) {
    return (
      <Card className="border-destructive/40">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-destructive">
            <AlertTriangle className="size-4" /> Could not load your commitments
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">{error}</p>
          <Button size="sm" onClick={onRetry}>
            <RefreshCw className="size-3" /> Try again
          </Button>
        </CardContent>
      </Card>
    )
  }

  if (loading && !data) {
    return (
      <Card>
        <CardContent className="flex items-center gap-2 py-10 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Loading commitments…
        </CardContent>
      </Card>
    )
  }

  const counts = data?.counts ?? {}

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile label="Pending" value={counts.pending ?? 0} icon={<CircleDot />} tone="text-foreground" />
        <StatTile label="Overdue" value={counts.overdue ?? 0} icon={<AlertTriangle />} tone="text-destructive" />
        <StatTile label="Due today" value={counts.upcoming ?? 0} icon={<Sparkles />} tone="text-primary" />
        <StatTile label="Completed" value={counts.completed ?? 0} icon={<CheckCircle2 />} tone="text-success" />
      </div>

      {data && data.next_actions.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Sparkles className="size-4 text-primary" /> What should I do next?
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="space-y-2">
              {data.next_actions.map((action) => (
                <li key={action.commitment.id} className="flex items-start gap-3 text-sm">
                  <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-semibold text-primary">
                    {action.commitment.title.slice(0, 1).toUpperCase()}
                  </span>
                  <div className="min-w-0">
                    <p className="truncate font-medium">{action.commitment.title}</p>
                    <p className="text-xs text-muted-foreground">
                      {action.reason}
                      {action.commitment.recipient ? ` · for ${action.commitment.recipient}` : ""}
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="flex-row items-center justify-between gap-2 space-y-0">
          <CardTitle>Commitments</CardTitle>
          <Button size="sm" variant="ghost" onClick={onRetry} disabled={loading}>
            <RefreshCw className={loading ? "size-3 animate-spin" : "size-3"} />
          </Button>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-1.5">
            {FILTERS.map((option) => (
              <button
                key={option.key}
                onClick={() => setFilter(option.key)}
                className={
                  "rounded-full border px-3 py-1 text-xs font-medium transition-colors cursor-pointer " +
                  (filter === option.key
                    ? "border-primary bg-primary text-primary-foreground"
                    : "bg-card text-muted-foreground hover:bg-accent")
                }
              >
                {option.label}
              </button>
            ))}
          </div>

          {items.length === 0 ? (
            <div className="rounded-lg border border-dashed py-10 text-center">
              <p className="text-sm font-medium">
                {filter === "all" ? "No commitments yet" : `Nothing ${filter}`}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {filter === "all"
                  ? "Tell the assistant what you promised and it will be saved here."
                  : "Try another filter."}
              </p>
            </div>
          ) : (
            <ul className="space-y-2">
              {items.map((item) => (
                <CommitmentCard
                  key={item.id}
                  commitment={item}
                  busy={busyId === item.id}
                  onComplete={onComplete}
                  onAddDependency={onAddDependency}
                />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function StatTile({
  label,
  value,
  icon,
  tone,
}: {
  label: string
  value: number
  icon: React.ReactNode
  tone: string
}) {
  return (
    <div className="rounded-lg border bg-card p-3">
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground [&_svg]:size-3.5">
        {icon}
        {label}
      </div>
      <p className={"mt-1 text-2xl font-semibold " + tone}>{value}</p>
    </div>
  )
}

export function BlockedBadge({ count }: { count: number }) {
  if (!count) return null
  return <Badge variant="warning">{count} blocked</Badge>
}
