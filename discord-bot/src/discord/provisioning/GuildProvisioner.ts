import { CATEGORY_BLUEPRINT, ROLE_BLUEPRINT, SEEDED_MESSAGES } from "../blueprint";
import type { SqliteStore } from "../../persistence/SqliteStore";
import type { PermissionRule, ProvisioningAdapter } from "./types";

function publicReadOnlyRules(): PermissionRule[] {
  return [
    { kind: "everyone", allow: ["ViewChannel", "ReadMessageHistory"], deny: ["SendMessages"] }
  ];
}

function verifiedDiscussionRules(): PermissionRule[] {
  return [
    { kind: "everyone", allow: [], deny: ["ViewChannel"] },
    { kind: "role", roleName: "Verified", allow: ["ViewChannel", "ReadMessageHistory", "SendMessages"], deny: [] },
    { kind: "role", roleName: "Community", allow: ["ViewChannel", "ReadMessageHistory", "SendMessages"], deny: [] },
    { kind: "role", roleName: "Tester", allow: ["ViewChannel", "ReadMessageHistory", "SendMessages"], deny: [] },
    { kind: "role", roleName: "Owner", allow: ["ViewChannel", "ReadMessageHistory", "SendMessages"], deny: [] },
    { kind: "role", roleName: "Lead Admin", allow: ["ViewChannel", "ReadMessageHistory", "SendMessages"], deny: [] },
    { kind: "role", roleName: "Developer", allow: ["ViewChannel", "ReadMessageHistory", "SendMessages"], deny: [] },
    { kind: "role", roleName: "Moderator", allow: ["ViewChannel", "ReadMessageHistory", "SendMessages"], deny: [] }
  ];
}

function staffOnlyRules(): PermissionRule[] {
  return [
    { kind: "everyone", allow: [], deny: ["ViewChannel"] },
    { kind: "role", roleName: "Owner", allow: ["ViewChannel", "ReadMessageHistory", "SendMessages"], deny: [] },
    { kind: "role", roleName: "Lead Admin", allow: ["ViewChannel", "ReadMessageHistory", "SendMessages"], deny: [] },
    { kind: "role", roleName: "Developer", allow: ["ViewChannel", "ReadMessageHistory", "SendMessages"], deny: [] },
    { kind: "role", roleName: "Moderator", allow: ["ViewChannel", "ReadMessageHistory", "SendMessages"], deny: [] }
  ];
}

function channelRules(channelName: string, categoryName: string): PermissionRule[] {
  if (channelName === "verify") {
    return [
      { kind: "everyone", allow: ["ViewChannel", "ReadMessageHistory", "SendMessages"], deny: [] }
    ];
  }

  if (categoryName === "Start Here") {
    return publicReadOnlyRules();
  }

  if (categoryName === "Staff") {
    return staffOnlyRules();
  }

  return verifiedDiscussionRules();
}

function categoryRules(categoryName: string): PermissionRule[] {
  if (categoryName === "Staff") {
    return staffOnlyRules();
  }

  if (categoryName === "Start Here") {
    return publicReadOnlyRules();
  }

  return verifiedDiscussionRules();
}

export class GuildProvisioner {
  constructor(
    private readonly adapter: ProvisioningAdapter,
    private readonly store: SqliteStore
  ) {}

  async scaffold() {
    for (const roleName of ROLE_BLUEPRINT) {
      const role = await this.adapter.ensureRole(roleName);
      this.store.upsertBinding("role", role.name, role.id);
    }

    for (const categorySpec of CATEGORY_BLUEPRINT) {
      const category = await this.adapter.ensureCategory(
        categorySpec.name,
        categoryRules(categorySpec.name)
      );
      this.store.upsertBinding("category", category.name, category.id);

      for (const channelName of categorySpec.channels) {
        const channel = await this.adapter.ensureTextChannel({
          name: channelName,
          parentId: category.id,
          topic: `OpenNXT ${channelName.replace(/-/g, " ")}`,
          overwrites: channelRules(channelName, categorySpec.name)
        });
        this.store.upsertBinding("channel", channel.name, channel.id);

        const seededMessages = SEEDED_MESSAGES[channel.name];
        if (seededMessages?.length) {
          await this.adapter.sendSeedMessages(channel.id, seededMessages);
        }
      }
    }
  }
}
