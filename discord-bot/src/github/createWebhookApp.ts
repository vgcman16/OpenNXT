import express from "express";
import type { GitHubWebhookService } from "./GitHubWebhookService";

export function createWebhookApp(service: GitHubWebhookService) {
  const app = express();
  app.use(express.raw({ type: "*/*" }));

  app.post("/github/webhook", async (request, response) => {
    const result = await service.handle(request.body, request.headers);
    response.status(result.status).send(result.body);
  });

  return app;
}
