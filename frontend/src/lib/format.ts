export function browserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"
  } catch {
    return "UTC"
  }
}

const DATE_TIME: Intl.DateTimeFormatOptions = {
  dateStyle: "medium",
  timeStyle: "short",
}

export function formatDeadline(
  dueAt: string | null,
  timezone: string,
  dueLocalDate?: string | null,
  dueLocalTime?: string | null,
): string {
  if (!dueAt) {
    if (!dueLocalDate) return "No deadline"
    return dueLocalTime
      ? `Due ${dueLocalDate} at ${dueLocalTime.slice(0, 5)}`
      : `Due ${dueLocalDate} (no time given)`
  }
  const date = new Date(dueAt)
  if (Number.isNaN(date.getTime())) return "No deadline"
  try {
    return new Intl.DateTimeFormat(undefined, { ...DATE_TIME, timeZone: timezone }).format(date)
  } catch {
    return date.toISOString().slice(0, 16).replace("T", " ")
  }
}

export function relativeDays(dueAt: string | null): string {
  if (!dueAt) return ""
  const target = new Date(dueAt).getTime()
  if (Number.isNaN(target)) return ""
  const diffMs = target - Date.now()
  const days = Math.round(diffMs / 86_400_000)
  if (days === 0) return "today"
  if (days === 1) return "tomorrow"
  if (days === -1) return "yesterday"
  if (days < 0) return `${-days} days overdue`
  return `in ${days} days`
}

export function initials(name: string | null | undefined): string {
  if (!name) return "?"
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("")
}
