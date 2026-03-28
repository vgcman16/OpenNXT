import path from "node:path";
import { describe, expect, it } from "vitest";
import { loadConfig } from "../src/config";

describe("loadConfig", () => {
  it("normalizes defaults and seeds the allowlist with the owner", () => {
    const config = loadConfig({
      DISCORD_TOKEN: "token",
      DISCORD_APPLICATION_ID: "app",
      DISCORD_GUILD_ID: "guild",
      DISCORD_OWNER_ID: "owner",
      DISCORD_ALLOWED_USER_IDS: "user-a,user-b",
      GITHUB_WEBHOOK_SECRET: "secret",
      OPENNXT_REPO_PATH: ".."
    });

    expect(config.discord.allowlistedUserIds).toEqual(["owner", "user-a", "user-b"]);
    expect(config.github.repoOwner).toBe("vgcman16");
    expect(config.bot.dbPath.endsWith(path.join("runtime", "discord-bot.sqlite"))).toBe(true);
    expect(config.opennxt.launcherPath.endsWith(path.join("data", "launchers", "win", "original.exe"))).toBe(true);
  });
});
