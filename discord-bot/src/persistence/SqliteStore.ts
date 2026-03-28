import Database from "better-sqlite3";
import { ensureDirectory } from "../util/fs";
import type { BindingKind, JobRecord, JobStatus, TicketRecord } from "../types";

export class SqliteStore {
  private readonly db: Database.Database;

  constructor(dbPath: string) {
    ensureDirectory(require("node:path").dirname(dbPath));
    this.db = new Database(dbPath);
    this.db.pragma("journal_mode = WAL");
    this.migrate();
  }

  close() {
    this.db.close();
  }

  private migrate() {
    this.db.exec(`
      create table if not exists bindings (
        kind text not null,
        name text not null,
        discord_id text not null,
        primary key (kind, name)
      );

      create table if not exists settings (
        key text primary key,
        value text not null
      );

      create table if not exists allowlist (
        user_id text primary key,
        source text not null,
        created_at text not null
      );

      create table if not exists jobs (
        id text primary key,
        kind text not null,
        status text not null,
        summary text not null,
        started_at text not null,
        finished_at text
      );

      create table if not exists github_deliveries (
        delivery_id text primary key,
        event_name text not null,
        received_at text not null
      );

      create table if not exists tickets (
        id integer primary key autoincrement,
        requester_id text not null,
        channel_id text not null unique,
        status text not null,
        subject text not null,
        created_at text not null,
        closed_at text,
        closed_by text
      );
    `);
  }

  upsertBinding(kind: BindingKind, name: string, discordId: string) {
    this.db
      .prepare(`
        insert into bindings(kind, name, discord_id)
        values (@kind, @name, @discordId)
        on conflict(kind, name) do update set discord_id = excluded.discord_id
      `)
      .run({ kind, name, discordId });
  }

  getBinding(kind: BindingKind, name: string) {
    const row = this.db
      .prepare(`select discord_id from bindings where kind = ? and name = ?`)
      .get(kind, name) as { discord_id: string } | undefined;
    return row?.discord_id ?? null;
  }

  listBindings(kind: BindingKind) {
    return this.db
      .prepare(`select name, discord_id from bindings where kind = ? order by name asc`)
      .all(kind) as Array<{ name: string; discord_id: string }>;
  }

  setSetting(key: string, value: string) {
    this.db
      .prepare(`
        insert into settings(key, value)
        values (?, ?)
        on conflict(key) do update set value = excluded.value
      `)
      .run(key, value);
  }

  getSetting(key: string) {
    const row = this.db
      .prepare(`select value from settings where key = ?`)
      .get(key) as { value: string } | undefined;
    return row?.value ?? null;
  }

  ensureAllowlist(userIds: string[], source = "env") {
    const statement = this.db.prepare(`
      insert into allowlist(user_id, source, created_at)
      values (@userId, @source, @createdAt)
      on conflict(user_id) do update set source = excluded.source
    `);
    const createdAt = new Date().toISOString();
    const transaction = this.db.transaction((ids: string[]) => {
      ids.forEach((userId) => statement.run({ userId, source, createdAt }));
    });
    transaction(userIds);
  }

  isUserAllowlisted(userId: string) {
    const row = this.db
      .prepare(`select user_id from allowlist where user_id = ?`)
      .get(userId) as { user_id: string } | undefined;
    return Boolean(row);
  }

  listAllowlist() {
    return this.db
      .prepare(`select user_id, source from allowlist order by user_id asc`)
      .all() as Array<{ user_id: string; source: string }>;
  }

  createJob(job: JobRecord) {
    this.db
      .prepare(`
        insert into jobs(id, kind, status, summary, started_at, finished_at)
        values (@id, @kind, @status, @summary, @startedAt, @finishedAt)
      `)
      .run({
        id: job.id,
        kind: job.kind,
        status: job.status,
        summary: job.summary,
        startedAt: job.startedAt,
        finishedAt: job.finishedAt
      });
  }

  updateJobStatus(id: string, status: JobStatus, summary: string, finishedAt: string | null = null) {
    this.db
      .prepare(`
        update jobs
        set status = @status,
            summary = @summary,
            finished_at = @finishedAt
        where id = @id
      `)
      .run({ id, status, summary, finishedAt });
  }

  getLatestJobs(limit = 10) {
    return this.db
      .prepare(`
        select id, kind, status, summary, started_at as startedAt, finished_at as finishedAt
        from jobs
        order by started_at desc
        limit ?
      `)
      .all(limit) as JobRecord[];
  }

  hasGithubDelivery(deliveryId: string) {
    const row = this.db
      .prepare(`select delivery_id from github_deliveries where delivery_id = ?`)
      .get(deliveryId) as { delivery_id: string } | undefined;
    return Boolean(row);
  }

  recordGithubDelivery(deliveryId: string, eventName: string) {
    this.db
      .prepare(`
        insert or ignore into github_deliveries(delivery_id, event_name, received_at)
        values (?, ?, ?)
      `)
      .run(deliveryId, eventName, new Date().toISOString());
  }

  createTicket(requesterId: string, channelId: string, subject: string) {
    const result = this.db
      .prepare(`
        insert into tickets(requester_id, channel_id, status, subject, created_at)
        values (?, ?, 'open', ?, ?)
      `)
      .run(requesterId, channelId, subject, new Date().toISOString());
    return Number(result.lastInsertRowid);
  }

  getOpenTicketForRequester(requesterId: string) {
    return (this.db
      .prepare(`
        select id, requester_id as requesterId, channel_id as channelId, status, subject, created_at as createdAt, closed_at as closedAt, closed_by as closedBy
        from tickets
        where requester_id = ? and status = 'open'
        limit 1
      `)
      .get(requesterId) as TicketRecord | undefined) ?? null;
  }

  getTicketByChannel(channelId: string) {
    return (this.db
      .prepare(`
        select id, requester_id as requesterId, channel_id as channelId, status, subject, created_at as createdAt, closed_at as closedAt, closed_by as closedBy
        from tickets
        where channel_id = ?
        limit 1
      `)
      .get(channelId) as TicketRecord | undefined) ?? null;
  }

  closeTicket(channelId: string, closedBy: string) {
    this.db
      .prepare(`
        update tickets
        set status = 'closed',
            closed_at = ?,
            closed_by = ?
        where channel_id = ? and status = 'open'
      `)
      .run(new Date().toISOString(), closedBy, channelId);
  }

  listRecentGithubDeliveries(limit = 10) {
    return this.db
      .prepare(`
        select delivery_id as deliveryId, event_name as eventName, received_at as receivedAt
        from github_deliveries
        order by received_at desc
        limit ?
      `)
      .all(limit) as Array<{ deliveryId: string; eventName: string; receivedAt: string }>;
  }
}
