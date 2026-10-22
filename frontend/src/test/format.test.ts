import { describe, expect, it } from "vitest"

import { formatDeadline, initials, relativeDays } from "@/lib/format"

describe("formatDeadline", () => {
  it("renders the deadline in the commitment timezone", () => {
    const iso = "2026-10-23T12:30:00+00:00"
    const formatted = formatDeadline(iso, "UTC")
    expect(formatted).toMatch(/2026/)
    expect(formatted).toMatch(/Oct/)
  })

  it("falls back to the spoken date when no instant is known", () => {
    expect(formatDeadline(null, "UTC", "2026-10-23")).toContain("2026-10-23")
  })

  it("reports when there is no deadline at all", () => {
    expect(formatDeadline(null, "UTC")).toBe("No deadline")
  })
})

describe("relativeDays", () => {
  it("describes near-term deadlines", () => {
    const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString()
    expect(relativeDays(tomorrow)).toBe("tomorrow")
  })

  it("describes overdue deadlines", () => {
    const past = new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString()
    expect(relativeDays(past)).toBe("3 days overdue")
  })

  it("returns an empty string without a deadline", () => {
    expect(relativeDays(null)).toBe("")
  })
})

describe("initials", () => {
  it("builds up to two initials", () => {
    expect(initials("Abhishek Kumar")).toBe("AK")
    expect(initials("Priya")).toBe("P")
    expect(initials(null)).toBe("?")
  })
})
