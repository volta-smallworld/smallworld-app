// Render artifact from a successful preview_render_pose call
export interface RenderArtifact {
  id: string;                // preview ID from tool result
  createdAt: string;         // ISO 8601 timestamp
  summary: string;           // e.g. "Terrain preview facing NW at 45°..."
  camera: {
    position: { lat: number; lng: number; alt_meters: number };
    heading_deg: number;
    pitch_deg: number;
    roll_deg: number;
    fov_deg: number;
  };
  scene: {
    center: { lat: number; lng: number };
    radius_meters: number;
    scene_id?: string;
    scene_type?: string;
  };
  composition: {
    target_template: string;
    subject_label?: string;
    horizon_ratio?: number;
    anchors?: Array<{
      id?: string; label?: string;
      lat: number; lng: number; alt_meters: number;
      desired_normalized_x: number; desired_normalized_y: number;
    }>;
  };
  viewport?: { width: number; height: number };
  enhancement?: { enabled: boolean; prompt?: string };
}

// Chat message for UI display and localStorage persistence
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
  toolRuns?: ToolRun[];
}

// Tool execution trace entry
export interface ToolRun {
  toolName: string;
  input: Record<string, unknown>;
  output: string;
  isError: boolean;
  errorMessage?: string;
  durationMs: number;
  startedAt: string; // ISO 8601
}

// Server-Sent Event types for streaming chat responses
export type StreamEvent =
  | { type: "text_delta"; delta: string }
  | { type: "tool_start"; toolName: string; input: Record<string, unknown>; startedAt: string }
  | { type: "tool_end"; toolName: string; output: string; isError: boolean; errorMessage?: string; durationMs: number; startedAt: string }
  | { type: "done"; id: string; content: string; toolRuns: ToolRun[]; artifacts?: RenderArtifact[]; usage?: { inputTokens: number; outputTokens: number } }
  | { type: "error"; message: string; code?: string }
  | { type: "status"; message: string };

// API request payload sent to POST /api/chat
export interface ChatRequest {
  messages: Array<{
    id: string;
    role: "user" | "assistant";
    content: string;
  }>;
  stream?: boolean;
  artifacts?: RenderArtifact[];
}

// API response from POST /api/chat
export interface ChatResponse {
  assistant: {
    id: string;
    role: "assistant";
    content: string;
  };
  toolRuns: ToolRun[];
  artifacts?: RenderArtifact[];
  usage?: {
    inputTokens: number;
    outputTokens: number;
  };
}

// API error response
export interface ChatErrorResponse {
  error: string;
  code?: string;
}

// Tool log entry returned by GET /api/tool-logs (balanced/truncated for UI)
export interface ToolLogEntry {
  id: string;
  eventType: "tool_discovery" | "tool_call";
  requestId: string;
  toolName: string;
  startedAt: string;
  endedAt: string;
  durationMs: number;
  isError: boolean;
  errorMessage?: string;
  inputPreview: string;
  inputTruncated: boolean;
  outputPreview: string;
  outputTruncated: boolean;
  metadata: { mcpServerUrl?: string; round?: number };
}

// Response from GET /api/tool-logs
export interface ToolLogsResponse {
  entries: ToolLogEntry[];
  total: number;
}
