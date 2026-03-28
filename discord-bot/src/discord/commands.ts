import { SlashCommandBuilder } from "discord.js";

export const slashCommands = [
  new SlashCommandBuilder()
    .setName("community")
    .setDescription("Community bootstrap commands")
    .addSubcommand((subcommand) =>
      subcommand.setName("scaffold").setDescription("Create the OpenNXT Discord structure")
    ),
  new SlashCommandBuilder()
    .setName("verify")
    .setDescription("Verification commands")
    .addSubcommand((subcommand) =>
      subcommand.setName("start").setDescription("Unlock the verified community channels")
    ),
  new SlashCommandBuilder()
    .setName("ticket")
    .setDescription("Support ticket commands")
    .addSubcommand((subcommand) =>
      subcommand
        .setName("create")
        .setDescription("Create a private support ticket")
        .addStringOption((option) =>
          option.setName("subject").setDescription("Short reason for the ticket").setRequired(true)
        )
    )
    .addSubcommand((subcommand) =>
      subcommand
        .setName("close")
        .setDescription("Close the current support ticket")
        .addStringOption((option) =>
          option.setName("reason").setDescription("Optional close reason").setRequired(false)
        )
    ),
  new SlashCommandBuilder()
    .setName("setup")
    .setDescription("OpenNXT setup commands")
    .addSubcommand((subcommand) =>
      subcommand.setName("audit").setDescription("Audit the current OpenNXT host state")
    )
    .addSubcommand((subcommand) =>
      subcommand
        .setName("bootstrap")
        .setDescription("Run the staged OpenNXT bootstrap flow")
        .addBooleanOption((option) =>
          option.setName("confirm").setDescription("Required to execute the bootstrap").setRequired(true)
        )
        .addBooleanOption((option) =>
          option
            .setName("refresh_assets")
            .setDescription("Force client and cache refresh even when local assets already exist")
            .setRequired(false)
        )
    ),
  new SlashCommandBuilder()
    .setName("server")
    .setDescription("OpenNXT server lifecycle commands")
    .addSubcommand((subcommand) =>
      subcommand.setName("start").setDescription("Start the OpenNXT game server")
    )
    .addSubcommand((subcommand) =>
      subcommand
        .setName("stop")
        .setDescription("Stop the OpenNXT game server")
        .addBooleanOption((option) =>
          option.setName("confirm").setDescription("Required to stop the server").setRequired(true)
        )
    )
    .addSubcommand((subcommand) =>
      subcommand
        .setName("restart")
        .setDescription("Restart the OpenNXT game server")
        .addBooleanOption((option) =>
          option.setName("confirm").setDescription("Required to restart the server").setRequired(true)
        )
    )
    .addSubcommand((subcommand) =>
      subcommand.setName("status").setDescription("Show the OpenNXT runtime status")
    )
    .addSubcommand((subcommand) =>
      subcommand
        .setName("logs")
        .setDescription("Show the latest OpenNXT server log lines")
        .addStringOption((option) =>
          option
            .setName("stream")
            .setDescription("Which stream to read")
            .addChoices(
              { name: "stdout", value: "stdout" },
              { name: "stderr", value: "stderr" },
              { name: "both", value: "both" }
            )
            .setRequired(false)
        )
        .addIntegerOption((option) =>
          option.setName("lines").setDescription("Number of lines to return").setRequired(false).setMinValue(5).setMaxValue(100)
        )
    ),
  new SlashCommandBuilder()
    .setName("github")
    .setDescription("GitHub integration commands")
    .addSubcommand((subcommand) =>
      subcommand.setName("status").setDescription("Show the GitHub webhook integration status")
    )
].map((command) => command.toJSON());
