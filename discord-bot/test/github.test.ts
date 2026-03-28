import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import crypto from "node:crypto";
import { afterEach, describe, expect, it } from "vitest";
import { SqliteStore } from "../src/persistence/SqliteStore";
import { GitHubWebhookService } from "../src/github/GitHubWebhookService";

function makeSignature(secret: string, payload: Buffer) {
  return `sha256=${crypto.createHmac("sha256", secret).update(payload).digest("hex")}`;
}

describe("GitHubWebhookService", () => {
  const tempRoots: string[] = [];

  afterEach(() => {
    for (const root of tempRoots) {
      fs.rmSync(root, { recursive: true, force: true });
    }
    tempRoots.length = 0;
  });

  it("validates signatures, dedupes deliveries, and publishes supported events", async () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "opennxt-github-"));
    tempRoots.push(root);
    const store = new SqliteStore(path.join(root, "bot.sqlite"));
    const sent: Array<{ bindingName: string; title: string; description: string }> = [];

    const service = new GitHubWebhookService(
      {
        secret: "secret",
        repoOwner: "vgcman16",
        repoName: "OpenNXT"
      },
      store,
      {
        async send(bindingName: string, title: string, description: string) {
          sent.push({ bindingName, title, description });
        }
      } as any,
      { info() {}, error() {} } as any
    );

    const payload = Buffer.from(JSON.stringify({
      ref: "refs/heads/main",
      repository: {
        name: "OpenNXT",
        owner: { login: "vgcman16" }
      },
      pusher: { name: "vgcman16" },
      commits: [
        { id: "abcdef123456", message: "First commit" }
      ]
    }));

    const headers = {
      "x-hub-signature-256": makeSignature("secret", payload),
      "x-github-delivery": "delivery-1",
      "x-github-event": "push"
    };

    const first = await service.handle(payload, headers);
    const second = await service.handle(payload, headers);

    expect(first.status).toBe(202);
    expect(second.body).toBe("duplicate delivery");
    expect(sent).toHaveLength(1);
    expect(sent[0].bindingName).toBe("github-feed");
    expect(store.listRecentGithubDeliveries(5)).toHaveLength(1);

    store.close();
  });
});
