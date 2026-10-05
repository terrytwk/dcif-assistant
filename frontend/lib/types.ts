export type RetrievalResult = {
  chunk_id: string;
  source_url: string;
  source_title: string;
  document_type: "html" | "pdf" | "text" | "structured";
  section_heading: string;
  page: number | null;
  crawl_timestamp: string;
  source_hash: string;
  text: string;
  score: number;
  rank: number;
};

export type ChatCitation = {
  chunk_id: string;
  source_url: string;
  source_title: string;
  section_heading: string;
  page: number | null;
};

export type ChatAnswer = {
  answer: string;
  citations: ChatCitation[];
  confidence: "low" | "medium" | "high";
};

export type ChatResponse = {
  answer: ChatAnswer;
  retrieved: RetrievalResult[];
  llm_enabled: boolean;
};
