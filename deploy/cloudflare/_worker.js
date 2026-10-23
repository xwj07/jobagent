export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === '/' || url.pathname.startsWith('/static/')) {
      return env.ASSETS.fetch(request);
    }
    if (url.pathname === '/evaluation') {
      url.pathname = '/evaluation.html';
      return env.ASSETS.fetch(new Request(url, request));
    }
    if (!env.BACKEND_URL) {
      return Response.json({detail: '尚未配置服务器地址 BACKEND_URL。'}, {status: 503});
    }
    const target = new URL(env.BACKEND_URL);
    target.pathname = url.pathname;
    target.search = url.search;
    try {
      return await fetch(new Request(target, request));
    } catch {
      return Response.json({detail: '无法连接服务器，请检查服务器电脑和 Cloudflare Tunnel 是否在线。'}, {status: 502});
    }
  },
};
