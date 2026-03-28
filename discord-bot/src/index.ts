import http from "node:http";
import path from "node:path";
import {
  ChannelType,
  Client,
  EmbedBuilder,
  GatewayIntentBits,
  GuildMember,
  MessageFlags,
  Partials,
  PermissionsBitField,
  type ChatInputCommandInteraction,
  type ColorResolvable
} from "discord.js";
import { loadConfig } from "./config";
import { createLogger } from "./logger";
import { ensureDirectory } from "./util/fs";
import { SqliteStore } from "./persistence/SqliteStore";
import { slashCommands } from "./discord/commands";
import { DiscordGuildAdapter } from "./discord/provisioning/DiscordGuildAdapter";
import { GuildProvisioner } from "./discord/provisioning/GuildProvisioner";
import { ChannelAnnouncer } from "./discord/ChannelAnnouncer";
import { VerificationService } from "./discord/verification/VerificationService";
import { TicketService } from "./discord/tickets/TicketService";
import { AntiSpamService } from "./discord/moderation/AntiSpamService";
import { canRunHostCommand } from "./discord/permissions";
import { ProcessExecutor } from "./ops/ProcessExecutor";
import { ServerController } from "./ops/ServerController";
import { OpenNxtOpsService } from "./ops/OpenNxtOpsService";
import { JobCoordinator, type JobProgressReporter } from "./ops/JobCoordinator";
import { GitHubWebhookService } from "./github/GitHubWebhookService";
import { createWebhookApp } from "./github/createWebhookApp";
import type { AuditReport, JobRecord, JobStatus } from "./types";

function createEmbed(title: string, description: string, color: ColorResolvable = "Blurple") {
  return [
    new EmbedBuilder()
      .setTitle(title)
      .setDescription(description)
      .setColor(color)
  ];
}

function renderAudit(report: AuditReport) {
  return [
    report.summary,
    ...report.findings.map((finding) => `${finding.ok ? "OK" : "FAIL"} ${finding.label}: ${finding.detail}`)
  ].join("\n");
}

function truncateForCodeBlock(value: string, maxLength = 1800) {
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, maxLength)}\n...truncated...`;
}

class InteractionJobReporter implements JobProgressReporter {
  constructor(
    private readonly interaction: ChatInputCommandInteraction,
    private readonly opsAnnouncer: ChannelAnnouncer,
    private readonly publicAnnouncer: ChannelAnnouncer
  ) {}

  async start(job: JobRecord) {
    await this.interaction.editReply({
      embeds: createEmbed(`Job Started: ${job.kind}`, `Job id: ${job.id}\nStatus: starting`)
    });
  }

  async stage(name: string, detail: string) {
    await this.interaction.editReply({
      embeds: createEmbed(name, detail)
    });
  }

  async finish(status: Exclude<JobStatus, "running">, detail: string) {
    const color: ColorResolvable = status === "succeeded" ? "Green" : status === "failed" ? "Red" : "Orange";
    await this.interaction.editReply({
      embeds: createEmbed(`Job ${status}`, detail, color)
    });

    await this.opsAnnouncer.send("ops-console", `Job ${status}`, detail, color);
    if (status === "succeeded") {
      await this.publicAnnouncer.send("server-status", "OpenNXT Update", detail, color);
    }
  }
}

function scaffoldAllowed(interaction: ChatInputCommandInteraction, store: SqliteStore, ownerId: string) {
  if (!interaction.inCachedGuild() || !(interaction.member instanceof GuildMember)) {
    return false;
  }

  return (
    interaction.user.id === ownerId ||
    store.isUserAllowlisted(interaction.user.id) ||
    interaction.member.permissions.has(PermissionsBitField.Flags.ManageGuild)
  );
}

function formatServerStatus(status: Awaited<ReturnType<OpenNxtOpsService["serverStatus"]>>) {
  return [
    `Running: ${status.running ? "yes" : "no"}`,
    `PID: ${status.pid ?? "n/a"}`,
    `Configured ports: game=${status.configuredPorts.game}, http=${status.configuredPorts.http}, https=${status.configuredPorts.https}`,
    `Live ports: game=${status.livePorts.game ? "open" : "closed"}, http=${status.livePorts.http ? "open" : "closed"}`,
    `stdout: ${status.stdoutLog}`,
    `stderr: ${status.stderrLog}`
  ].join("\n");
}

async function main() {
  const config = loadConfig();
  ensureDirectory(config.bot.dataDir);
  ensureDirectory(config.opennxt.logPath);

  const logger = createLogger(config.bot.logLevel);
  const store = new SqliteStore(config.bot.dbPath);
  store.ensureAllowlist(config.discord.allowlistedUserIds);

  const client = new Client({
    intents: [
      GatewayIntentBits.Guilds,
      GatewayIntentBits.GuildMembers,
      GatewayIntentBits.GuildMessages,
      GatewayIntentBits.MessageContent
    ],
    partials: [Partials.Channel]
  });

  const announcer = new ChannelAnnouncer(client, store);
  const verificationService = new VerificationService(store, announcer);
  const ticketService = new TicketService(store, announcer);
  const antiSpamService = new AntiSpamService(store, announcer, config.discord.configuredStaffRoleIds);

  const processExecutor = new ProcessExecutor(logger);
  const serverController = new ServerController(
    {
      repoPath: config.opennxt.repoPath,
      javaHome: config.opennxt.javaHome,
      logPath: config.opennxt.logPath
    },
    store,
    logger
  );
  const opsService = new OpenNxtOpsService(
    {
      repoPath: config.opennxt.repoPath,
      launcherPath: config.opennxt.launcherPath,
      javaHome: config.opennxt.javaHome,
      logPath: path.join(config.opennxt.logPath, "ops"),
      allowedCommandSet: config.opennxt.allowedCommandSet
    },
    processExecutor,
    serverController,
    logger
  );
  const jobCoordinator = new JobCoordinator(store);

  const githubWebhookService = new GitHubWebhookService(
    {
      secret: config.github.webhookSecret,
      repoOwner: config.github.repoOwner,
      repoName: config.github.repoName
    },
    store,
    announcer,
    logger
  );
  const webhookApp = createWebhookApp(githubWebhookService);
  const webhookServer = http.createServer(webhookApp);

  client.once("ready", async () => {
    logger.info({ botUser: client.user?.tag }, "Discord bot ready");
    const guild = await client.guilds.fetch(config.discord.guildId);
    await guild.commands.set(slashCommands);
    logger.info({ guildId: guild.id }, "Registered guild slash commands");
  });

  client.on("interactionCreate", async (interaction) => {
    if (!interaction.isChatInputCommand()) {
      return;
    }

    try {
      if (interaction.commandName === "community" && interaction.options.getSubcommand() === "scaffold") {
        if (!scaffoldAllowed(interaction, store, config.discord.ownerId)) {
          await interaction.reply({
            content: "You are not allowed to scaffold the Discord server.",
            flags: MessageFlags.Ephemeral
          });
          return;
        }

        await interaction.deferReply();
        const guild = interaction.guild;
        if (!guild) {
          await interaction.editReply("This command must be used in a guild.");
          return;
        }

        const provisioner = new GuildProvisioner(new DiscordGuildAdapter(guild), store);
        await provisioner.scaffold();
        store.setSetting("guild.id", guild.id);
        await interaction.editReply({
          embeds: createEmbed(
            "OpenNXT Community Scaffolded",
            "Roles, categories, channels, permissions, and seed messages are in place.",
            "Green"
          )
        });
        await announcer.send("ops-console", "Community Scaffold Complete", "The OpenNXT Discord structure is ready.", "Green");
        return;
      }

      if (interaction.commandName === "verify" && interaction.options.getSubcommand() === "start") {
        await verificationService.verify(interaction);
        return;
      }

      if (interaction.commandName === "ticket" && interaction.options.getSubcommand() === "create") {
        const subject = interaction.options.getString("subject", true);
        await ticketService.create(interaction, subject);
        return;
      }

      if (interaction.commandName === "ticket" && interaction.options.getSubcommand() === "close") {
        const reason = interaction.options.getString("reason");
        await ticketService.close(interaction, reason);
        return;
      }

      if (!interaction.inCachedGuild() || !(interaction.member instanceof GuildMember)) {
        await interaction.reply({
          content: "This command must be used in a guild.",
          flags: MessageFlags.Ephemeral
        });
        return;
      }

      const canOperate = canRunHostCommand(interaction.member, store, config.discord.configuredStaffRoleIds);

      if (interaction.commandName === "setup" && interaction.options.getSubcommand() === "audit") {
        if (!canOperate) {
          await interaction.reply({ content: "You are not allowed to run host audit commands.", flags: MessageFlags.Ephemeral });
          return;
        }

        const report = await opsService.audit();
        await interaction.reply({
          embeds: createEmbed("OpenNXT Host Audit", renderAudit(report), report.findings.every((item) => item.ok) ? "Green" : "Orange")
        });
        return;
      }

      if (interaction.commandName === "setup" && interaction.options.getSubcommand() === "bootstrap") {
        if (!canOperate) {
          await interaction.reply({ content: "You are not allowed to run bootstrap commands.", flags: MessageFlags.Ephemeral });
          return;
        }

        const confirm = interaction.options.getBoolean("confirm", true);
        if (!confirm) {
          await interaction.reply({ content: "Set `confirm` to true to run the bootstrap.", flags: MessageFlags.Ephemeral });
          return;
        }

        await interaction.deferReply();
        const reporter = new InteractionJobReporter(interaction, announcer, announcer);
        await jobCoordinator.runExclusive("setup.bootstrap", reporter, async () => {
          await opsService.bootstrap(
            {
              refreshAssets: interaction.options.getBoolean("refresh_assets") ?? false
            },
            reporter
          );
          return true;
        });
        return;
      }

      if (interaction.commandName === "server" && interaction.options.getSubcommand() === "status") {
        if (!canOperate) {
          await interaction.reply({ content: "You are not allowed to view host status.", flags: MessageFlags.Ephemeral });
          return;
        }

        const status = await opsService.serverStatus();
        await interaction.reply({
          embeds: createEmbed("OpenNXT Server Status", formatServerStatus(status), status.running ? "Green" : "Orange")
        });
        return;
      }

      if (interaction.commandName === "server" && interaction.options.getSubcommand() === "logs") {
        if (!canOperate) {
          await interaction.reply({ content: "You are not allowed to read host logs.", flags: MessageFlags.Ephemeral });
          return;
        }

        const stream = (interaction.options.getString("stream") ?? "both") as "stdout" | "stderr" | "both";
        const lines = interaction.options.getInteger("lines") ?? 30;
        const logs = opsService.readServerLogs(stream, lines);
        await interaction.reply({
          content: `\`\`\`\n${truncateForCodeBlock(logs || "No logs available.")}\n\`\`\``,
          flags: MessageFlags.Ephemeral
        });
        return;
      }

      if (interaction.commandName === "server" && interaction.options.getSubcommand() === "start") {
        if (!canOperate) {
          await interaction.reply({ content: "You are not allowed to start the server.", flags: MessageFlags.Ephemeral });
          return;
        }

        await interaction.deferReply();
        const reporter = new InteractionJobReporter(interaction, announcer, announcer);
        await jobCoordinator.runExclusive("server.start", reporter, async () => {
          await reporter.stage("Server start", "Starting OpenNXT.");
          const status = await opsService.startServer();
          await reporter.stage("Smoke checks", `Started pid ${status.pid}.`);
          return status;
        });
        return;
      }

      if (interaction.commandName === "server" && interaction.options.getSubcommand() === "stop") {
        if (!canOperate) {
          await interaction.reply({ content: "You are not allowed to stop the server.", flags: MessageFlags.Ephemeral });
          return;
        }

        const confirm = interaction.options.getBoolean("confirm", true);
        if (!confirm) {
          await interaction.reply({ content: "Set `confirm` to true to stop the server.", flags: MessageFlags.Ephemeral });
          return;
        }

        await interaction.deferReply();
        const reporter = new InteractionJobReporter(interaction, announcer, announcer);
        await jobCoordinator.runExclusive("server.stop", reporter, async () => {
          await reporter.stage("Server stop", "Stopping OpenNXT.");
          const stopped = await opsService.stopServer();
          await reporter.stage("Server stop", stopped ? "OpenNXT stopped." : "No bot-managed server was running.");
          return stopped;
        });
        return;
      }

      if (interaction.commandName === "server" && interaction.options.getSubcommand() === "restart") {
        if (!canOperate) {
          await interaction.reply({ content: "You are not allowed to restart the server.", flags: MessageFlags.Ephemeral });
          return;
        }

        const confirm = interaction.options.getBoolean("confirm", true);
        if (!confirm) {
          await interaction.reply({ content: "Set `confirm` to true to restart the server.", flags: MessageFlags.Ephemeral });
          return;
        }

        await interaction.deferReply();
        const reporter = new InteractionJobReporter(interaction, announcer, announcer);
        await jobCoordinator.runExclusive("server.restart", reporter, async () => {
          await reporter.stage("Server restart", "Restarting OpenNXT.");
          const status = await opsService.restartServer();
          await reporter.stage("Smoke checks", `Restarted pid ${status.pid}.`);
          return status;
        });
        return;
      }

      if (interaction.commandName === "github" && interaction.options.getSubcommand() === "status") {
        if (!canOperate) {
          await interaction.reply({ content: "You are not allowed to read GitHub status.", flags: MessageFlags.Ephemeral });
          return;
        }

        const deliveries = store
          .listRecentGithubDeliveries(5)
          .map((delivery) => `${delivery.receivedAt} - ${delivery.eventName} (${delivery.deliveryId})`)
          .join("\n");
        await interaction.reply({
          embeds: createEmbed(
            "GitHub Integration Status",
            `Repo: ${config.github.repoOwner}/${config.github.repoName}\nRecent deliveries:\n${deliveries || "None yet."}`,
            "Blurple"
          )
        });
        return;
      }

      await interaction.reply({ content: "Command handler not implemented.", flags: MessageFlags.Ephemeral });
    } catch (error) {
      logger.error({ err: error }, "Interaction handler failed");
      if (interaction.deferred || interaction.replied) {
        await interaction.editReply({
          embeds: createEmbed(
            "Command Failed",
            error instanceof Error ? error.message : String(error),
            "Red"
          )
        });
      } else {
        await interaction.reply({
          content: error instanceof Error ? error.message : String(error),
          flags: MessageFlags.Ephemeral
        });
      }
    }
  });

  client.on("messageCreate", async (message) => {
    try {
      await antiSpamService.handle(message);
    } catch (error) {
      logger.error({ err: error }, "Anti-spam handler failed");
    }
  });

  webhookServer.listen(config.github.webhookPort, () => {
    logger.info({ port: config.github.webhookPort }, "GitHub webhook server listening");
  });

  await client.login(config.discord.token);

  const shutdown = async () => {
    logger.info("Shutting down Discord bot");
    webhookServer.close();
    await client.destroy();
    store.close();
    process.exit(0);
  };

  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

main().catch((error) => {
  // eslint-disable-next-line no-console
  console.error(error);
  process.exit(1);
});
