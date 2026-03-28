import fs from "node:fs";
import path from "node:path";

export function ensureDirectory(directoryPath: string) {
  fs.mkdirSync(directoryPath, { recursive: true });
}

export function resolveExistingPath(...parts: string[]) {
  return path.resolve(...parts);
}

export function safeReadText(filePath: string) {
  return fs.existsSync(filePath) ? fs.readFileSync(filePath, "utf8") : "";
}
