import assert from "node:assert/strict";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

const directory = mkdtempSync(join(tmpdir(), "bili-meter-check-"));
process.env.AUDIT_USAGE_LOG = join(directory, "usage.jsonl");
const { startAuditRequest, auditResponseBody } = await import("../src/audit-usage.ts");

test("stream bytes survive fragmented SSE and terminal usage is counted once", async () => {
    const payload = 'event: response.completed\ndata: {"type":"response.completed","response":{"id":"r1","usage":{"input_tokens":123,"output_tokens":17,"input_tokens_details":{"cached_tokens":80}}}}\n\ndata: [DONE]\n\n';
    const bytes = new TextEncoder().encode(payload);
    const stream = new ReadableStream<Uint8Array>({ start(controller) {
        for (let offset = 0; offset < bytes.length; offset += 7) controller.enqueue(bytes.slice(offset, offset + 7));
        controller.close();
    } });
    const ticket = startAuditRequest("https://example.invalid/v1/responses", "POST", "{}");
    const response = auditResponseBody(new Response(stream, { headers: { "content-type": "text/event-stream" } }), ticket);
    assert.equal(await response.text(), payload);
    const rows = readFileSync(process.env.AUDIT_USAGE_LOG!, "utf8").trim().split("\n").map((line) => JSON.parse(line));
    const usage = rows.filter((row) => row.kind === "usage");
    assert.equal(usage.length, 1);
    assert.equal(usage[0].usage.input_tokens, 123);
    assert.equal(usage[0].usage.input_tokens_details.cached_tokens, 80);
    assert.equal(usage[0].usage.output_tokens, 17);
    assert.equal(rows.at(-1).usage_seen, true);
});

test("nonstream usage is preserved and an error without usage is not counted as zero", async () => {
    const payload = JSON.stringify({ id: "r2", usage: { input_tokens: 321, output_tokens: 19 } });
    const ticket = startAuditRequest("https://example.invalid/v1/responses", "POST", "{}");
    assert.equal(await auditResponseBody(new Response(payload), ticket).text(), payload);
    const errorTicket = startAuditRequest("https://example.invalid/v1/responses", "POST", "{}");
    assert.equal(await auditResponseBody(new Response('{"error":"test"}', { status: 429 }), errorTicket).text(), '{"error":"test"}');
    const rows = readFileSync(process.env.AUDIT_USAGE_LOG!, "utf8").trim().split("\n").map((line) => JSON.parse(line));
    assert.equal(rows.filter((row) => row.kind === "usage").length, 2);
    assert.equal(rows.at(-1).usage_seen, false);
    assert.equal(rows.at(-1).status, 429);
});

test("CR-delimited multiline SSE is measured without changing its bytes", async () => {
    const payload = 'event: response.completed\rdata: {"type":"response.completed",\rdata: "response":{"id":"r3","usage":{"input_tokens":456,"output_tokens":23}}}\r\r';
    const bytes = new TextEncoder().encode(payload);
    const stream = new ReadableStream<Uint8Array>({ start(controller) {
        for (let offset = 0; offset < bytes.length; offset += 5) controller.enqueue(bytes.slice(offset, offset + 5));
        controller.close();
    } });
    const ticket = startAuditRequest("https://example.invalid/v1/responses", "POST", "{}");
    assert.equal(await auditResponseBody(new Response(stream), ticket).text(), payload);
    const entries = readFileSync(process.env.AUDIT_USAGE_LOG!, "utf8").trim().split("\n").map((line) => JSON.parse(line));
    assert.equal(entries.filter((row) => row.kind === "usage" && row.response_id === "r3").length, 1);
});
