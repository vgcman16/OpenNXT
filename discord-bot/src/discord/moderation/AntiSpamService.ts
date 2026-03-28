import type { Collection, Message } from "discord.js";
import type { SqliteStore } from "../../persistence/SqliteStore";
import { hasStaffRole } from "../permissions";
import { ChannelAnnouncer } from "../ChannelAnnouncer";

interface RecentMessage {
  timestamp: number;
  links: number;
}

const URL_REGEX = /https?:\/\/\S+/gi;

export class AntiSpamService {
  private readonly history = new Map<string, RecentMessage[]>();

  constructor(
    private readonly store: SqliteStore,
    private readonly announcer: ChannelAnnouncer,
    private readonly configuredStaffRoleIds: string[]
  ) {}

  async handle(message: Message<boolean>) {
    if (!message.inGuild() || message.author.bot || !message.member) {
      return;
    }

    if (hasStaffRole(message.member, this.store, this.configuredStaffRoleIds)) {
      return;
    }

    const now = Date.now();
    const links = (message.content.match(URL_REGEX) ?? []).length;
    const existing = this.history.get(message.author.id) ?? [];
    const recent = existing.filter((entry) => now - entry.timestamp < 10_000);
    recent.push({ timestamp: now, links });
    this.history.set(message.author.id, recent);

    const messageBurst = recent.length >= 5;
    const linkBurst = recent.reduce((sum, entry) => sum + entry.links, 0) >= 3;

    if (!messageBurst && !linkBurst) {
      return;
    }

    if (message.deletable) {
      await message.delete();
    }

    await this.announcer.send(
      "mod-log",
      "Anti-Spam Triggered",
      `${message.author.tag} tripped the anti-spam guard in <#${message.channelId}>.`,
      "Red"
    );
  }
}
