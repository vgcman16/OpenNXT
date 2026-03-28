import type { Logger } from "pino";
import type { SqliteStore } from "../persistence/SqliteStore";
import { ChannelAnnouncer } from "../discord/ChannelAnnouncer";
import { verifyGithubSignature } from "./signature";

interface GitHubWebhookConfig {
  secret: string;
  repoOwner: string;
  repoName: string;
}

function isTargetRepo(payload: any, repoOwner: string, repoName: string) {
  return payload?.repository?.owner?.login === repoOwner && payload?.repository?.name === repoName;
}

export class GitHubWebhookService {
  constructor(
    private readonly config: GitHubWebhookConfig,
    private readonly store: SqliteStore,
    private readonly announcer: ChannelAnnouncer,
    private readonly logger: Logger
  ) {}

  async handle(rawBody: Buffer, headers: Record<string, string | string[] | undefined>) {
    if (!verifyGithubSignature(this.config.secret, rawBody, headers["x-hub-signature-256"])) {
      return { status: 401, body: "invalid signature" };
    }

    const deliveryId = String(headers["x-github-delivery"] ?? "");
    const eventName = String(headers["x-github-event"] ?? "");
    if (!deliveryId || !eventName) {
      return { status: 400, body: "missing GitHub headers" };
    }

    if (this.store.hasGithubDelivery(deliveryId)) {
      return { status: 202, body: "duplicate delivery" };
    }

    const payload = JSON.parse(rawBody.toString("utf8"));
    if (!isTargetRepo(payload, this.config.repoOwner, this.config.repoName)) {
      return { status: 202, body: "ignored repo" };
    }

    this.store.recordGithubDelivery(deliveryId, eventName);
    await this.publish(eventName, payload);
    return { status: 202, body: "accepted" };
  }

  private async publish(eventName: string, payload: any) {
    switch (eventName) {
      case "push":
        await this.publishPush(payload);
        return;
      case "issues":
        await this.publishIssue(payload);
        return;
      case "release":
        await this.publishRelease(payload);
        return;
      case "workflow_run":
        await this.publishWorkflowRun(payload);
        return;
      default:
        this.logger.info({ eventName }, "Ignored GitHub event");
    }
  }

  private async publishPush(payload: any) {
    if (payload.ref !== "refs/heads/main") {
      return;
    }

    const commits = Array.isArray(payload.commits) ? payload.commits : [];
    const description = commits.length === 0
      ? `${payload.pusher?.name ?? "unknown"} pushed to main.`
      : commits
          .slice(0, 5)
          .map((commit: any) => `- \`${String(commit.id).slice(0, 7)}\` ${commit.message.split("\n")[0]}`)
          .join("\n");

    await this.announcer.send(
      "github-feed",
      "GitHub Push",
      description || "Push received on `main`.",
      "Blurple"
    );
  }

  private async publishIssue(payload: any) {
    const action = payload.action;
    if (!["opened", "closed", "labeled", "reopened"].includes(action)) {
      return;
    }

    const issue = payload.issue;
    const labelSuffix = action === "labeled" && payload.label ? ` with label \`${payload.label.name}\`` : "";
    await this.announcer.send(
      "github-feed",
      `Issue ${action}`,
      `#${issue.number} ${issue.title}${labelSuffix}\n${issue.html_url}`,
      "Orange"
    );
  }

  private async publishRelease(payload: any) {
    if (payload.action !== "published") {
      return;
    }

    const release = payload.release;
    const description = `${release.name || release.tag_name}\n${release.html_url}`;
    await this.announcer.send("github-feed", "Release Published", description, "Green");
    await this.announcer.send("announcements", "OpenNXT Release", description, "Green");
  }

  private async publishWorkflowRun(payload: any) {
    const run = payload.workflow_run;
    if (!run || run.conclusion !== "success" || run.event !== "release") {
      return;
    }

    await this.announcer.send(
      "dev-updates",
      "Release Workflow Succeeded",
      `${run.name} succeeded.\n${run.html_url}`,
      "Green"
    );
  }
}
