// Servidor de traducao do Tradutor Runeteria (Cloudflare Worker).
//
// O app manda texto em ingles que nao achou na biblioteca; o servidor devolve a traducao em pt-BR.
// - Memoria compartilhada (KV): cada texto e traduzido uma vez so; os outros jogadores recebem na hora.
// - Traducao pelo DeepL (chave em segredo DEEPL_KEY, nunca no app: o codigo do app e publico).
// - Nomes e termos fixos chegam protegidos como <k>Zq0x</k>: o DeepL nao mexe neles (ignore_tags).
// - Mensagem de chat vem com guardar=false: traduz, mas nao entra na memoria (cada mensagem e unica).
// - GET /memoria (com o segredo ADMIN_TOKEN): baixa a memoria para revisar e passar para a biblioteca.
// Nao guarda nada do jogador: nem IP, nem nome, so o texto do jogo e a traducao.

const MAX_TEXTS = 20;      // por pedido
const MAX_CHARS = 600;     // por texto
const MAX_TOTAL = 6000;    // por pedido
const VERSAO = "1";        // muda a chave da memoria (zera o cache) se o jeito de traduzir mudar

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    try {
      if (request.method === "POST" && url.pathname === "/traduzir") return await traduzir(request, env);
      if (request.method === "GET" && url.pathname === "/memoria") return await memoria(request, env, url);
      if (request.method === "GET" && url.pathname === "/") return json({ ok: true, servico: "tradutor-runeteria" });
      return json({ erro: "nao encontrado" }, 404);
    } catch (e) {
      return json({ erro: String(e && e.message || e) }, 500);
    }
  },
};

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
  });
}

async function chave(texto) {
  const dados = new TextEncoder().encode(VERSAO + "\n" + texto);
  const hash = await crypto.subtle.digest("SHA-256", dados);
  return "t:" + [...new Uint8Array(hash)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function traduzir(request, env) {
  if (!(request.headers.get("User-Agent") || "").startsWith("tradutor-runeteria")) {
    return json({ erro: "cliente desconhecido" }, 403);
  }
  let corpo;
  try {
    corpo = await request.json();
  } catch {
    return json({ erro: "json invalido" }, 400);
  }
  const textos = Array.isArray(corpo.textos) ? corpo.textos : null;
  const guardar = Array.isArray(corpo.guardar) ? corpo.guardar : [];
  if (!textos || !textos.length || textos.length > MAX_TEXTS) return json({ erro: "textos invalidos" }, 400);
  let total = 0;
  for (const t of textos) {
    if (typeof t !== "string" || !t.trim() || t.length > MAX_CHARS) return json({ erro: "texto invalido" }, 400);
    total += t.length;
  }
  if (total > MAX_TOTAL) return json({ erro: "pedido grande demais" }, 400);

  const out = new Array(textos.length).fill(null);
  const chaves = await Promise.all(textos.map(chave));
  const faltam = [];
  await Promise.all(textos.map(async (t, i) => {
    if (guardar[i] === false) { faltam.push(i); return; }
    const hit = env.MEMORIA ? await env.MEMORIA.get(chaves[i]) : null;
    if (hit !== null) out[i] = hit;
    else faltam.push(i);
  }));
  faltam.sort((a, b) => a - b);

  if (faltam.length) {
    const resp = await fetch(env.DEEPL_URL || "https://api-free.deepl.com/v2/translate", {
      method: "POST",
      headers: { "Authorization": "DeepL-Auth-Key " + env.DEEPL_KEY, "Content-Type": "application/json" },
      body: JSON.stringify({
        text: faltam.map((i) => textos[i]),
        source_lang: "EN",
        target_lang: "PT-BR",
        tag_handling: "xml",
        ignore_tags: ["k"],
        preserve_formatting: true,
        context: "Interface e falas de um jogo de RPG online (Hytale). Termos de jogo como loot, boss, buff, HP e XP ficam em ingles.",
      }),
    });
    if (!resp.ok) {
      // 456 = cota do mes acabou; o app volta para a traducao offline
      return json({ erro: "deepl " + resp.status, traducoes: out }, resp.status === 456 ? 503 : 502);
    }
    const dados = await resp.json();
    const trad = (dados.translations || []).map((x) => x.text);
    const gravar = [];
    faltam.forEach((i, k) => {
      const pt = trad[k];
      if (typeof pt !== "string") return;
      out[i] = pt;
      if (guardar[i] !== false && env.MEMORIA) {
        const meta = textos[i].length + pt.length < 900 ? { en: textos[i], pt } : { en: textos[i].slice(0, 400) };
        gravar.push(env.MEMORIA.put(chaves[i], pt, { metadata: meta }));
      }
    });
    await Promise.all(gravar);
  }
  return json({ traducoes: out });
}

async function memoria(request, env, url) {
  const token = request.headers.get("Authorization") || "";
  if (!env.ADMIN_TOKEN || token !== "Bearer " + env.ADMIN_TOKEN) return json({ erro: "sem permissao" }, 401);
  const lista = await env.MEMORIA.list({ prefix: "t:", cursor: url.searchParams.get("cursor") || undefined });
  const itens = await Promise.all(lista.keys.map(async (k) => {
    const m = k.metadata || {};
    const pt = m.pt !== undefined ? m.pt : await env.MEMORIA.get(k.name);
    return { en: m.en, pt };
  }));
  return json({ itens, cursor: lista.list_complete ? null : lista.cursor });
}
