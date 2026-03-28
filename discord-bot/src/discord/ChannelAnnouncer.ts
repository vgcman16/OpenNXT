import { EmbedBuilder, type Client, type ColorResolvable } from "discord.js";
import type { SqliteStore } from "../persistence/SqliteStore";

export class ChannelAnnouncer {
  constructor(
    private readonly client: Client,
    private readonly store: SqliteStore
  ) {}

  async send(bindingName: string, title: string, description: string, color: ColorResolvable = "Blurple") {
    const channelId = this.store.getBinding("channel", bindingName);
    if (!channelId) {
      return;
    }

    const channel = await this.client.channels.fetch(channelId);
    if (!channel?.isSendable()) {
      return;
    }

    await channel.send({
      embeds: [
        new EmbedBuilder()
          .setTitle(title)
          .setDescription(description)
          .setColor(color)
      ]
    });
  }
}
