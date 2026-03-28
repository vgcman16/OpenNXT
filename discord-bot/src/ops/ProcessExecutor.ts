import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import type { Logger } from "pino";
import { ensureDirectory } from "../util/fs";

export interface CommandSpec {
  id: string;
  label: string;
  command: string;
  args: string[];
  cwd: string;
  env?: NodeJS.ProcessEnv;
  shell?: boolean;
  timeoutMs?: number;
  logFile: string;
}

export interface CommandExecutionResult {
  exitCode: number;
  durationMs: number;
  logFile: string;
  tail: string;
}

export class ProcessExecutor {
  constructor(private readonly logger: Logger) {}

  async run(spec: CommandSpec): Promise<CommandExecutionResult> {
    ensureDirectory(path.dirname(spec.logFile));
    const output = fs.createWriteStream(spec.logFile, { flags: "a" });
    const startedAt = Date.now();
    const lines: string[] = [];

    return await new Promise<CommandExecutionResult>((resolve, reject) => {
      const child = spawn(spec.command, spec.args, {
        cwd: spec.cwd,
        env: { ...process.env, ...spec.env },
        shell: spec.shell ?? false,
        windowsHide: true
      });

      let timedOut = false;
      const timeout = spec.timeoutMs
        ? setTimeout(() => {
            timedOut = true;
            child.kill();
          }, spec.timeoutMs)
        : null;

      const append = (chunk: Buffer) => {
        const text = chunk.toString("utf8");
        output.write(text);
        for (const line of text.split(/\r?\n/)) {
          if (!line) {
            continue;
          }
          lines.push(line);
          if (lines.length > 60) {
            lines.shift();
          }
        }
      };

      child.stdout.on("data", append);
      child.stderr.on("data", append);
      child.on("error", (error) => {
        if (timeout) {
          clearTimeout(timeout);
        }
        output.end();
        reject(error);
      });
      child.on("close", (code) => {
        if (timeout) {
          clearTimeout(timeout);
        }
        output.end();

        if (timedOut) {
          reject(new Error(`${spec.label} timed out after ${spec.timeoutMs}ms`));
          return;
        }

        const result = {
          exitCode: code ?? -1,
          durationMs: Date.now() - startedAt,
          logFile: spec.logFile,
          tail: lines.join("\n")
        };

        if (result.exitCode !== 0) {
          this.logger.error({ command: spec.id, logFile: spec.logFile }, `${spec.label} failed`);
          reject(new Error(`${spec.label} failed with exit code ${result.exitCode}\n${result.tail}`));
          return;
        }

        resolve(result);
      });
    });
  }
}
