export type BindingKind = "role" | "channel" | "category";

export type JobStatus = "running" | "succeeded" | "failed" | "rejected";

export interface AuditFinding {
  label: string;
  ok: boolean;
  detail: string;
}

export interface AuditReport {
  findings: AuditFinding[];
  summary: string;
}

export interface JobRecord {
  id: string;
  kind: string;
  status: JobStatus;
  summary: string;
  startedAt: string;
  finishedAt: string | null;
}

export interface TicketRecord {
  id: number;
  requesterId: string;
  channelId: string;
  status: "open" | "closed";
  subject: string;
  createdAt: string;
  closedAt: string | null;
  closedBy: string | null;
}
