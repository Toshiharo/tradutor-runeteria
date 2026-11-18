# Servidor de tradução online

Um Cloudflare Worker (`worker.js`) que traduz com o DeepL e guarda uma memória compartilhada: cada texto
do jogo é traduzido uma vez só, e os outros jogadores recebem na hora. O app usa o servidor só para texto
que não está na biblioteca; se ele não responder, usa a tradução offline.

Custo: zero nos planos gratuitos (Cloudflare Workers + KV; DeepL API Free = 500 mil caracteres por mês).
Mensagens de chat são traduzidas mas não entram na memória (cada uma é única; poupa a cota de gravação do KV).

## Publicar (uma vez)

Precisa do Node.js. Nesta pasta:

```
npm install
npx wrangler login                          # abre o navegador para entrar na conta Cloudflare
npx wrangler kv namespace create MEMORIA    # copie o "id" que aparecer para o wrangler.toml
npx wrangler secret put DEEPL_KEY           # cole a chave da API do DeepL (termina em ":fx")
npx wrangler secret put ADMIN_TOKEN         # invente uma senha longa (para baixar a memória)
npx wrangler deploy                         # mostra o endereço: https://tradutor-runeteria.<conta>.workers.dev
```

Depois coloque o endereço em `app/config.py` (`ONLINE_MT_URL`) e gere uma versão nova do app.

## Revisar a memória

`GET /memoria` com o cabeçalho `Authorization: Bearer <ADMIN_TOKEN>` devolve `{itens: [{en, pt}], cursor}`
(passe `?cursor=` para a próxima página). As boas vão para `app/data/biblioteca.json` como revisadas.

## Testar sem conta

Crie `.dev.vars` com `DEEPL_KEY=...`, `ADMIN_TOKEN=...` e `DEEPL_URL=` apontando para um DeepL simulado,
e rode `npx wrangler dev --local`.
