// Backend schema mirrors (loose — defensive access in pages).

export interface User {
  id: number;
  email: string;
  name: string;
  created_at?: string;
}

export interface AuthResponse {
  token: { access_token: string; expires_in: number };
  user: User;
}

export interface Track {
  id: number;
  spotify_track_id: string;
  track_name: string;
  artist_name: string;
  album_name?: string | null;
  release_date?: string | null;
  artwork_path?: string | null;
  album_art_url?: string | null;
  genre?: string | null;
  duration_ms?: number | null;
  popularity_signal?: number | null;
  exposure_label?: string | null;
  discovery_score?: number | null;
  status: string;
  rights_status: string;
  spotify_url?: string | null;
}

export interface VideoTemplate {
  id: number;
  name: string;
  label: string;
  description?: string | null;
  defaults?: Record<string, string | number>;
}

export interface Video {
  id: number;
  track_id: number;
  template: string;
  status: string;
  file_path?: string | null;
  preview: boolean;
  thumbnail_path?: string | null;
  duration_ms?: number | null;
  created_at?: string | null;
}

export interface Stats {
  tracks_discovered: number;
  awaiting_permission: number;
  licensed_tracks: number;
  videos_generated: number;
  uploaded_to_youtube: number;
  failed_jobs: number;
}

export interface AutomationInfo {
  automation_count: number;
  enabled: number;
  next_run_at?: string | null;
  discovery_frequency_hours?: number | null;
}

export interface Dashboard {
  stats: Stats;
  recent_tracks: Track[];
  recent_videos: Video[];
  recent_uploads: unknown[];
  queue: Array<{ id: number; job_type: string; status: string; progress: number }>;
  automation: AutomationInfo;
  provider_mode: string;
}

export interface DiscoverResult {
  discovered: number;
  new_tracks: number;
  scoring_summary: {
    provider: string;
    candidates: number;
    score_range: [number, number];
  };
}

export interface Permission {
  id: number;
  track_id: number;
  artist?: string | null;
  email?: string | null;
  status: string;
}

export interface Job {
  id: number;
  job_type: string;
  status: string;
  progress: number;
  result?: Record<string, unknown> | null;
  error?: string | null;
  created_at?: string | null;
}

export interface Automation {
  id: number;
  name: string;
  enabled: boolean;
  discovery_frequency_hours?: number | null;
  max_tracks?: number | null;
  target_platforms?: string[] | null;
  next_run_at?: string | null;
  last_run_at?: string | null;
}