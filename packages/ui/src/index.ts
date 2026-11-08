/**
 * @trato/ui
 *
 * Design system components built on Radix UI + Tailwind CSS.
 * Based on shadcn/ui patterns.
 */

export { cn } from './lib/utils.js'

// Primitives
export { Button, type ButtonProps } from './components/button.js'
export { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from './components/card.js'
export { Badge, type BadgeProps } from './components/badge.js'

// Layout
export { Skeleton } from './components/skeleton.js'

// Forms
export { Input, type InputProps } from './components/input.js'
export { Label } from './components/label.js'

// Feedback
export { Progress } from './components/progress.js'

// TODO: Add more components as needed:
// - Dialog
// - Select
// - Tabs
// - Toast
// - Table
// - DropdownMenu
// - Popover
// - Tooltip
