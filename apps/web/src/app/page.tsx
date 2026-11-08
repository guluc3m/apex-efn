import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle } from '@trato/ui'

export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-24">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>TRATO</CardTitle>
          <CardDescription>B2B Sourcing Inteligente y Negociación Automatizada</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <p className="text-sm text-muted-foreground">
            Plataforma de compras por volumen que perfila tu empresa, busca ofertas, puntúa vendedores, negocia precios
            y presenta los tratos finales para tu decisión.
          </p>
          <div className="flex gap-2">
            <Button>Comenzar onboarding</Button>
            <Button variant="outline">Iniciar sesión</Button>
          </div>
        </CardContent>
      </Card>
    </main>
  )
}
