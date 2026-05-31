import { Pool } from 'pg';

const pool = new Pool({
  host: process.env.DB_HOST || 'localhost',
  port: parseInt(process.env.DB_PORT || '5432'),
  database: process.env.DB_NAME || 'groundtruth',
  user: process.env.DB_USER || 'postgres',
  password: process.env.DB_PASSWORD || 'postgres',
});

export async function query(text: string, params?: any[]) {
  const client = await pool.connect();
  try {
    return await client.query(text, params);
  } finally {
    client.release();
  }
}

export async function hybridSearch(
  workspaceId: string,
  embedding: number[],
  keywordQuery: string,
  topK: number = 10
) {
  const result = await query(
    `
    SELECT id, content, source,
      (0.7 * ts_rank_cd(to_tsvector('english', content), plainto_tsquery('english', $3)) +
       0.3 * (1 - (embedding <=> $2::vector))) AS score
    FROM documents
    WHERE workspace_id = $1
    ORDER BY score DESC
    LIMIT $4
    `,
    [workspaceId, `[${embedding.join(',')}]`, keywordQuery, topK]
  );
  return result.rows;
}
