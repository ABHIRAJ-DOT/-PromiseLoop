import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { Dashboard } from "@/components/Dashboard"
import type { Commitment, Dashboard as DashboardData } from "@/types"

const commitment: Commitment = {
  id: "1",
  title: "Send project demo to Abhishek",
  recipient: "Abhishek",
  details: null,
  status: "pending",
  priority: "normal",
  due_at: new Date().toISOString(),
  due_local_date: null,
  due_local_time: null,
  deadline_precision: "day",
  timezone: "UTC",
  source: "chat",
  original_text: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  completed_at: null,
  depends_on_ids: [],
  blocked_by: [],
}

const data: DashboardData = {
  pending: [],
  overdue: [commitment],
  completed: [],
  upcoming: [],
  blocked: [],
  counts: { pending: 0, overdue: 1, upcoming: 0, completed: 0, blocked: 0, total: 1 },
  next_actions: [],
  server_time: new Date().toISOString(),
}

const noop = () => {}

describe("Dashboard", () => {
  it("shows an error state with a retry action", () => {
    const onRetry = vi.fn()
    render(
      <Dashboard
        data={null}
        loading={false}
        error="Backend unreachable"
        busyId={null}
        onRetry={onRetry}
        onComplete={noop}
        onAddDependency={noop}
      />,
    )
    expect(screen.getByText("Backend unreachable")).toBeTruthy()
    expect(screen.getByText(/try again/i)).toBeTruthy()
  })

  it("shows an empty state when there is nothing to show", () => {
    render(
      <Dashboard
        data={{ ...data, overdue: [], counts: { ...data.counts, overdue: 0, total: 0 } }}
        loading={false}
        error={null}
        busyId={null}
        onRetry={noop}
        onComplete={noop}
        onAddDependency={noop}
      />,
    )
    expect(screen.getByText(/no commitments yet/i)).toBeTruthy()
  })

  it("lists commitments and lets the user mark them done", () => {
    const onComplete = vi.fn()
    render(
      <Dashboard
        data={data}
        loading={false}
        error={null}
        busyId={null}
        onRetry={noop}
        onComplete={onComplete}
        onAddDependency={noop}
      />,
    )
    expect(screen.getByText("Send project demo to Abhishek")).toBeTruthy()
    screen.getByText("Done").click()
    expect(onComplete).toHaveBeenCalledWith("1")
  })
})
