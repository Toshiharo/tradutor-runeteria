// Servidor de traducao do Tradutor Runeteria (Cloudflare Worker).
//
// O app manda texto em ingles que nao achou na biblioteca; o servidor devolve a traducao em pt-BR.
// - Memoria compartilhada (KV): cada texto e traduzido uma vez so; os outros jogadores recebem na hora.
// - Traducao pelo DeepL (chave em segredo DEEPL_KEY, nunca no app: o codigo do app e publico).
// - Nomes e termos fixos chegam protegidos como <k>Zq0x</k>: o DeepL nao mexe neles (ignore_tags).
// - Mensagem de chat vem com guardar=false: nao entra na memoria permanente, mas fica 1 h no cache do
//   Cloudflare (sem limite de gravacao): a mesma mensagem vista por varios jogadores e paga uma vez so.
// - Numeros chegam como <k>N0</k>: "Level 10" e "Level 11" sao o mesmo texto para a memoria.
// - GET /memoria (com o segredo ADMIN_TOKEN): baixa a memoria para revisar e passar para a biblioteca.
// - Limites para a cota gratis do DeepL durar o mes todo (quando estoura, devolve null e o app usa a
//   traducao offline): por dia (LIMITE_DIA), por jogador por dia (LIMITE_IP_DIA) e, passando de 80% da
//   cota do mes, o chat fica so na offline (o resto da cota fica para as telas).
// Nao guarda nada do jogador: o IP so entra cifrado (com o dia) na chave de um contador que some no
// fim do dia; nem nome nem IP sao gravados. Fica so o texto do jogo e a traducao.

const MAX_TEXTS = 20;      // por pedido
const MAX_CHARS = 600;     // por texto
const MAX_TOTAL = 6000;    // por pedido
const VERSAO = "1";        // muda a chave da memoria (zera o cache) se o jeito de traduzir mudar
const CACHE_CHAT = 3600;      // segundos que uma mensagem de chat fica no cache
const CACHE_TELA = 86400 * 7; // texto de tela tambem fica no cache (poupa leitura do KV)
const RESERVA_CHAT = 0.8;     // passou disso da cota do mes: chat so na traducao offline
const RESERVA_TUDO = 0.97;    // perto do fim da cota: tudo na offline

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

function cacheReq(k) {
  return new Request("https://cache.tradutor-runeteria/" + k);
}

async function deCache(k) {
  try {
    const r = await caches.default.match(cacheReq(k));
    return r ? await r.text() : null;
  } catch {
    return null;
  }
}

async function paraCache(k, pt, segundos) {
  try {
    await caches.default.put(cacheReq(k), new Response(pt, {
      headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "public, max-age=" + segundos },
    }));
  } catch {
    // sem cache neste ponto: so perde a economia, a traducao segue
  }
}

function hoje() {
  return new Date().toISOString().slice(0, 10);
}

function ateMeiaNoite() {
  const d = new Date();
  return Math.max(60, Math.ceil((Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() + 1) - d) / 1000));
}

async function contador(nome) {
  const v = await deCache("c:" + nome);
  return v === null ? 0 : Number(v) || 0;
}

async function somar(nome, n) {
  await paraCache("c:" + nome, String((await contador(nome)) + n), ateMeiaNoite());
}

async function usoDoMes(env) {
  // quanto da cota do DeepL ja foi usado (0 a 1); consultado no maximo a cada 10 min
  const salvo = await deCache("uso");
  if (salvo !== null) return Number(salvo);
  try {
    const url = (env.DEEPL_URL || "https://api-free.deepl.com/v2/translate").replace(/\/translate$/, "/usage");
    const r = await fetch(url, { headers: { "Authorization": "DeepL-Auth-Key " + env.DEEPL_KEY } });
    if (!r.ok) return 0;
    const u = await r.json();
    const frac = u.character_limit ? u.character_count / u.character_limit : 0;
    await paraCache("uso", String(frac), 600);
    return frac;
  } catch {
    return 0;
  }
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
    let hit = await deCache(chaves[i]);
    if (hit === null && guardar[i] !== false && env.MEMORIA) {
      hit = await env.MEMORIA.get(chaves[i]);
      if (hit !== null) await paraCache(chaves[i], hit, CACHE_TELA);
    }
    if (hit !== null) out[i] = hit;
    else faltam.push(i);
  }));
  faltam.sort((a, b) => a - b);

  if (faltam.length) {
    // limites: o que nao couber volta como null e o app traduz offline
    const dia = hoje();
    const ip = await chave(dia + "|" + (request.headers.get("CF-Connecting-IP") || "?"));
    const limDia = Number(env.LIMITE_DIA || 20000);
    const limIp = Number(env.LIMITE_IP_DIA || 5000);
    const [usoDia, usoIp, mes] = await Promise.all([contador("dia:" + dia), contador("ip:" + ip), usoDoMes(env)]);
    const soTela = mes >= RESERVA_CHAT || usoDia >= limDia;   // chat primeiro vai para a offline
    const nada = mes >= RESERVA_TUDO || usoDia >= limDia * 1.5 || usoIp >= limIp;
    for (let k = faltam.length - 1; k >= 0; k--) {
      if (nada || (soTela && guardar[faltam[k]] === false)) faltam.splice(k, 1);
    }
  }
  // o mesmo texto duas vezes no pedido vai uma vez so para o DeepL
  const unicos = [...new Set(faltam.map((i) => textos[i]))];

  if (unicos.length) {
    let resp;
    try {
      resp = await fetch(env.DEEPL_URL || "https://api-free.deepl.com/v2/translate", {
      method: "POST",
      headers: { "Authorization": "DeepL-Auth-Key " + env.DEEPL_KEY, "Content-Type": "application/json" },
      body: JSON.stringify({
        text: unicos,
        source_lang: "EN",
        target_lang: "PT-BR",
        tag_handling: "xml",
        ignore_tags: ["k"],
        preserve_formatting: true,
        context: "Interface e falas de um jogo de RPG online (Hytale). Termos de jogo como loot, boss, buff, HP e XP ficam em ingles.",
      }),
      });
    } catch (e) {
      // DeepL fora do ar: devolve o que veio da memoria; o app traduz o resto offline
      return json({ erro: "deepl indisponivel", traducoes: out });
    }
    if (!resp.ok) {
      // 456 = cota do mes acabou: devolve o que veio da memoria; o app traduz o resto offline
      return json({ erro: "deepl " + resp.status, traducoes: out });
    }
    const dados = await resp.json();
    const porTexto = new Map(unicos.map((t, k) => [t, (dados.translations || [])[k]?.text]));
    const gravar = [];
    const feitos = new Set();
    for (const i of faltam) {
      const pt = porTexto.get(textos[i]);
      if (typeof pt !== "string") continue;
      out[i] = pt;
      if (feitos.has(chaves[i])) continue;
      feitos.add(chaves[i]);
      const chat = guardar[i] === false;
      gravar.push(paraCache(chaves[i], pt, chat ? CACHE_CHAT : CACHE_TELA));
      if (!chat && env.MEMORIA) {
        // metadado (ate 1 KB): o texto inteiro, para virar chave da memoria compartilhada do app
        const meta = textos[i].length + pt.length < 900 ? { en: textos[i], pt } : textos[i].length < 900 ? { en: textos[i] } : {};
        // o plano gratis grava 1.000 por dia: se passar, a traducao vai assim mesmo (e fica no cache)
        gravar.push(env.MEMORIA.put(chaves[i], pt, { metadata: meta }).catch(() => null));
      }
    }
    const gastos = unicos.reduce((n, t) => n + t.length, 0);
    const dia = hoje();
    const ip = await chave(dia + "|" + (request.headers.get("CF-Connecting-IP") || "?"));
    gravar.push(somar("dia:" + dia, gastos), somar("ip:" + ip, gastos));
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
