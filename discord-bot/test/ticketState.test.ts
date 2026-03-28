import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { SqliteStore } from "../src/persistence/SqliteStore";

describe("SqliteStore ticket state", () => {
  const tempRoots: string[] = [];

  afterEach(() => {
    for (const root of tempRoots) {
      fs.rmSync(root, { recursive: true, force: true });
    }
    tempRoots.length = 0;
  });

  it("tracks open and closed tickets", () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "opennxt-ticket-"));
    tempRoots.push(root);
    const store = new SqliteStore(path.join(root, "bot.sqlite"));

    const ticketId = store.createTicket("user-1", "channel-1", "need help");
    expect(ticketId).toBeGreaterThan(0);
    expect(store.getOpenTicketForRequester("user-1")?.channelId).toBe("channel-1");

    store.closeTicket("channel-1", "staff-1");
    expect(store.getTicketByChannel("channel-1")?.status).toBe("closed");

    store.close();
  });
});
