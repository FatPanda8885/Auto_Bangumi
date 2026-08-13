import type {
  OnlineChannel,
  OnlineDownloadRequest,
  OnlineSourceSummary,
  OnlineSubject,
} from '#/onlineSource';

type EventSourceStatus = 'OPEN' | 'CONNECTING' | 'CLOSED';

export const apiOnlineSource = {
  /** 已导入的在线源列表 */
  async listSources() {
    const { data } = await axios.get<OnlineSourceSummary[]>(
      'api/v1/online_source/sources'
    );
    return data;
  },

  /** 拉取并覆盖导入 css1.json 订阅列表 */
  async importSources(url: string) {
    const { data } = await axios.post<{ imported: number }>(
      'api/v1/online_source/import',
      { url }
    );
    return data;
  },

  /** 某番剧详情页的播放路线与集数列表 */
  async getEpisodes(source: string, subject: string) {
    const { data } = await axios.get<OnlineChannel[]>(
      'api/v1/online_source/episodes',
      { params: { source, subject } }
    );
    return data;
  },

  /** 解析片源直链并下载到指定番剧 */
  async download(payload: OnlineDownloadRequest) {
    const { data } = await axios.post<{ status: string }>(
      'api/v1/online_source/download',
      payload
    );
    return data;
  },

  /** SSE 流式搜索 */
  search() {
    // shallowRef：ref() 会把 EventSource 包成 reactive 代理，
    // 导致下面 `eventSource.value !== es` 的同流判定永远为真
    const eventSource = shallowRef<EventSource | null>(null);
    const status = ref<EventSourceStatus>('CLOSED');
    const data = ref<OnlineSubject[]>([]);
    const error = ref(false);

    const keyword = ref('');
    const source = ref('');

    const close = () => {
      if (eventSource.value) {
        eventSource.value.close();
        eventSource.value = null;
        status.value = 'CLOSED';
      }
    };

    const _init = () => {
      status.value = 'CONNECTING';

      const url = `api/v1/online_source/search?source=${
        source.value
      }&keyword=${encodeURIComponent(keyword.value)}`;

      const es = new EventSource(url, { withCredentials: true });
      eventSource.value = es;
      es.onopen = () => {
        if (eventSource.value !== es) return;
        status.value = 'OPEN';
      };
      es.onmessage = (e) => {
        if (eventSource.value !== es) {
          es.close();
          return;
        }
        const subject = JSON.parse(e.data) as OnlineSubject;
        if (!subject.name || !subject.url) return;
        if (data.value.some((d) => d.url === subject.url)) return;
        data.value = [...data.value, subject];
      };
      es.onerror = () => {
        if (eventSource.value !== es) {
          es.close();
          return;
        }
        if (status.value === 'CONNECTING') {
          error.value = true;
        }
        close();
      };
    };

    const open = () => {
      close();
      data.value = [];
      error.value = false;
      _init();
    };

    return { keyword, source, status, data, error, open, close };
  },
};
