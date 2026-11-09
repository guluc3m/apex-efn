'use client'

import type { ColumnFiltersState, SortingState } from '@tanstack/react-table'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'

import { toRoute } from '../app-link'

/** Orden y filtros de una tabla en la URL (`?sort=-price&status=aborted`). Cambiar de filtro usa `replace`: no ensucia el historial. */
export function useUrlTable(filterIds: readonly string[]) {
  const params = useSearchParams()
  const pathname = usePathname()
  const router = useRouter()

  const sort = params.get('sort')
  const sorting: SortingState = sort ? [{ id: sort.replace(/^-/, ''), desc: sort.startsWith('-') }] : []
  const columnFilters: ColumnFiltersState = filterIds.flatMap((id) => {
    const value = params.get(id)
    return value ? [{ id, value }] : []
  })

  const write = (mutate: (p: URLSearchParams) => void) => {
    const next = new URLSearchParams(params.toString())
    mutate(next)
    const qs = next.toString()
    // typedRoutes no admite rutas con query dinámica.
    router.replace(toRoute(qs ? `${pathname}?${qs}` : pathname), { scroll: false })
  }

  return {
    sorting,
    columnFilters,
    value: (id: string) => params.get(id) ?? 'all',
    onSortingChange: (s: SortingState) =>
      write((p) => (s[0] ? p.set('sort', `${s[0].desc ? '-' : ''}${s[0].id}`) : p.delete('sort'))),
    setFilter: (id: string, v: string) => write((p) => (v === 'all' ? p.delete(id) : p.set(id, v))),
    onColumnFiltersChange: (f: ColumnFiltersState) =>
      write((p) => {
        filterIds.forEach((id) => p.delete(id))
        f.forEach((x) => p.set(x.id, String(x.value)))
      }),
  }
}
