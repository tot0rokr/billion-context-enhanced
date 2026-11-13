import { appendFileSync } from "node:fs";
import { randomUUID } from "node:crypto";
import { finalizeSseLineEndings, normalizeSseLineEndings } from "./sse-util.js";

type Ticket = { id: string; start: number; path: string; bytes: number };
type JsonRecord = Record<string, unknown>;

const logPath = process.env.AUDIT_USAGE_LOG;
const MAX_BUFFER = 8 * 1024 * 1024;

function record(value: JsonRecord): void {
    if (logPath) appendFileSync(logPath, JSON.stringify({ at: Date.now(), ...value }) + "\n", { mode: 0o600 });
}

export function startAuditRequest(url: string, method?: string, body?: unknown): Ticket | undefined {
    if (!logPath || method !== "POST") return undefined;
    const path = new URL(url).pathname;
    if (!/responses(?:\/compact)?$|messages$|generateContent|streamGenerateContent/.test(path)) return undefined;
    const ticket = { id: randomUUID(), start: Date.now(), path, bytes: typeof body === "string" ? Buffer.byteLength(body) : 0 };
    record({ kind: "request", ...ticket });
    return ticket;
}

export function failAuditRequest(ticket: Ticket | undefined, error: unknown): void {
    if (ticket) record({ kind: "request_error", id: ticket.id, error: error instanceof Error ? error.name : typeof error });
}

export function auditResponseBody(response: Response, ticket: Ticket | undefined): Response {
    if (!ticket || !response.body) return response;
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let isSse = response.headers.get("content-type")?.includes("text/event-stream") === true;
    let pending = "";
    let usageSeen = false;
    let capped = false;
    const eventTypes = new Set<string>();
    const seen = new Set<string>();
    const inspect = (raw: string): void => {
        if (raw === "[DONE]") return;
        let parsed: JsonRecord;
        try { parsed = JSON.parse(raw) as JsonRecord; } catch { return; }
        if (typeof parsed.type === "string") eventTypes.add(parsed.type);
        const item = parsed.item as JsonRecord | undefined;
        if (parsed.type === "response.output_item.done" && item && typeof item.type === "string" && item.type.endsWith("_call")) {
            record({ kind: "tool_call", id: ticket.id, item_id: item.id, tool_type: item.type, name: item.name });
        }
        const payload = parsed.response && typeof parsed.response === "object" ? parsed.response as JsonRecord : parsed;
        const usage = payload.usage;
        if (!usage || typeof usage !== "object") return;
        const signature = JSON.stringify([payload.id, usage]);
        if (seen.has(signature)) return;
        seen.add(signature);
        usageSeen = true;
        record({ kind: "usage", id: ticket.id, response_id: payload.id, model: payload.model, status: payload.status, usage, elapsed_ms: Date.now() - ticket.start });
    };
    const inspectChunk = (chunk: Uint8Array): void => {
        if (capped) return;
        pending += decoder.decode(chunk, { stream: true });
        if (!isSse && /^(event:|data:)/.test(pending.trimStart())) isSse = true;
        if (pending.length > MAX_BUFFER) {
            capped = true;
            pending = "";
            record({ kind: "parser_limit", id: ticket.id });
            return;
        }
        if (isSse) {
            pending = normalizeSseLineEndings(pending);
            let boundary: number;
            while ((boundary = pending.indexOf("\n\n")) >= 0) {
                const frame = pending.slice(0, boundary);
                pending = pending.slice(boundary + 2);
                const data = frame.split("\n").filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trimStart()).join("\n");
                if (data) inspect(data);
            }
        }
    };
    const body = new ReadableStream<Uint8Array>({
        async pull(controller) {
            try {
                const next = await reader.read();
                if (next.done) {
                    if (!capped) {
                        pending += decoder.decode();
                        if (!isSse) inspect(pending);
                        else {
                            const data = finalizeSseLineEndings(pending).split("\n").filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trimStart()).join("\n");
                            if (data) inspect(data);
                        }
                    }
                    record({ kind: "finished", id: ticket.id, status: response.status, usage_seen: usageSeen, content_type: response.headers.get("content-type"), event_types: [...eventTypes], elapsed_ms: Date.now() - ticket.start });
                    controller.close();
                    return;
                }
                inspectChunk(next.value);
                controller.enqueue(next.value);
            } catch (error) {
                failAuditRequest(ticket, error);
                controller.error(error);
            }
        },
        async cancel(reason) {
            record({ kind: "cancelled", id: ticket.id, usage_seen: usageSeen });
            await reader.cancel(reason);
        },
    });
    return new Response(body, { status: response.status, statusText: response.statusText, headers: response.headers });
}
