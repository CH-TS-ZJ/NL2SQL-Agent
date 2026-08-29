/**
 * 智能体接口客户端
 * 封装后端 /api/query SSE 流式接口请求与事件解析逻辑
 */
import type { AgentEvent, ChatMessage, SessionHistory } from "../types/agent";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ?? "";

type QueryOptions = {
  sessionId?: string;
  signal?: AbortSignal;
  onEvent: (event: AgentEvent) => void;
};

export async function streamQuery(query: string, options: QueryOptions) {
  const response = await fetch(`${API_BASE_URL}/api/query`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({ query, session_id: options.sessionId }),
    signal: options.signal,
  });

  if (!response.ok) {
    throw new Error(`接口请求失败：HTTP ${response.status}`);
  }

  if (!response.body) {
    throw new Error("浏览器未返回可读取的流式响应。");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split(/\n\n/);
    buffer = chunks.pop() ?? "";

    for (const chunk of chunks) {
      const event = parseSseChunk(chunk);
      if (event) {
        options.onEvent(event);
      }
    }
  }

  buffer += decoder.decode();
  const tail = parseSseChunk(buffer);
  if (tail) {
    options.onEvent(tail);
  }
}

function parseSseChunk(chunk: string): AgentEvent | null {
  const payload = chunk
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.replace(/^data:\s?/, ""))
    .join("\n")
    .trim();

  if (!payload) return null;

  try {
    return JSON.parse(payload) as AgentEvent;
  } catch {
    return {
      type: "error",
      message: `无法解析后端事件：${payload}`,
    };
  }
}

type StoredMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: number;
  sql?: string | null;
  result?: unknown;
  error?: string | null;
  detail?: string | null;
};

function toChatMessage(message: StoredMessage): ChatMessage {
  if (message.role === "user") {
    return { id: message.id, role: "user", content: message.content, createdAt: message.createdAt };
  }

  return {
    id: message.id,
    role: "assistant",
    content: message.content,
    createdAt: message.createdAt,
    status: message.error ? "error" : "done",
    result: message.result ?? undefined,
    error: message.error ?? undefined,
    errorSql: message.sql ?? undefined,
    errorDetail: message.detail ?? undefined,
  };
}

/** 拉取单个会话的历史消息，用于页面刷新后恢复对话 */
export async function getSession(sessionId: string): Promise<SessionHistory> {
  const response = await fetch(`${API_BASE_URL}/api/sessions/${sessionId}`);

  if (!response.ok) {
    throw new Error(`加载会话失败：HTTP ${response.status}`);
  }

  const data = (await response.json()) as {
    id: string;
    title: string;
    messages: StoredMessage[];
  };

  return {
    id: data.id,
    title: data.title,
    messages: data.messages.map(toChatMessage),
  };
}
