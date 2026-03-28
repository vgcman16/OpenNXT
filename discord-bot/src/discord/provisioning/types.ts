export interface ProvisionedRole {
  id: string;
  name: string;
}

export interface ProvisionedChannel {
  id: string;
  name: string;
  parentId: string | null;
  kind: "category" | "text";
}

export interface PermissionRule {
  kind: "everyone" | "role";
  roleName?: string;
  allow: string[];
  deny: string[];
}

export interface ProvisioningAdapter {
  ensureRole(name: string): Promise<ProvisionedRole>;
  ensureCategory(name: string, overwrites: PermissionRule[]): Promise<ProvisionedChannel>;
  ensureTextChannel(input: {
    name: string;
    parentId: string;
    topic?: string;
    overwrites: PermissionRule[];
  }): Promise<ProvisionedChannel>;
  sendSeedMessages(channelId: string, messages: string[]): Promise<void>;
}
