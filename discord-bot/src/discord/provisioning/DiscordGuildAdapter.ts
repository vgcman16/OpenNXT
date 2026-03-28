import {
  ChannelType,
  type Guild,
  type GuildBasedChannel,
  type GuildTextBasedChannel,
  OverwriteType,
  PermissionFlagsBits
} from "discord.js";
import type { PermissionRule, ProvisionedChannel, ProvisionedRole, ProvisioningAdapter } from "./types";

const PERMISSION_MAP = {
  ViewChannel: PermissionFlagsBits.ViewChannel,
  ReadMessageHistory: PermissionFlagsBits.ReadMessageHistory,
  SendMessages: PermissionFlagsBits.SendMessages
} as const;

function resolvePermissionFlags(names: string[]) {
  return names.map((name) => PERMISSION_MAP[name as keyof typeof PERMISSION_MAP]).filter(Boolean);
}

export class DiscordGuildAdapter implements ProvisioningAdapter {
  constructor(private readonly guild: Guild) {}

  async ensureRole(name: string): Promise<ProvisionedRole> {
    await this.guild.roles.fetch();
    let role = this.guild.roles.cache.find((candidate) => candidate.name === name);
    if (!role) {
      role = await this.guild.roles.create({ name, mentionable: false });
    }
    return { id: role.id, name: role.name };
  }

  async ensureCategory(name: string, overwrites: PermissionRule[]): Promise<ProvisionedChannel> {
    const existing = await this.findChannel(name, ChannelType.GuildCategory);
    if (existing) {
      await existing.edit({ permissionOverwrites: this.resolveOverwrites(overwrites) });
      return { id: existing.id, name: existing.name, parentId: null, kind: "category" };
    }

    const created = await this.guild.channels.create({
      name,
      type: ChannelType.GuildCategory,
      permissionOverwrites: this.resolveOverwrites(overwrites)
    });
    return { id: created.id, name: created.name, parentId: null, kind: "category" };
  }

  async ensureTextChannel(input: {
    name: string;
    parentId: string;
    topic?: string;
    overwrites: PermissionRule[];
  }): Promise<ProvisionedChannel> {
    const existing = await this.findChannel(input.name, ChannelType.GuildText);
    if (existing?.type === ChannelType.GuildText) {
      await existing.edit({
        parent: input.parentId,
        topic: input.topic,
        permissionOverwrites: this.resolveOverwrites(input.overwrites)
      });
      return {
        id: existing.id,
        name: existing.name,
        parentId: existing.parentId,
        kind: "text"
      };
    }

    const created = await this.guild.channels.create({
      name: input.name,
      type: ChannelType.GuildText,
      parent: input.parentId,
      topic: input.topic,
      permissionOverwrites: this.resolveOverwrites(input.overwrites)
    });

    return {
      id: created.id,
      name: created.name,
      parentId: created.parentId,
      kind: "text"
    };
  }

  async sendSeedMessages(channelId: string, messages: string[]) {
    const channel = await this.guild.channels.fetch(channelId);
    if (!channel?.isTextBased()) {
      return;
    }

    const textChannel = channel as GuildTextBasedChannel;
    const existingMessages = await textChannel.messages.fetch({ limit: 1 });
    if (existingMessages.size > 0) {
      return;
    }

    for (const message of messages) {
      await textChannel.send(message);
    }
  }

  private async findChannel(name: string, type: ChannelType) {
    await this.guild.channels.fetch();
    return this.guild.channels.cache.find(
      (channel) => channel?.name === name && channel.type === type
    ) as GuildBasedChannel | undefined;
  }

  private resolveOverwrites(overwrites: PermissionRule[]) {
    return overwrites.map((rule) => {
      if (rule.kind === "everyone") {
        return {
          id: this.guild.roles.everyone.id,
          type: OverwriteType.Role,
          allow: resolvePermissionFlags(rule.allow),
          deny: resolvePermissionFlags(rule.deny)
        };
      }

      const role = this.guild.roles.cache.find((candidate) => candidate.name === rule.roleName);
      if (!role) {
        throw new Error(`Missing role for permission overwrite: ${rule.roleName}`);
      }

      return {
        id: role.id,
        type: OverwriteType.Role,
        allow: resolvePermissionFlags(rule.allow),
        deny: resolvePermissionFlags(rule.deny)
      };
    });
  }
}
