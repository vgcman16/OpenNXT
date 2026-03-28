import { describe, expect, it } from "vitest";
import { canRunHostCommand, hasStaffRole } from "../src/discord/permissions";

function createStoreStub() {
  return {
    isUserAllowlisted(userId: string) {
      return userId === "allowed-user";
    },
    getBinding(kind: string, name: string) {
      if (kind !== "role") {
        return null;
      }
      const bindings: Record<string, string> = {
        "Lead Admin": "role-admin",
        Moderator: "role-moderator"
      };
      return bindings[name] ?? null;
    }
  };
}

function createMember(id: string, roleIds: string[]) {
  return {
    id,
    roles: {
      cache: {
        has(roleId: string) {
          return roleIds.includes(roleId);
        }
      }
    }
  };
}

describe("permission gates", () => {
  it("accepts configured staff roles", () => {
    const member = createMember("allowed-user", ["configured-staff"]);
    expect(hasStaffRole(member as any, createStoreStub() as any, ["configured-staff"])).toBe(true);
  });

  it("requires both allowlist and staff role for host commands", () => {
    const store = createStoreStub();
    const member = createMember("allowed-user", ["role-admin"]);
    expect(canRunHostCommand(member as any, store as any, [])).toBe(true);

    const outsider = createMember("outsider", ["role-admin"]);
    expect(canRunHostCommand(outsider as any, store as any, [])).toBe(false);
  });
});
