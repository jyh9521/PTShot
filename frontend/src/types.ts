export interface Settings {
  mode: 'screenshots' | 'sheet' | 'both'; count: number; cols: number; rows: number; width: number;
  content_type: number; thumbnail_size: number; upload: boolean; optimization: number; tools: Record<string, string>;
}
export interface Video { path: string; name: string; size: number }
export interface ImageRecord {
  source_video: string; original_path: string; upload_path: string; original_bytes: number; upload_bytes: number;
  width: number; height: number; status: string; show_url: string; direct_url: string; thumbnail_url: string;
  error: string; preview_url?: string;
}
export interface Job { directory: string; settings: Settings; videos: string[]; records: ImageRecord[]; errors: string[]; state: string; successful_urls: string[] }
export interface WorkerEvent { type: string; job?: Job; message?: string; busy?: boolean; tools?: Record<string, string> }
export interface Bootstrap { version: string; settings: Settings; output: string; theme: string; tools: Record<string, string> }
export interface DesktopAPI {
  bootstrap(): Promise<Bootstrap>;
  chooseVideos(): Promise<Video[]>; chooseFolder(): Promise<Video[]>; importPaths(paths: string[]): Promise<Video[]>;
  pathForFile(file: File): string;
  chooseOutput(): Promise<string | null>; chooseTool(name: string): Promise<string | null>;
  openSession(): Promise<WorkerEvent | null>;
  start(request: { videos: string[]; output: string; settings: Settings }): Promise<WorkerEvent>;
  retry(settings: Settings): Promise<WorkerEvent>; cancel(): Promise<boolean>;
  inspect(settings: Settings): Promise<WorkerEvent>; install(settings: Settings): Promise<WorkerEvent>;
  savePreferences(value: { settings: Settings; output: string; theme: string }): Promise<boolean>;
  copy(text: string): Promise<boolean>; openOutput(): Promise<string>; openImage(index: number): Promise<string>;
  openProject(): Promise<void>; onEvent(callback: (event: WorkerEvent) => void): () => void;
}
declare global { interface Window { ptshot: DesktopAPI } }
