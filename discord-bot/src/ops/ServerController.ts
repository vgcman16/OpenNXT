import fs from "node:fs";
import path from "node:path";
import net from "node:net";
import { spawn } from "node:child_process";
import type { Logger } from "pino";
import type { SqliteStore } from "../persistence/SqliteStore";
import { ensureDirectory } from "../util/fs";
import { tailFile } from "../util/tail";
import { loadServerConfig } from "./serverConfig";

interface ServerControllerConfig {
  repoPath: string;
  javaHome?: string;
  logPath: string;
}

export interface ServerRuntimeStatus {
  running: boolean;
  pid: number | null;
  configuredPorts: {
    game: number;
    http: number;
    https: number;
  };
  livePorts: {
    game: boolean;
    http: boolean;
  };
  stdoutLog: string;
  stderrLog: string;
}

async function waitForPort(port: number, timeoutMs: number) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    const isOpen = await probePort(port);
    if (isOpen) {
      return true;
    }
    await new Promise((resolve) => setTimeout(resolve, 1_000));
  }
  return false;
}

function probePort(port: number) {
  return new Promise<boolean>((resolve) => {
    const socket = new net.Socket();
    socket.setTimeout(1_500);
    socket.once("connect", () => {
      socket.destroy();
      resolve(true);
    });
    socket.once("timeout", () => {
      socket.destroy();
      resolve(false);
    });
    socket.once("error", () => {
      socket.destroy();
      resolve(false);
    });
    socket.connect(port, "127.0.0.1");
  });
}

function processExists(pid: number) {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

export class ServerController {
  private readonly stdoutLogPath: string;
  private readonly stderrLogPath: string;

  constructor(
    private readonly config: ServerControllerConfig,
    private readonly store: SqliteStore,
    private readonly logger: Logger
  ) {
    ensureDirectory(config.logPath);
    this.stdoutLogPath = path.join(config.logPath, "opennxt-server.out.log");
    this.stderrLogPath = path.join(config.logPath, "opennxt-server.err.log");
  }

  async start() {
    const currentStatus = await this.status();
    if (currentStatus.running) {
      throw new Error(`Server is already running with pid ${currentStatus.pid}`);
    }

    const libDir = path.join(this.config.repoPath, "build", "install", "OpenNXT", "lib");
    if (!fs.existsSync(libDir)) {
      throw new Error(`Installed distribution not found at ${libDir}`);
    }

    const javaExecutable = this.config.javaHome
      ? path.join(this.config.javaHome, "bin", "java.exe")
      : "java";
    const stdout = fs.openSync(this.stdoutLogPath, "a");
    const stderr = fs.openSync(this.stderrLogPath, "a");

    const child = spawn(
      javaExecutable,
      [
        "--enable-native-access=ALL-UNNAMED",
        "-cp",
        path.join(libDir, "*"),
        "com.opennxt.MainKt",
        "run-server"
      ],
      {
        cwd: this.config.repoPath,
        detached: true,
        stdio: ["ignore", stdout, stderr],
        windowsHide: true
      }
    );

    child.unref();
    this.store.setSetting("server.pid", String(child.pid));
    this.store.setSetting("server.stdoutLogPath", this.stdoutLogPath);
    this.store.setSetting("server.stderrLogPath", this.stderrLogPath);
    this.store.setSetting("server.startedAt", new Date().toISOString());

    const serverConfig = loadServerConfig(path.join(this.config.repoPath, "data", "config", "server.toml"));
    const httpReady = await waitForPort(serverConfig.ports.http, 30_000);
    const gameReady = await waitForPort(serverConfig.ports.game, 30_000);
    if (!httpReady || !gameReady) {
      await this.stop();
      throw new Error("Server failed smoke checks after start.");
    }

    this.logger.info({ pid: child.pid }, "OpenNXT server started");
    return { pid: child.pid, stdoutLogPath: this.stdoutLogPath, stderrLogPath: this.stderrLogPath };
  }

  async stop() {
    const pidValue = this.store.getSetting("server.pid");
    if (!pidValue) {
      return false;
    }

    const pid = Number(pidValue);
    if (!Number.isFinite(pid) || !processExists(pid)) {
      this.clearStoredPid();
      return false;
    }

    await new Promise<void>((resolve, reject) => {
      const child = spawn("taskkill", ["/PID", String(pid), "/T", "/F"], {
        cwd: this.config.repoPath,
        windowsHide: true
      });
      child.on("error", reject);
      child.on("close", () => resolve());
    });
    this.clearStoredPid();
    this.logger.info({ pid }, "OpenNXT server stopped");
    return true;
  }

  async restart() {
    await this.stop();
    return await this.start();
  }

  async status(): Promise<ServerRuntimeStatus> {
    const serverConfig = loadServerConfig(path.join(this.config.repoPath, "data", "config", "server.toml"));
    const pidValue = this.store.getSetting("server.pid");
    const pid = pidValue ? Number(pidValue) : null;
    const running = pid !== null && Number.isFinite(pid) && processExists(pid);

    if (!running && pid !== null) {
      this.clearStoredPid();
    }

    return {
      running,
      pid: running ? pid : null,
      configuredPorts: serverConfig.ports,
      livePorts: {
        game: await probePort(serverConfig.ports.game),
        http: await probePort(serverConfig.ports.http)
      },
      stdoutLog: this.stdoutLogPath,
      stderrLog: this.stderrLogPath
    };
  }

  readLogs(stream: "stdout" | "stderr" | "both", lineCount: number) {
    const stdout = tailFile(this.stdoutLogPath, lineCount);
    const stderr = tailFile(this.stderrLogPath, lineCount);

    if (stream === "stdout") {
      return stdout;
    }
    if (stream === "stderr") {
      return stderr;
    }
    return [stdout, stderr].filter(Boolean).join("\n--- stderr ---\n");
  }

  private clearStoredPid() {
    this.store.setSetting("server.pid", "");
  }
}
