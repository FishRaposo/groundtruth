import { NextRequest } from 'next/server';

export const runtime = 'edge';

export async function POST(req: NextRequest) {
  const { message, workspace_id } = await req.json();

  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      const chunks = [
        JSON.stringify({ type: 'chunk', text: 'Searching knowledge base...' }),
        JSON.stringify({ type: 'citation', source: 'docs/getting-started.md', text: 'GroundTruth supports hybrid search.' }),
        JSON.stringify({ type: 'chunk', text: ' Found relevant documents.' }),
        JSON.stringify({ type: 'chunk', text: ' GroundTruth uses PostgreSQL + pgvector for vector storage.' }),
        JSON.stringify({ type: 'done' }),
      ];
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(`data: ${chunk}\n\n`));
        await new Promise((r) => setTimeout(r, 300));
      }
      controller.close();
    },
  });

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      Connection: 'keep-alive',
    },
  });
}
