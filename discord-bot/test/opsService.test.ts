import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { OpenNxtOpsService } from "../src/ops/OpenNxtOpsService";

class FakeExecutor {
  commands: Array<{ id: string; command: string; args: string[] }> = [];

  async run(spec: { id: string; command: string; args: string[]; logFile: string }) {
    this.commands.push({ id: spec.id, command: spec.command, args: spec.args });
    fs.mkdirSync(path.dirname(spec.logFile), { recursive: true });
    fs.writeFileSync(spec.logFile, "ok");
    return { exitCode: 0, durationMs: 1, logFile: spec.logFile, tail: "ok" };
  }
}

class FakeServerController {
  running = false;
  stopCalls = 0;
  startCalls = 0;

  async status() {
    return {
      running: this.running,
      pid: this.running ? 1234 : null,
      configuredPorts: { game: 43595, http: 8081, https: 8444 },
      livePorts: { game: this.running, http: this.running },
      stdoutLog: "stdout.log",
      stderrLog: "stderr.log"
    };
  }

  async start() {
    this.running = true;
    this.startCalls += 1;
    return { pid: 4321, stdoutLogPath: "stdout.log", stderrLogPath: "stderr.log" };
  }

  async stop() {
    this.running = false;
    this.stopCalls += 1;
    return true;
  }

  async restart() {
    await this.stop();
    return await this.start();
  }

  readLogs() {
    return "logs";
  }
}

class FakeReporter {
  stages: string[] = [];

  async start() {}
  async stage(name: string, detail: string) {
    this.stages.push(`${name}: ${detail}`);
  }
  async finish() {}
}

describe("OpenNxtOpsService", () => {
  const tempRoots: string[] = [];

  afterEach(() => {
    for (const root of tempRoots) {
      fs.rmSync(root, { recursive: true, force: true });
    }
    tempRoots.length = 0;
  });

  it("skips asset downloads when assets already exist and refresh is false", async () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "opennxt-ops-"));
    tempRoots.push(root);
    fs.mkdirSync(path.join(root, "data", "config"), { recursive: true });
    fs.mkdirSync(path.join(root, "data", "cache"), { recursive: true });
    fs.mkdirSync(path.join(root, "data", "clients", "946"), { recursive: true });
    fs.mkdirSync(path.join(root, "data", "prot", "946"), { recursive: true });
    fs.mkdirSync(path.join(root, "build", "install", "OpenNXT", "bin"), { recursive: true });
    fs.writeFileSync(path.join(root, "gradlew.bat"), "@echo off");
    fs.writeFileSync(path.join(root, "build", "install", "OpenNXT", "bin", "OpenNXT.bat"), "@echo off");
    fs.writeFileSync(path.join(root, "data", "config", "server.toml"), `
hostname = "127.0.0.1"
build = 946
configUrl = "http://127.0.0.1:8081/jav_config.ws?binaryType=6"

[networking.ports]
game = 43595
http = 8081
https = 8444
`);
    fs.writeFileSync(path.join(root, "data", "config", "rsa.toml"), "ok");
    fs.writeFileSync(path.join(root, "data", "cache", "js5-0.jcache"), "ok");
    fs.writeFileSync(path.join(root, "launcher.exe"), "ok");

    const executor = new FakeExecutor();
    const serverController = new FakeServerController();
    const reporter = new FakeReporter();
    const service = new OpenNxtOpsService(
      {
        repoPath: root,
        launcherPath: path.join(root, "launcher.exe"),
        logPath: path.join(root, "logs"),
        allowedCommandSet: []
      },
      executor as any,
      serverController as any,
      { info() {}, error() {} } as any
    );

    await service.bootstrap({ refreshAssets: false }, reporter as any);

    expect(executor.commands.map((command) => command.id)).toEqual([
      "gradle.build_install",
      "tool.client_patcher"
    ]);
    expect(serverController.startCalls).toBe(1);
  });
});
