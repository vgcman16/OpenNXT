import { randomUUID } from "node:crypto";
import type { JobRecord, JobStatus } from "../types";
import type { SqliteStore } from "../persistence/SqliteStore";

export interface JobProgressReporter {
  start(job: JobRecord): Promise<void>;
  stage(name: string, detail: string): Promise<void>;
  finish(status: Exclude<JobStatus, "running">, detail: string): Promise<void>;
}

export class JobCoordinator {
  private currentJobId: string | null = null;

  constructor(private readonly store: SqliteStore) {}

  isBusy() {
    return this.currentJobId !== null;
  }

  async runExclusive<T>(
    kind: string,
    reporter: JobProgressReporter,
    work: (jobId: string) => Promise<T>
  ) {
    if (this.currentJobId) {
      throw new Error(`Another job is already running: ${this.currentJobId}`);
    }

    const jobId = randomUUID();
    this.currentJobId = jobId;

    const job: JobRecord = {
      id: jobId,
      kind,
      status: "running",
      summary: "Starting",
      startedAt: new Date().toISOString(),
      finishedAt: null
    };
    this.store.createJob(job);
    await reporter.start(job);

    try {
      const result = await work(jobId);
      this.store.updateJobStatus(jobId, "succeeded", `${kind} completed`, new Date().toISOString());
      await reporter.finish("succeeded", `${kind} completed successfully.`);
      return result;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      this.store.updateJobStatus(jobId, "failed", message, new Date().toISOString());
      await reporter.finish("failed", message);
      throw error;
    } finally {
      this.currentJobId = null;
    }
  }
}
