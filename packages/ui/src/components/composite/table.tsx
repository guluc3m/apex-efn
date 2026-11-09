import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type ColumnFiltersState,
  type SortingState,
} from '@tanstack/react-table'
import { ArrowUp, ArrowUpRight, Inbox } from 'lucide-react'
import * as React from 'react'

import { cn } from '../../lib/utils.js'
import { Button } from '../button.js'
import { Icon } from '../icon.js'
import { Skeleton } from '../skeleton.js'

import { anchor, type RenderLink } from './link.js'

export interface TableColumn<R> {
  id: string
  header: string
  /** Numérica: a la derecha, tabular. */
  num?: boolean
  /** Por defecto ordenable. */
  sortable?: boolean
  /** Solo para lectores de pantalla (columna de acciones). */
  hidden?: boolean
  /** Valor ya calculado por la API que se ordena y filtra. Sin él no se ordena. */
  sortValue?: (row: R) => string | number
  cell: (row: R) => React.ReactNode
}

export interface TableProps<R> {
  columns: TableColumn<R>[]
  rows: R[]
  getRowId: (row: R) => string
  /** La primera columna es el enlace de la fila (`<a>` real). */
  getHref?: (row: R) => string
  caption: string
  loading?: boolean
  /** Contenido del estado vacío (icono + texto). */
  empty: string
  /** Orden controlable desde fuera (la página lo lleva a la URL). */
  sorting?: SortingState
  onSortingChange?: (s: SortingState) => void
  defaultSorting?: SortingState
  /** Filtro de texto sobre los `sortValue`; controlable desde fuera. */
  filter?: string
  /** Filtros por columna (banda, veredicto, plataforma): igualdad con el `sortValue`. Controlables desde fuera. */
  columnFilters?: ColumnFiltersState
  onColumnFiltersChange?: (f: ColumnFiltersState) => void
  pageSize?: number
  loadMoreLabel?: string
  maxHeight?: string
  dense?: boolean
  renderLink?: RenderLink
  className?: string
}

export function Table<R>({
  columns,
  rows,
  getRowId,
  getHref,
  caption,
  loading,
  empty,
  sorting: sortingProp,
  onSortingChange,
  defaultSorting = [],
  filter,
  columnFilters: filtersProp,
  onColumnFiltersChange,
  pageSize = 25,
  loadMoreLabel,
  maxHeight,
  dense,
  renderLink = anchor,
  className,
}: TableProps<R>) {
  const [inner, setInner] = React.useState<SortingState>(defaultSorting)
  const [shown, setShown] = React.useState(pageSize)
  const [innerFilters, setInnerFilters] = React.useState<ColumnFiltersState>([])
  const sorting = sortingProp ?? inner
  const columnFilters = filtersProp ?? innerFilters

  const defs = React.useMemo<ColumnDef<R>[]>(
    () =>
      columns.map((c, i) => ({
        id: c.id,
        header: c.header,
        filterFn: 'weakEquals',
        enableSorting: c.sortable !== false && !c.hidden && !!c.sortValue,
        ...(c.sortValue ? { accessorFn: c.sortValue } : { accessorFn: () => '' }),
        cell: ({ row }) => {
          const content = c.cell(row.original)
          const href = i === 0 ? getHref?.(row.original) : undefined
          return href
            ? renderLink({
                href,
                className: 'group/link inline-flex items-center gap-1 font-medium text-ink no-underline',
                children: (
                  <>
                    {content}
                    <Icon icon={ArrowUpRight} className="opacity-0 transition-opacity duration-(--fast) ease-apex group-hover/link:opacity-100 group-focus-visible/link:opacity-100 motion-reduce:transition-none" />
                  </>
                ),
              })
            : content
        },
      })),
    [columns, getHref, renderLink],
  )

  const table = useReactTable({
    data: rows,
    columns: defs,
    getRowId,
    state: { sorting, columnFilters, globalFilter: filter ?? '', pagination: { pageIndex: 0, pageSize: shown } },
    onSortingChange: (u) => {
      const next = typeof u === 'function' ? u(sorting) : u
      if (onSortingChange) onSortingChange(next)
      else setInner(next)
    },
    onColumnFiltersChange: (u) => {
      const next = typeof u === 'function' ? u(columnFilters) : u
      if (onColumnFiltersChange) onColumnFiltersChange(next)
      else setInnerFilters(next)
    },
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    globalFilterFn: 'includesString',
    manualPagination: false,
  })

  const out = table.getRowModel().rows
  const total = table.getFilteredRowModel().rows.length

  return (
    <div className={cn('flex flex-col', className)} aria-busy={loading || undefined}>
      <div className="overflow-auto" style={maxHeight ? { maxHeight } : undefined} role="region" aria-label={caption} tabIndex={0}>
        <table className="w-full border-separate border-spacing-0">
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr>
              {table.getHeaderGroups()[0]?.headers.map((h, i) => {
                const col = columns[i]!
                const dir = h.column.getIsSorted()
                return (
                  <th
                    key={h.id}
                    scope="col"
                    aria-sort={dir === 'asc' ? 'ascending' : dir === 'desc' ? 'descending' : undefined}
                    className={cn(
                      'sticky top-0 z-2 box-border h-9 border-b border-line bg-raised px-3 text-left text-[13px] font-medium whitespace-nowrap text-ink-muted',
                      col.num && 'text-right',
                      i === 0 && 'left-0 z-3',
                    )}
                  >
                    {col.hidden ? (
                      <span className="sr-only">{col.header}</span>
                    ) : h.column.getCanSort() ? (
                      <button
                        type="button"
                        onClick={h.column.getToggleSortingHandler()}
                        className={cn('group/sort inline-flex cursor-pointer items-center gap-1 border-0 bg-transparent p-0 font-[inherit] text-inherit', col.num && 'flex-row-reverse')}
                      >
                        <span>{col.header}</span>
                        <span className={cn('inline-flex transition-[opacity,transform] duration-(--fast) ease-apex-move motion-reduce:transition-[opacity] group-hover/sort:opacity-100 group-focus-visible/sort:opacity-100', dir ? 'opacity-100' : 'opacity-0', dir === 'desc' && 'rotate-180')}>
                          <Icon icon={ArrowUp} />
                        </span>
                      </button>
                    ) : (
                      col.header
                    )}
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {loading
              ? [0, 1, 2, 3, 4].map((r) => (
                  <tr key={r}>
                    {columns.map((c) => (
                      <td key={c.id} className={cn('h-11 border-b border-line bg-bg px-3 py-2', c.num && 'text-right')}>
                        <Skeleton className="inline-block h-3 w-[70%] align-middle" />
                      </td>
                    ))}
                  </tr>
                ))
              : out.map((row) => (
                  <tr key={row.id} className="hover:*:bg-raised hover:*:first:shadow-[inset_1px_0_0_var(--accent)] [&>td]:transition-[background-color] [&>td]:duration-(--fast)">
                    {row.getVisibleCells().map((cell, i) => (
                      <td
                        key={cell.id}
                        {...(i === 0 ? { role: 'rowheader' } : {})}
                        className={cn(
                          'box-border border-b border-line bg-bg px-3 align-middle',
                          dense ? 'h-9 py-1' : 'h-11 py-2',
                          columns[i]?.num && 'text-right tabular-nums',
                          i === 0 && 'sticky left-0 z-1',
                        )}
                      >
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                ))}
            {!loading && out.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="px-3 py-8 text-center text-ink-muted">
                  <span className="inline-flex items-center gap-1.5">
                    <Icon icon={Inbox} size={20} />
                    {empty}
                  </span>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {!loading && loadMoreLabel && total > out.length && (
        <div className="flex justify-center pt-3">
          <Button variant="sec" onClick={() => setShown((n) => n + pageSize)}>
            {loadMoreLabel}
          </Button>
        </div>
      )}
    </div>
  )
}
