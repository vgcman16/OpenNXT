import { describe, expect, it } from "vitest";
import { GuildProvisioner } from "../src/discord/provisioning/GuildProvisioner";
import { SqliteStore } from "../src/persistence/SqliteStore";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

class FakeProvisioningAdapter {
  roles = new Map<string, { id: string; name: string }>();
  categories = new Map<string, { id: string; name: string; parentId: null; kind: "category" }>();
  channels = new Map<string, { id: string; name: string; parentId: string | null; kind: "text" }>();
  messages = new Map<string, string[]>();

  async ensureRole(name: string) {
    const existing = this.roles.get(name);
    if (existing) {
      return existing;
    }
    const created = { id: `role-${this.roles.size + 1}`, name };
    this.roles.set(name, created);
    return created;
  }

  async ensureCategory(name: string) {
    const existing = this.categories.get(name);
    if (existing) {
      return existing;
    }
    const created = { id: `category-${this.categories.size + 1}`, name, parentId: null, kind: "category" as const };
    this.categories.set(name, created);
    return created;
  }

  async ensureTextChannel(input: { name: string; parentId: string }) {
    const existing = this.channels.get(input.name);
    if (existing) {
      return existing;
    }
    const created = {
      id: `channel-${this.channels.size + 1}`,
      name: input.name,
      parentId: input.parentId,
      kind: "text" as const
    };
    this.channels.set(input.name, created);
    return created;
  }

  async sendSeedMessages(channelId: string, messages: string[]) {
    if (this.messages.has(channelId)) {
      return;
    }
    this.messages.set(channelId, [...messages]);
  }
}

describe("GuildProvisioner", () => {
  it("creates the expected structure and stays idempotent on rerun", async () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "opennxt-provisioner-"));
    const store = new SqliteStore(path.join(root, "bot.sqlite"));
    const adapter = new FakeProvisioningAdapter();
    const provisioner = new GuildProvisioner(adapter as any, store);

    await provisioner.scaffold();
    await provisioner.scaffold();

    expect(adapter.roles.size).toBe(7);
    expect(adapter.categories.size).toBe(5);
    expect(adapter.channels.size).toBe(21);
    expect(store.getBinding("channel", "verify")).toBeTruthy();
    expect(store.getBinding("category", "Staff")).toBeTruthy();

    store.close();
    fs.rmSync(root, { recursive: true, force: true });
  });
});
