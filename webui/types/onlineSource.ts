/** 已导入的在线源摘要（不含选择器细节） */
export interface OnlineSourceSummary {
  name: string;
  icon: string;
  description: string;
  tier: number;
}

/** 搜索结果：一个番剧条目 */
export interface OnlineSubject {
  name: string;
  url: string;
}

/** 单集：解析出的集号 + 集名 + 播放页链接 */
export interface OnlineEpisode {
  sort: number | null;
  name: string;
  url: string;
}

/** 一条播放路线：路线名 + 集数列表 */
export interface OnlineChannel {
  name: string;
  episodes: OnlineEpisode[];
}

/** 下载请求：解析片源直链并下载到指定番剧 */
export interface OnlineDownloadRequest {
  source: string;
  episode_url: string;
  bangumi_id: number;
  season: number;
  episode: number;
  media_type: string;
}
