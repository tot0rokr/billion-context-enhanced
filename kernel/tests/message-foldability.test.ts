import assert from "node:assert/strict";
import { test } from "node:test";
import { defaultConfig } from "../src/config.js";
import { assignRefs } from "../src/refs.js";
import { buildStatusReport } from "../src/report.js";
import { createInitialState } from "../src/state.js";
import { defaultCountTokens } from "../src/tokenize.js";
import type { CoreMessage } from "../src/types.js";

function fixture() {
  const messages: CoreMessage[] = [
    {
      id: "old",
      role: "assistant",
      contentType: "text",
      text: "old work ".repeat(800),
    },
    {
      id: "request",
      role: "user",
      contentType: "text",
      text: "current evidence ".repeat(11000),
    },
    ...Array.from({ length: 5 }, (_, index): CoreMessage => ({
      id: `reply-${index}`,
      role: "assistant",
      contentType: "text",
      text: "working notes ".repeat(500),
    })),
  ];
  const state = createInitialState();
  state.messageRefs = assignRefs(messages, {
    existing: state.messageRefs,
    nextIndex: 1,
  }).map;
  const config = defaultConfig(1_000_000, {
    preserveRecentTokens: 0,
    preserveRecentMessages: 3,
  });
  return { messages, state, config };
}

test("message view identifies the latest user as protected after it leaves the recent window", () => {
  const { messages, state, config } = fixture();
  const report = buildStatusReport(state, messages, defaultCountTokens, {
    scope: "uncompressed",
    view: "messages",
    config,
    originalMessages: messages,
  });
  const current = report
    .split("\n")
    .find((line) => line.includes(state.messageRefs.byRaw.request!));
  const older = report
    .split("\n")
    .find((line) => line.includes(state.messageRefs.byRaw.old!));
  assert.match(current!, /not foldable: protected zone only/);
  assert.doesNotMatch(older!, /not foldable/);
});

test("a new user request makes the previous request eligible again", () => {
  const { messages, state, config } = fixture();
  messages.push({
    id: "new-request",
    role: "user",
    contentType: "text",
    text: "Continue the task.",
  });
  state.messageRefs = assignRefs(messages, {
    existing: state.messageRefs,
    nextIndex: 1,
  }).map;
  const report = buildStatusReport(state, messages, defaultCountTokens, {
    scope: "uncompressed",
    view: "messages",
    config,
    originalMessages: messages,
  });
  const previous = report
    .split("\n")
    .find((line) => line.includes(state.messageRefs.byRaw.request!));
  const current = report
    .split("\n")
    .find((line) => line.includes(state.messageRefs.byRaw["new-request"]!));
  assert.doesNotMatch(previous!, /not foldable/);
  assert.match(current!, /not foldable: protected zone only/);
});

test("message eligibility uses the apply history when the displayed view is shorter", () => {
  const { messages, state, config } = fixture();
  const report = buildStatusReport(
    state,
    messages.slice(0, 2),
    defaultCountTokens,
    {
      scope: "uncompressed",
      view: "messages",
      config,
      originalMessages: messages,
    },
  );
  const older = report
    .split("\n")
    .find((line) => line.includes(state.messageRefs.byRaw.old!));
  const current = report
    .split("\n")
    .find((line) => line.includes(state.messageRefs.byRaw.request!));
  assert.doesNotMatch(older!, /not foldable/);
  assert.match(current!, /not foldable: protected zone only/);
});

test("legacy message view without eligibility inputs stays unchanged", () => {
  const { messages, state } = fixture();
  const report = buildStatusReport(state, messages, defaultCountTokens, {
    scope: "uncompressed",
    view: "messages",
  });
  assert.doesNotMatch(report, /not foldable/);
  assert.equal(
    report.split("\n").filter((line) => /^  m\d+ /.test(line)).length,
    messages.length,
  );
});

test("message view flags an unresolvable displayed ref", () => {
  const { messages, state, config } = fixture();
  state.messageRefs.byRaw.request = "BLOCKED";
  const report = buildStatusReport(state, messages, defaultCountTokens, {
    scope: "uncompressed",
    view: "messages",
    config,
    originalMessages: messages,
  });
  assert.match(
    report.split("\n").find((line) => line.includes("BLOCKED"))!,
    /not foldable: refs unresolvable/,
  );
});

test("a single tool-call row can widen to its complete unprotected exchange", () => {
  const { messages, state, config } = fixture();
  messages.unshift(
    {
      id: "call",
      role: "assistant",
      contentType: "tool-call",
      toolName: "read",
      toolCallId: "read-1",
      text: '{"path":"source.ts"}',
    },
    {
      id: "result",
      role: "tool",
      contentType: "tool-result",
      toolName: "read",
      toolCallId: "read-1",
      text: "source content ".repeat(1000),
    },
  );
  state.messageRefs = assignRefs(messages, {
    existing: state.messageRefs,
    nextIndex: 1,
  }).map;
  const report = buildStatusReport(state, messages, defaultCountTokens, {
    scope: "uncompressed",
    view: "messages",
    config,
    originalMessages: messages,
  });
  const call = report
    .split("\n")
    .find((line) => line.includes(state.messageRefs.byRaw.call!));
  assert.ok(call);
  assert.doesNotMatch(call, /not foldable/);
});
