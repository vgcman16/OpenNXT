import type { GuildMember } from "discord.js";
import { STAFF_ROLE_NAMES } from "./blueprint";
import type { SqliteStore } from "../persistence/SqliteStore";

export function hasStaffRole(member: GuildMember, store: SqliteStore, configuredRoleIds: string[]) {
  if (configuredRoleIds.some((roleId) => member.roles.cache.has(roleId))) {
    return true;
  }

  return STAFF_ROLE_NAMES.some((roleName) => {
    const roleId = store.getBinding("role", roleName);
    return roleId ? member.roles.cache.has(roleId) : false;
  });
}

export function canRunHostCommand(
  member: GuildMember,
  store: SqliteStore,
  configuredRoleIds: string[]
) {
  return store.isUserAllowlisted(member.id) && hasStaffRole(member, store, configuredRoleIds);
}
