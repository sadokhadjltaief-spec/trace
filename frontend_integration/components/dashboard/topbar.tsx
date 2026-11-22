'use client'

import { useEffect, useState } from 'react'
import { Flame, Menu, Search, Trophy } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ThemeToggle } from '@/components/theme-toggle'
import type { DashboardCopy } from './dashboard-copy'

type Props = { copy: DashboardCopy; streak: number; points: number; onOpenMenu: () => void; onSearch?: (query: string) => void
}

function useHideOnScroll(threshold = 64) {
  const [hidden, setHidden] = useState(false)

  useEffect(() => {
    let lastY = window.scrollY
    const onScroll = () => {
      const y = window.scrollY
      if (Math.abs(y - lastY) < 6) return
      setHidden(y > lastY && y > threshold)
      lastY = y
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [threshold])

  return hidden
}

export function Topbar({ copy, streak, points, onOpenMenu, onSearch }: Props) {
  const hidden = useHideOnScroll()

  return (
    <header
      className={cn(
        'sticky top-0 z-20 flex items-center gap-3 border-b border-border bg-background/90 px-4 py-3 backdrop-blur transition-transform duration-300 focus-within:translate-y-0 md:px-8',
        hidden && '-translate-y-full',
      )}
    >
      <button
        type="button"
        onClick={onOpenMenu}
        aria-label={copy.openMenu}
        className="flex size-10 items-center justify-center rounded-xl border border-border text-foreground lg:hidden"
      >
        <Menu className="size-5" aria-hidden="true" />
      </button>

      <label className="relative flex max-w-md flex-1 items-center">
        <span className="sr-only">{copy.search}</span>
        <Search className="pointer-events-none absolute start-3.5 size-4 text-muted-foreground" aria-hidden="true" />
        <input
          type="search"
          placeholder={copy.search}
          onKeyDown={(e) => { const v = e.currentTarget.value.trim(); if (e.key === 'Enter' && v) onSearch?.(v) }}
          className="h-10 w-full rounded-full border border-border bg-muted/60 ps-10 pe-4 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
        />
      </label>

      <div className="ms-auto flex items-center gap-2">
        <ThemeToggle labels={copy.theme} tone="light" />
        <span
          className="inline-flex h-9 items-center gap-1.5 rounded-full bg-secondary px-3 text-sm font-bold text-primary-deep"
          title={copy.streak.title}
        >
          <Flame className="size-4" aria-hidden="true" />
          {streak}
          <span className="sr-only">{copy.streak.title}</span>
        </span>
        <span
          className="hidden h-9 items-center gap-1.5 rounded-full bg-accent px-3 text-sm font-bold text-accent-foreground sm:inline-flex"
          title={copy.points.title}
        >
          <Trophy className="size-4" aria-hidden="true" />
          {points} {copy.points.unit}
        </span>
      </div>
    </header>
  )
}
