export type OtpPurpose = "verify_email" | "login";
export type ProjectStatus = "active" | "archived";
export type DocumentStatus = "pending" | "processing" | "ready" | "failed";
export type MessageRole = "user" | "assistant";
export type RetrievalMode = "hybrid" | "dense" | "sparse";

export type MessageResponse = {
  message: string;
};

export type UserResponse = {
  id: string;
  email: string;
  full_name: string | null;
  is_verified: boolean;
  is_active: boolean;
  sso_provider: string | null;
  sso_subject: string | null;
  avatar_url: string | null;
  created_at: string;
  updated_at: string;
};

export type AuthRegisterRequest = {
  full_name: string;
  email: string;
  password: string;
};

export type AuthVerifyOtpRequest = {
  email: string;
  code: string;
  purpose: OtpPurpose;
};

export type AuthLoginRequest = {
  email: string;
  password: string;
};

export type AuthRequestOtpRequest = {
  email: string;
};

export type AuthUpdateMeRequest = {
  full_name?: string;
  avatar_url?: string;
};

export type TokenResponse = {
  access_token: string;
  token_type: "bearer";
};

export type AuthTokenUserResponse = TokenResponse & {
  user: UserResponse;
};

export type ProjectCreateRequest = {
  name: string;
  description?: string;
};

export type ProjectUpdateRequest = {
  name?: string;
  description?: string;
};

export type ProjectCreateResponse = {
  project_id: string;
  name: string;
  qdrant_namespace: string;
  doc_count: number;
  chunk_count: number;
  created_at: string;
};

export type ProjectResponse = {
  id: string;
  user_id: string;
  name: string;
  description: string | null;
  qdrant_namespace: string;
  doc_count: number;
  chunk_count: number;
  status: ProjectStatus;
  created_at: string;
  updated_at: string;
};

export type ProjectListResponse = {
  projects: ProjectResponse[];
};

export type DocumentUploadItemResponse = {
  doc_id: string;
  status: DocumentStatus;
};

export type DocumentUploadResponse = {
  documents: DocumentUploadItemResponse[];
};

export type DocumentResponse = {
  id: string;
  project_id: string;
  user_id: string;
  filename: string;
  original_path: string;
  mime_type: string | null;
  file_size_bytes: number | null;
  doc_type: string | null;
  num_chunks: number | null;
  status: DocumentStatus;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type DocumentListResponse = {
  documents: DocumentResponse[];
};

export type ChatSessionCreateRequest = {
  title?: string;
};

export type ChatSessionUpdateRequest = {
  title?: string;
  is_archived?: boolean;
};

export type ChatSessionResponse = {
  id: string;
  project_id: string;
  user_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  is_archived: boolean;
};

export type ChatSessionListResponse = {
  sessions: ChatSessionResponse[];
};

export type ChatMessageResponse = {
  id: string;
  session_id: string;
  role: MessageRole;
  content: string;
  sources: unknown;
  confidence: number | null;
  retrieval_meta: unknown;
  created_at: string;
};

export type ChatMessageListResponse = {
  messages: ChatMessageResponse[];
};

export type AskRequest = {
  session_id: string;
  question: string;
  top_k?: number;
  retrieval_mode?: RetrievalMode;
  use_hyde?: boolean;
};

export type SourceChunkResponse = {
  chunk_id: string;
  text: string;
  page: number | null;
  source_filename: string;
  reranker_score: number | null;
};

export type ConfidenceBreakdown = {
  retrieval_score: number;
  chunk_agreement: number;
  answer_coverage: number;
  source_count: number;
};

export type AskResponse = {
  answer: string;
  confidence: number;
  confidence_breakdown: ConfidenceBreakdown;
  sources: SourceChunkResponse[];
  refused: boolean;
  latency_ms: number;
};

export type ExtractRequest = {
  session_id: string;
  prompt: string;
  top_k?: number;
  retrieval_mode?: RetrievalMode;
  use_hyde?: boolean;
};

export type ExtractResponse = {
  data: Record<string, unknown>;
  confidence: number | null;
  sources: SourceChunkResponse[];
};

export type HealthResponse = {
  status: string;
};
