/**
 * Animate a number from its previous value to the new one (ease-out), so a changed score is noticed.
 * Non-numbers are returned unchanged; with reduced motion the value updates instantly.
 */
import { useEffect, useRef, useState } from "react"

const reducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches

export function useCountUp<T>(value: T, duration = 600): T | number {
  const [shown, setShown] = useState<T | number>(value)
  const from = useRef<number | null>(typeof value === "number" ? value : null)

  useEffect(() => {
    if (typeof value !== "number" || !Number.isFinite(value)) {
      setShown(value)
      from.current = null
      return
    }
    const start = from.current ?? 0
    from.current = value
    if (start === value || reducedMotion()) {
      setShown(value)
      return
    }
    let raf = 0
    const t0 = performance.now()
    const tick = (now: number) => {
      const p = Math.min(1, (now - t0) / duration)
      const eased = 1 - Math.pow(1 - p, 3)
      setShown(Math.round(start + (value - start) * eased))
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [value, duration])

  return shown
}
