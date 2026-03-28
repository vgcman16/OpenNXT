import fs from "node:fs";

export interface OpenNxtServerConfig {
  hostname: string;
  build: number;
  configUrl: string;
  ports: {
    game: number;
    http: number;
    https: number;
  };
}

const DEFAULT_CONFIG: OpenNxtServerConfig = {
  hostname: "127.0.0.1",
  build: 918,
  configUrl: "http://127.0.0.1:8080/jav_config.ws?binaryType=2",
  ports: {
    game: 43594,
    http: 8080,
    https: 8443
  }
};

function readValue(source: string, key: string) {
  const match = source.match(new RegExp(`^${key}\\s*=\\s*"?(.*?)"?$`, "m"));
  return match?.[1] ?? null;
}

function readPort(source: string, key: keyof OpenNxtServerConfig["ports"], fallback: number) {
  const sectionMatch = source.match(/\[networking\.ports\]([\s\S]*)/m);
  if (!sectionMatch) {
    return fallback;
  }

  const portMatch = sectionMatch[1].match(new RegExp(`^${key}\\s*=\\s*(\\d+)$`, "m"));
  return portMatch ? Number(portMatch[1]) : fallback;
}

export function loadServerConfig(filePath: string): OpenNxtServerConfig {
  if (!fs.existsSync(filePath)) {
    throw new Error(`Missing server config at ${filePath}`);
  }

  const raw = fs.readFileSync(filePath, "utf8");
  const build = Number(readValue(raw, "build") ?? DEFAULT_CONFIG.build);

  return {
    hostname: readValue(raw, "hostname") ?? DEFAULT_CONFIG.hostname,
    build: Number.isFinite(build) ? build : DEFAULT_CONFIG.build,
    configUrl: readValue(raw, "configUrl") ?? DEFAULT_CONFIG.configUrl,
    ports: {
      game: readPort(raw, "game", DEFAULT_CONFIG.ports.game),
      http: readPort(raw, "http", DEFAULT_CONFIG.ports.http),
      https: readPort(raw, "https", DEFAULT_CONFIG.ports.https)
    }
  };
}
