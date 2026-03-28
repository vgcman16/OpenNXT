import fs from "node:fs";

export function tailFile(filePath: string, lineCount: number) {
  if (!fs.existsSync(filePath)) {
    return "";
  }

  const content = fs.readFileSync(filePath, "utf8");
  return content
    .split(/\r?\n/)
    .filter(Boolean)
    .slice(-lineCount)
    .join("\n");
}
