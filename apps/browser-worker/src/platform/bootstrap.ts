import { configFromEnv, startTelemetry } from './telemetry.js'

export const telemetry = startTelemetry(configFromEnv(process.env))

process.once('beforeExit', () => {
  void telemetry.shutdown()
})
