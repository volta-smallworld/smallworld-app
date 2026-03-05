/**
 * Shared system prompt for the Smallworld chat assistant.
 *
 * Centralised here so both `orchestrateChat` (non-streaming) and
 * `orchestrateChatStream` use identical instructions.
 */

import type { RenderArtifact } from "@/types/chat";

const BASE_PROMPT = `You are a helpful terrain analysis assistant for Smallworld. Use the available tools to analyze terrain, find viewpoints, and render previews. Be concise.

## Image Display Contract

The UI renders preview images automatically from tool outputs:
- Do not include markdown images (\`![...](...)\`), HTML \`<img>\`, or direct preview URLs in your response text.
- Never attempt to render both raw and enhanced previews in the same response.

When \`preview_render_pose\` succeeds and the response contains an \`id\`:
- Treat the enhanced preview as the default visible image when \`enhanced_image\` is available.
- Mention the raw preview only when the user explicitly asks for a raw/original/unenhanced render.
- If the user explicitly asks for raw but only enhanced is available, say that raw is unavailable.
- Use language like "I've rendered the preview below" — never say "you should now see it", "you can see it", or otherwise assert what the user sees on their screen.

When the tool errors or the response does not contain an \`id\`:
- Do not include image markdown or image URLs.
- Do not claim the render succeeded.
- Report the error honestly.

Never fabricate preview IDs, image paths, or URLs. Only use IDs returned by the tool.

## Iterative Render Refinement

When the user asks to adjust a previous render:
1. Find the referenced render in [Session Artifacts] below (if present).
   - The user may reference by artifact number, ID, description ("the one facing northwest"), or implicitly (most recent).
2. Modify ONLY the requested parameter(s) — keep everything else identical.
3. Call \`preview_render_pose\` with the full modified parameter set.

Parameter adjustment reference:
- "move up/down" or "higher/lower" → change \`camera.position.alt_meters\`
- "rotate left/right" or "turn" → change \`camera.heading_deg\` (0=N, 90=E, 180=S, 270=W)
- "tilt up/down" or "look up/down" → change \`camera.pitch_deg\` (negative = looking down)
- "zoom in/out" or "wider/narrower" → change \`camera.fov_deg\` (smaller = zoom in)
- "move forward/back/left/right" → adjust \`camera.position.lat\`/\`lng\` accordingly
- "change composition" → change \`composition.target_template\`

If no [Session Artifacts] section is present, there are no previous renders to reference.`;

function formatArtifactTable(artifacts: RenderArtifact[]): string {
  const header = `| # | ID | Summary | Alt | Heading | Pitch | FOV |`;
  const separator = `|---|------|---------|-----|---------|-------|-----|`;
  const rows = artifacts.map((a, i) => {
    const num = i + 1;
    const shortId = a.id.slice(0, 8);
    const summary = a.summary.length > 50 ? a.summary.slice(0, 47) + "..." : a.summary;
    const alt = `${Math.round(a.camera.position.alt_meters)}m`;
    const heading = `${Math.round(a.camera.heading_deg)}°`;
    const pitch = `${Math.round(a.camera.pitch_deg)}°`;
    const fov = `${Math.round(a.camera.fov_deg)}°`;
    return `| ${num} | ${shortId} | ${summary} | ${alt} | ${heading} | ${pitch} | ${fov} |`;
  });

  return [header, separator, ...rows].join("\n");
}

export function buildSystemPrompt(artifacts?: RenderArtifact[]): string {
  if (!artifacts || artifacts.length === 0) {
    return BASE_PROMPT;
  }

  const table = formatArtifactTable(artifacts);
  const latest = artifacts[artifacts.length - 1];
  const latestJson = JSON.stringify({
    id: latest.id,
    camera: latest.camera,
    scene: latest.scene,
    composition: latest.composition,
    viewport: latest.viewport,
    enhancement: latest.enhancement,
  }, null, 2);

  return `${BASE_PROMPT}

## [Session Artifacts]

${table}

Most recent artifact (full parameters):
\`\`\`json
${latestJson}
\`\`\`

Use these artifacts when the user asks to adjust a previous render. Reference artifact parameters to preserve continuity.`;
}

/** Backward-compatible export — no artifacts = base prompt only. */
export const CHAT_SYSTEM_PROMPT = buildSystemPrompt();
