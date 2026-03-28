import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import type { Logger } from "pino";
import type { AuditReport } from "../types";
import type { JobProgressReporter } from "./JobCoordinator";
import type { ProcessExecutor } from "./ProcessExecutor";
import type { ServerController } from "./ServerController";
import { ensureDirectory } from "../util/fs";
import { loadServerConfig } from "./serverConfig";

interface OpenNxtOpsConfig {
  repoPath: string;
  launcherPath: string;
  javaHome?: string;
  logPath: string;
  allowedCommandSet: string[];
}

const COMMAND_IDS = {
  buildInstall: "gradle.build_install",
  rsaKeyGenerator: "tool.rsa_key_generator",
  clientDownloader: "tool.client_downloader",
  cacheDownloader: "tool.cache_downloader",
  clientPatcher: "tool.client_patcher",
  serverStart: "server.start",
  serverStop: "server.stop",
  serverRestart: "server.restart"
} as const;

export class OpenNxtOpsService {
  constructor(
    private readonly config: OpenNxtOpsConfig,
    private readonly executor: ProcessExecutor,
    private readonly serverController: ServerController,
    private readonly logger: Logger
  ) {
    ensureDirectory(config.logPath);
  }

  async audit(): Promise<AuditReport> {
    const findings = [];
    const repoPath = this.config.repoPath;
    const gradlePath = path.join(repoPath, "gradlew.bat");
    const serverConfigPath = path.join(repoPath, "data", "config", "server.toml");
    const rsaPath = path.join(repoPath, "data", "config", "rsa.toml");
    const installPath = path.join(repoPath, "build", "install", "OpenNXT");
    const clientsPath = path.join(repoPath, "data", "clients");
    const cachePath = path.join(repoPath, "data", "cache", "js5-0.jcache");

    findings.push({
      label: "Repository path",
      ok: fs.existsSync(repoPath),
      detail: repoPath
    });
    findings.push({
      label: "Gradle wrapper",
      ok: fs.existsSync(gradlePath),
      detail: gradlePath
    });
    findings.push({
      label: "Launcher executable",
      ok: fs.existsSync(this.config.launcherPath),
      detail: this.config.launcherPath
    });
    findings.push({
      label: "Server config",
      ok: fs.existsSync(serverConfigPath),
      detail: serverConfigPath
    });
    findings.push({
      label: "RSA config",
      ok: fs.existsSync(rsaPath),
      detail: rsaPath
    });
    findings.push({
      label: "Installed distribution",
      ok: fs.existsSync(installPath),
      detail: installPath
    });
    findings.push({
      label: "Client assets",
      ok: fs.existsSync(clientsPath) && (fs.readdirSync(clientsPath).length > 0),
      detail: clientsPath
    });
    findings.push({
      label: "Cache",
      ok: fs.existsSync(cachePath),
      detail: cachePath
    });

    try {
      const serverConfig = loadServerConfig(serverConfigPath);
      findings.push({
        label: "Protocol data",
        ok: fs.existsSync(path.join(repoPath, "data", "prot", String(serverConfig.build))),
        detail: `build ${serverConfig.build}`
      });
      findings.push({
        label: "Server ports",
        ok: true,
        detail: `game=${serverConfig.ports.game}, http=${serverConfig.ports.http}, https=${serverConfig.ports.https}`
      });
    } catch (error) {
      findings.push({
        label: "Server config parse",
        ok: false,
        detail: error instanceof Error ? error.message : String(error)
      });
    }

    const javaExecutable = this.config.javaHome
      ? path.join(this.config.javaHome, "bin", "java.exe")
      : "java";
    const javaVersion = spawnSync(javaExecutable, ["-version"], { encoding: "utf8" });
    findings.push({
      label: "Java runtime",
      ok: javaVersion.status === 0,
      detail: (javaVersion.stderr || javaVersion.stdout || "java not found").trim()
    });

    const passing = findings.filter((finding) => finding.ok).length;
    return {
      findings,
      summary: `${passing}/${findings.length} host checks passed.`
    };
  }

  async bootstrap(
    options: { refreshAssets: boolean },
    reporter: JobProgressReporter
  ) {
    const audit = await this.audit();
    await reporter.stage("Audit prerequisites", audit.summary);

    const blockingFailures = audit.findings.filter((finding) =>
      ["Repository path", "Gradle wrapper", "Launcher executable", "Server config", "Java runtime", "Protocol data"].includes(
        finding.label
      ) && !finding.ok
    );
    if (blockingFailures.length > 0) {
      throw new Error(blockingFailures.map((finding) => `${finding.label}: ${finding.detail}`).join("\n"));
    }

    await reporter.stage("Build installDist", "Running Gradle build and installDist.");
    await this.runBatch(COMMAND_IDS.buildInstall, "Gradle build installDist", "gradlew.bat", ["build", "installDist"]);

    const rsaPath = path.join(this.config.repoPath, "data", "config", "rsa.toml");
    if (!fs.existsSync(rsaPath)) {
      await reporter.stage("RSA keys", "Generating RSA configuration.");
      await this.runInstalledTool(COMMAND_IDS.rsaKeyGenerator, "RSA key generator", ["run-tool", "rsa-key-generator"]);
    } else {
      await reporter.stage("RSA keys", "RSA configuration already present. Skipping generation.");
    }

    const clientsPath = path.join(this.config.repoPath, "data", "clients");
    const shouldDownloadClients =
      options.refreshAssets || !fs.existsSync(clientsPath) || fs.readdirSync(clientsPath).length === 0;
    if (shouldDownloadClients) {
      await reporter.stage("Client download", "Downloading the latest supported client assets.");
      await this.runInstalledTool(COMMAND_IDS.clientDownloader, "Client downloader", ["run-tool", "client-downloader"]);
    } else {
      await reporter.stage("Client download", "Client assets already present. Skipping download.");
    }

    const cachePath = path.join(this.config.repoPath, "data", "cache", "js5-0.jcache");
    const shouldDownloadCache = options.refreshAssets || !fs.existsSync(cachePath);
    if (shouldDownloadCache) {
      await reporter.stage("Cache download", "Refreshing the cache from the live JS5 servers.");
      await this.runInstalledTool(COMMAND_IDS.cacheDownloader, "Cache downloader", ["run-tool", "cache-downloader"]);
    } else {
      await reporter.stage("Cache download", "Cache already present. Skipping download.");
    }

    await reporter.stage("Client patcher", "Patching clients against the local config and RSA setup.");
    await this.runInstalledTool(COMMAND_IDS.clientPatcher, "Client patcher", ["run-tool", "client-patcher"]);

    await reporter.stage("Config validation", "Reloading server configuration.");
    const serverConfig = loadServerConfig(path.join(this.config.repoPath, "data", "config", "server.toml"));
    await reporter.stage(
      "Config validation",
      `OpenNXT build ${serverConfig.build} on game:${serverConfig.ports.game} http:${serverConfig.ports.http}`
    );

    const status = await this.serverController.status();
    if (status.running) {
      await reporter.stage("Server restart", `Stopping existing pid ${status.pid} before bootstrap start.`);
      this.assertAllowed(COMMAND_IDS.serverStop);
      await this.serverController.stop();
    }

    await reporter.stage("Server start", "Starting the OpenNXT server.");
    this.assertAllowed(COMMAND_IDS.serverStart);
    await this.serverController.start();

    const finalStatus = await this.serverController.status();
    await reporter.stage(
      "Smoke checks",
      `HTTP ${finalStatus.livePorts.http ? "up" : "down"}, Game ${finalStatus.livePorts.game ? "up" : "down"}`
    );
    return finalStatus;
  }

  async startServer() {
    this.assertAllowed(COMMAND_IDS.serverStart);
    return await this.serverController.start();
  }

  async stopServer() {
    this.assertAllowed(COMMAND_IDS.serverStop);
    return await this.serverController.stop();
  }

  async restartServer() {
    this.assertAllowed(COMMAND_IDS.serverRestart);
    return await this.serverController.restart();
  }

  async serverStatus() {
    return await this.serverController.status();
  }

  readServerLogs(stream: "stdout" | "stderr" | "both", lineCount: number) {
    return this.serverController.readLogs(stream, lineCount);
  }

  private assertAllowed(commandId: string) {
    const allowed = this.config.allowedCommandSet;
    if (allowed.length > 0 && !allowed.includes(commandId)) {
      throw new Error(`Command ${commandId} is disabled by OPENNXT_ALLOWED_COMMAND_SET`);
    }
  }

  private async runBatch(commandId: string, label: string, command: string, args: string[]) {
    this.assertAllowed(commandId);
    const logFile = path.join(this.config.logPath, `${commandId.replace(/\./g, "-")}-${Date.now()}.log`);
    return await this.executor.run({
      id: commandId,
      label,
      command,
      args,
      cwd: this.config.repoPath,
      shell: true,
      timeoutMs: 6 * 60 * 60 * 1000,
      logFile
    });
  }

  private async runInstalledTool(commandId: string, label: string, args: string[]) {
    const command = path.join(this.config.repoPath, "build", "install", "OpenNXT", "bin", "OpenNXT.bat");
    return await this.runBatch(commandId, label, command, args);
  }
}
