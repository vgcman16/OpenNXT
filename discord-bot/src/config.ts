import path from "node:path";
import { z } from "zod";

const CsvString = z.string().transform((value) =>
  value
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean)
);

const RawConfigSchema = z.object({
  DISCORD_TOKEN: z.string().min(1),
  DISCORD_APPLICATION_ID: z.string().min(1),
  DISCORD_GUILD_ID: z.string().min(1),
  DISCORD_OWNER_ID: z.string().min(1),
  DISCORD_STAFF_ROLE_IDS: z.string().default(""),
  DISCORD_ALLOWED_USER_IDS: z.string().default(""),
  GITHUB_WEBHOOK_SECRET: z.string().min(1),
  GITHUB_REPO_OWNER: z.string().min(1).default("vgcman16"),
  GITHUB_REPO_NAME: z.string().min(1).default("OpenNXT"),
  GITHUB_WEBHOOK_PORT: z.coerce.number().int().positive().default(3001),
  BOT_DATA_DIR: z.string().default("./runtime"),
  BOT_DB_PATH: z.string().optional(),
  BOT_LOG_LEVEL: z.string().default("info"),
  OPENNXT_REPO_PATH: z.string().min(1),
  OPENNXT_LAUNCHER_PATH: z.string().optional(),
  OPENNXT_JAVA_HOME: z.string().optional(),
  OPENNXT_LOG_PATH: z.string().optional(),
  OPENNXT_ALLOWED_COMMAND_SET: z.string().default("")
});

export type BotConfig = ReturnType<typeof loadConfig>;

export function loadConfig(env: NodeJS.ProcessEnv = process.env) {
  const raw = RawConfigSchema.parse(env);

  const repoPath = path.resolve(raw.OPENNXT_REPO_PATH);
  const dataDir = path.resolve(raw.BOT_DATA_DIR);
  const dbPath = raw.BOT_DB_PATH
    ? path.resolve(raw.BOT_DB_PATH)
    : path.join(dataDir, "discord-bot.sqlite");
  const logPath = raw.OPENNXT_LOG_PATH
    ? path.resolve(raw.OPENNXT_LOG_PATH)
    : path.join(dataDir, "logs");
  const launcherPath = raw.OPENNXT_LAUNCHER_PATH
    ? path.resolve(raw.OPENNXT_LAUNCHER_PATH)
    : path.join(repoPath, "data", "launchers", "win", "original.exe");
  const javaHome = raw.OPENNXT_JAVA_HOME ? path.resolve(raw.OPENNXT_JAVA_HOME) : undefined;
  const allowlistedUserIds = CsvString.parse(raw.DISCORD_ALLOWED_USER_IDS);
  const configuredStaffRoleIds = CsvString.parse(raw.DISCORD_STAFF_ROLE_IDS);
  const allowedCommandSet = CsvString.parse(raw.OPENNXT_ALLOWED_COMMAND_SET);

  return {
    discord: {
      token: raw.DISCORD_TOKEN,
      applicationId: raw.DISCORD_APPLICATION_ID,
      guildId: raw.DISCORD_GUILD_ID,
      ownerId: raw.DISCORD_OWNER_ID,
      configuredStaffRoleIds,
      allowlistedUserIds: Array.from(new Set([raw.DISCORD_OWNER_ID, ...allowlistedUserIds]))
    },
    github: {
      webhookSecret: raw.GITHUB_WEBHOOK_SECRET,
      repoOwner: raw.GITHUB_REPO_OWNER,
      repoName: raw.GITHUB_REPO_NAME,
      webhookPort: raw.GITHUB_WEBHOOK_PORT
    },
    bot: {
      dataDir,
      dbPath,
      logLevel: raw.BOT_LOG_LEVEL
    },
    opennxt: {
      repoPath,
      launcherPath,
      javaHome,
      logPath,
      allowedCommandSet
    }
  };
}
