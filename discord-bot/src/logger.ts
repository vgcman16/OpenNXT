import pino, { type Logger } from "pino";

export function createLogger(level: string): Logger {
  return pino({
    level,
    base: undefined,
    timestamp: pino.stdTimeFunctions.isoTime
  });
}
