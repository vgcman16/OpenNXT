import {
  ChannelType,
  GuildMember,
  OverwriteType,
  PermissionFlagsBits,
  type ChatInputCommandInteraction,
  type TextChannel
} from "discord.js";
import { STAFF_ROLE_NAMES } from "../blueprint";
import type { SqliteStore } from "../../persistence/SqliteStore";
import { ChannelAnnouncer } from "../ChannelAnnouncer";

function buildTicketChannelName(subject: string, username: string) {
  const sanitizedSubject = subject
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 20);
  const sanitizedUser = username
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 12);
  return `ticket-${sanitizedUser}-${sanitizedSubject || "help"}`;
}

export class TicketService {
  constructor(
    private readonly store: SqliteStore,
    private readonly announcer: ChannelAnnouncer
  ) {}

  async create(interaction: ChatInputCommandInteraction, subject: string) {
    if (!interaction.inCachedGuild() || !(interaction.member instanceof GuildMember)) {
      await interaction.reply({ content: "Tickets only work inside a server.", ephemeral: true });
      return;
    }

    const existing = this.store.getOpenTicketForRequester(interaction.user.id);
    if (existing) {
      await interaction.reply({
        content: `You already have an open ticket: <#${existing.channelId}>`,
        ephemeral: true
      });
      return;
    }

    const supportChannelId = this.store.getBinding("channel", "support-tickets");
    const reviewChannelId = this.store.getBinding("channel", "ticket-review");
    if (!supportChannelId || !reviewChannelId) {
      await interaction.reply({ content: "Run `/community scaffold` first.", ephemeral: true });
      return;
    }

    const supportChannel = await interaction.guild.channels.fetch(supportChannelId);
    if (!supportChannel?.isTextBased()) {
      await interaction.reply({ content: "Support ticket channel is not configured.", ephemeral: true });
      return;
    }

    const permissionOverwrites = [
      {
        id: interaction.guild.roles.everyone.id,
        type: OverwriteType.Role,
        deny: [PermissionFlagsBits.ViewChannel]
      },
      {
        id: interaction.user.id,
        type: OverwriteType.Member,
        allow: [
          PermissionFlagsBits.ViewChannel,
          PermissionFlagsBits.ReadMessageHistory,
          PermissionFlagsBits.SendMessages,
          PermissionFlagsBits.AttachFiles
        ]
      }
    ];

    for (const roleName of STAFF_ROLE_NAMES) {
      const roleId = this.store.getBinding("role", roleName);
      if (!roleId) {
        continue;
      }
      permissionOverwrites.push({
        id: roleId,
        type: OverwriteType.Role,
        allow: [
          PermissionFlagsBits.ViewChannel,
          PermissionFlagsBits.ReadMessageHistory,
          PermissionFlagsBits.SendMessages,
          PermissionFlagsBits.ManageChannels
        ]
      });
    }

    const channel = await interaction.guild.channels.create({
      name: buildTicketChannelName(subject, interaction.user.username),
      type: ChannelType.GuildText,
      parent: supportChannel.parentId ?? undefined,
      permissionOverwrites
    });

    this.store.createTicket(interaction.user.id, channel.id, subject);

    await channel.send(
      `Support ticket opened by <@${interaction.user.id}>.\nSubject: ${subject}\nA staff member will pick this up here.`
    );
    await interaction.reply({
      content: `Ticket created: <#${channel.id}>`,
      ephemeral: true
    });
    await this.announcer.send(
      "ticket-review",
      "New Support Ticket",
      `${interaction.user.tag} opened <#${channel.id}> with subject: ${subject}`,
      "Orange"
    );
  }

  async close(interaction: ChatInputCommandInteraction, reason: string | null) {
    if (!interaction.inCachedGuild() || !(interaction.member instanceof GuildMember) || !interaction.channel) {
      await interaction.reply({ content: "Ticket close only works inside a ticket channel.", ephemeral: true });
      return;
    }

    const ticket = this.store.getTicketByChannel(interaction.channelId);
    if (!ticket || ticket.status !== "open") {
      await interaction.reply({ content: "This channel is not an open ticket.", ephemeral: true });
      return;
    }

    const channel = interaction.channel as TextChannel;
    this.store.closeTicket(channel.id, interaction.user.id);
    await channel.permissionOverwrites.edit(ticket.requesterId, {
      ViewChannel: false
    });
    await channel.setName(`closed-${channel.name}`.slice(0, 95));
    await interaction.reply({
      content: `Ticket closed.${reason ? ` Reason: ${reason}` : ""}`
    });
    await this.announcer.send(
      "ticket-review",
      "Ticket Closed",
      `Channel <#${channel.id}> closed by ${interaction.user.tag}.${reason ? ` Reason: ${reason}` : ""}`,
      "Grey"
    );
  }
}
