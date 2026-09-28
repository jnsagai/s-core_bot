import { apiFetch, apiFetchJson } from "./client";

export interface CapabilityState {
  available: boolean;
  reasons: string[];
}

export interface Limits {
  questionCharacters: number;
  historyCharacters: number;
  activeGenerations: number;
  queuedGenerations: number;
  requestDeadlineSeconds: number;
}

export interface Capabilities {
  app: { name: string; version: string };
  runsLocally: boolean;
  modes: Record<string, CapabilityState>;
  limits: Limits;
  models: { generation: string; embedding: string };
  responseLanguages: string[];
}

interface CapabilitiesResponseWire {
  app: { name: string; version: string };
  runs_locally: boolean;
  modes: Record<string, { available: boolean; reasons: string[] }>;
  limits: {
    question_characters: number;
    history_characters: number;
    active_generations: number;
    queued_generations: number;
    request_deadline_seconds: number;
  };
  models: { generation: string; embedding: string };
  response_languages: string[];
}

export async function getCapabilities(): Promise<Capabilities> {
  const wire = await apiFetchJson<CapabilitiesResponseWire>("/api/v1/capabilities");
  return {
    app: wire.app,
    runsLocally: wire.runs_locally,
    modes: wire.modes,
    limits: {
      questionCharacters: wire.limits.question_characters,
      historyCharacters: wire.limits.history_characters,
      activeGenerations: wire.limits.active_generations,
      queuedGenerations: wire.limits.queued_generations,
      requestDeadlineSeconds: wire.limits.request_deadline_seconds,
    },
    models: wire.models,
    responseLanguages: wire.response_languages,
  };
}

interface ReadinessResponseWire {
  ready: boolean;
  capabilities: Record<string, { available: boolean; reasons: string[] }>;
}

export async function getHealthReady(): Promise<ReadinessResponseWire> {
  const response = await apiFetch("/health/ready", { okStatuses: [503] });
  return (await response.json()) as ReadinessResponseWire;
}
