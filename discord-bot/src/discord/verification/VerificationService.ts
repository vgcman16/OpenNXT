import { GuildMember, type ChatInputCommandInteraction } from "discord.js";
import type { SqliteStore } from "../../persistence/SqliteStore";
import { ChannelAnnouncer } from "../ChannelAnnouncer";

export class VerificationService {
  constructor(
    private readonly store: SqliteStore,
    private readonly announcer: ChannelAnnouncer
  ) {}

  async verify(interaction: ChatInputCommandInteraction) {
    const member = interaction.member;
    if (!interaction.inCachedGuild() || !(member instanceof GuildMember)) {
      await interaction.reply({ content: "Verification only works inside a server.", ephemeral: true });
      return;
    }

    const verifiedRoleId = this.store.getBinding("role", "Verified");
    const communityRoleId = this.store.getBinding("role", "Community");

    if (!verifiedRoleId || !communityRoleId) {
      await interaction.reply({ content: "Run `/community scaffold` first.", ephemeral: true });
      return;
    }

    await member.roles.add([verifiedRoleId, communityRoleId]);
    await interaction.reply({
      content: "You are verified. Community and playtesting channels are now unlocked.",
      ephemeral: true
    });
    await this.announcer.send(
      "mod-log",
      "Verification Completed",
      `<@${member.id}> completed self-verification.`,
      "Green"
    );
  }
}
