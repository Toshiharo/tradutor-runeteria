# Tradutor Runeteria — contexto para o Claude Code

Responda sempre em português (pt-BR). O autor é o dev principal de UI/UX do Runeteria e o dono do servidor
autorizou o programa: não é "projeto de fã" (não escrever isso em textos públicos), mas também não é produto
oficial do Hytale. Feito pelo autor (Windows) para ele e para ser
compartilhado com outros jogadores brasileiros. Todas as traduções são em português do Brasil (nunca pt-PT).

## O que é
App Windows que traduz para pt-BR as telas do servidor **Runeteria** (Hytale, `play.runeteria.com:5520`),
desenhando a tradução por cima da janela do jogo. Só funciona dentro do Runeteria. A tradução é offline
(a internet é usada só para baixar traduções/versões novas, ver "Internet").
O cliente do Hytale não aceita mods: o app só lê a tela, os logs e o cache. **Nunca modificar o cache do jogo.**

## Status
- Roda no Windows (2026-11-18): Python 3.12.10 em `.venv`, winrt 4.x, ctranslate2 4.9, mss 10, PyInstaller 6.22.
  OCR en-US instalado; modelo em `modelos/en_pt`; `dist\TradutorRuneteria\` gerado e abre sem erro.
- Verificado de verdade: OCR, tradução offline, biblioteca/fuzzy, lock no log real, atualizador no cache real, captura da janela.
- Overlay conferido em 2026-11-18 sobre uma captura real do jogo (tela Overview, 1920x1009): em 77 textos, mediana de
  altura x1,00, largura x1,00 e desvio vertical 0 px contra o original. O app também rodou ao vivo com o jogo em foco
  sem erro. O OCR lê só a janela do jogo (`winutil.grab_window`, PrintWindow ~21 ms), então o overlay aparece em
  gravações/transmissões (OBS, Discord) — `permitir_gravar`. Se o PrintWindow vier preto, volta para a captura da tela
  com o overlay excluído (`SetWindowDisplayAffinity`). A conferência visual também é feita desenhando com `App.draw`
  sobre a captura; o clique atravessando o overlay só o usuário consegue confirmar.
  O jogo precisa estar em janela / janela sem bordas (tela cheia exclusiva esconde o overlay).
- A tradução automática (Argos) é fraca em rótulos curtos e puxa para pt-PT; o que importa deve ir para `biblioteca.json`.

## Arquitetura (`app/`)
- `main.py` — janela de controle tkinter + overlay transparente click-through + thread de captura (mss).
  `worker` captura a cada 0,15 s, mas só faz OCR quando precisa: confere a região de cada tradução desenhada
  (`style.region_thumb`/`region_changed`) e tira na hora a que ficou em cima de texto que mudou (troca de menu ~0,03 s,
  menu fechado ~0,1 s); relê assim que a tela para de mexer; senão relê a cada `intervalo_segundos` (0,8 s).
  Atalhos globais F8 liga/desliga, F9 mostra original, F10 salva `ultima_tela.txt`.
- `lock.py` — lê incrementalmente o `*_client.log` mais recente em `%APPDATA%\Hytale\UserData\Logs`.
  Classe `Session`: "Direct connecting to multiplayer server at X" define a sessão; "Referral: A -> B" e reconexões
  mantêm a sessão (o Runeteria transfere para sub-servidores por IP: 135.148.52.87, 40.160.66.98, 51.195.60.189);
  "Changing from Stage … to MainMenu/Exited" encerra. Ativo = sessão contém `runeteria.com` e estágio `InGame`.
- `ocr_engine.py` — OCR nativo do Windows (Windows.Media.Ocr via pacotes `winrt-*`), precisa do pacote OCR en-US.
- `pipeline.py` — agrupa linhas em parágrafos; biblioteca primeiro; desconhecidos vão para fila de tradução offline,
  mas só se passarem no filtro `looks_translatable` (descarta lixo de OCR do cenário) e ficarem ~1,5 s parados na tela.
  O que o modelo não traduz entra num cache negativo (`failed`) e não é tentado de novo na sessão.
- `style.py` — aparência do overlay (só PIL), tudo medido na captura: `add_colors` anota em cada linha a cor de
  fundo/letra, o fundo liso dos lados (`room_l`/`room_r`), topo/altura/quantidade de tinta das letras (`iy`/`ih`/`ink`),
  fundo em degradê (`grad`) e se a palavra foi cortada pelo OCR (`cut`, aí não traduz). `pick_face` escolhe a fonte do
  jogo com os arquivos de `app/fonts`: família pela largura (MAIÚSCULAS→Lexend, texto→Inter, título grande→Cormorant),
  peso pela tinta, tamanho pela altura das letras, e devolve o espaçamento entre letras (`track`) e a linha de base.
  `guess_align` decide esquerda/centro/direita pelas vizinhas e pelo fundo dos lados.
  `main.draw` alinha pela linha de base, desenha letra a letra quando há espaçamento (`draw_tracked`), nunca quebra
  no meio de palavra e não redesenha se nada mudou. Tradução automática aparece em itálico.
  `usar_cores_da_tela: false` volta às cores fixas; `fonte_overlay` troca "auto" por uma fonte fixa.
- `variaveis.py` + `pipeline.Translator` — partes variáveis e telas nunca vistas. Ordem em `Translator._one`:
  biblioteca (exato, ou parecido aprovado por `library.adapt`) → `compose` (linha de tooltip/atributo montada por
  partes: nome no começo + termos da biblioteca/`termos_fixos` + valores intactos) → nome próprio (`is_name`) ou
  ruído (`is_noise`, nome de jogador no chat) ficam em inglês sem caixa → tradução automática em lote, com nomes e
  valores protegidos (`names_in`). "Nome" = 2–5 palavras com inicial maiúscula sem palavra de frase, ou palavra que o
  modelo quebra em 3+ pedaços (`unknown_word`). `adapt` só troca pedaço com cara de valor (`_variable_like`:
  número, apóstrofo, nome de 2+ palavras) e só aceita erro de OCR em texto quase idêntico: nunca põe na tela nome
  ou valor que não é o do jogo. Memória automática tem `"v": 2`; entradas `auto-tela` antigas são descartadas.
  Testes: `.venv\Scripts\python.exe -m unittest discover -s tests` (casos reais de tooltip/skill/item).
- `pipeline.tidy_lines` (antes de traduzir) separa colunas que o OCR juntou e tira ícones lidos como letra
  ("O MANA"); `join_known` junta pedaços de rótulos espaçados quando o conjunto existe na biblioteca ("RUNE BACKPACK").
- `library.py` — prioridade: `minhas_traducoes.json` (usuário) > `data/biblioteca.json` (~2.770 revisadas; a cópia baixada do GitHub só vale no programa instalado e se for mais nova)
  > `memoria_automatica.json`. Normaliza caixa/pontuação, números viram `#` e são reinseridos; rapidfuzz ratio ≥ 86.
- `mt.py` — modelo Argos en→pt rodando direto em ctranslate2 + sentencepiece (sem argostranslate/torch).
  Termos do glossário protegidos com marcadores `ZqNx`; se o modelo perder um, traduz os pedaços entre os termos.
- `updater.py` — linhas do log `asset <sha256>: <n>, <caminho>` dão o caminho real; arquivo em
  `CachedAssets\<hash[:2]>\<hash[2:]>` (lido com compartilhamento total, o jogo trava o arquivo).
  Extrai `Text:`/`TooltipText:`/`PlaceholderText:` de `.ui` e valores de `.lang` (`extract_ui.py`), ignora telas
  de admin (regex `ADMIN_RE`), traduz novos e registra em `textos_novos.txt`.
- `config.py` — dados do usuário em `%APPDATA%\RuneteriaTradutor` (config.json, glossário, memória, erros.log).

## Convenções de tradução
Nomes próprios ficam em inglês (classes Warrior/Mage/Rogue/Priest, skills, itens, Hollow Crypt, Rune Coins,
raças como Kweeborn, Battle Master, Race Change Token, títulos de músicas). UI genérica é traduzida.
Termos de jogo que o jogador brasileiro usa em inglês ficam em inglês: Hotbar, loot, Lootbag, drop, boss, World Boss,
buff, mob, NPC, HP, XP, PvP, tier, rank, pet, crafting, stamina, homestead (nunca "barra quente", "chefe", "PV").
Traduzidos: quest→missão, bag→bolsa, slot→espaço, stall→banca, dungeon→masmorra, party→grupo, cooldown→recarga.
A lista vale também para a tradução automática: `termos_fixos` em `data/glossario.json` (`mt._protect` troca o termo
por marcador e `_agree` acerta artigo/possessivo). Ao mudar um termo, mude na biblioteca e no glossário.
Profissões/bancadas traduzidas nos textos de maestria (Sawmill→Serraria, Tannery→Curtume, Loom→Tear, Smelter→Fundição).
Labels com `RenderUppercase` aparecem em MAIÚSCULAS no OCR — a biblioteca compara sem diferenciar caixa.

## Resoluções e escala do Windows
Nada pode depender de 1920x1080. Medido com capturas redimensionadas (1280 a 3840): o overlay mantém altura x1,00,
largura x1,00 e desvio 0 px. Regras: `escala_ocr: "auto"` (`ocr_engine.auto_scale`: alvo ~15,5 px de texto depois de
ampliar, LANCZOS, 1x–3x; 0,75x em 4K) ajustada a cada leitura pela altura mediana do texto (`main.learn_text_size`);
leituras alternam escala x1/x1,2 e traduções ficam enquanto a região não muda (o OCR oscila entre escalas).
Distâncias em pixels são proporcionais à altura do texto (`style.free_room`, `guess_align`, `avail_width`).
Fonte do overlay nunca abaixo de 80% do original: se não cabe, fica o texto original (ilegível é pior que inglês).
Janela do tradutor: `theme.S()` aplica a escala do Windows (125%/150%), limitada à área útil da tela
(`RT_UI_SCALE` força um valor para teste). Monitor à esquerda (coordenadas negativas) funciona no tk e no mss.

## Linhas de tooltip/habilidade
`compose` devolve os trechos traduzidos por palavra; `Translator._span_boxes` cobre só esses trechos (mais separador,
tecla e número inteiro vizinhos: "530 dano · signature completa"). Valores com letra ("8.6s") e nomes ficam com os
pixels do jogo — o OCR erra esses ("8.65", "g.6s"). Título e subtítulo de card com cor diferente não viram parágrafo.
Título de card logo acima de linha que começa com número (`Translator._card_titles`) é nome de skill/item: fica em
inglês mesmo sendo palavra comum ("Hemorrhage"). Fileira de rótulos com vão grande entre eles (abas do topo que o OCR
juntou) vira uma caixa por rótulo (`_label_row`), nunca vai para a tradução automática. Memória automática `"v": 5`
(`library.MEMORY_VERSION`; subir quando o que foi gravado antes não presta mais: a memória passa na frente da online).
Nome com etiqueta logo abaixo ("DAMAGE" sobre "[DMG] - PVP & PVE", guilda) fica em inglês até contra a biblioteca.
Objetivo de missão "Verbo N Item" ("Mine 15 Rock Blocks") traduz só o verbo, com `verbos_de_objetivo` do glossário.
Trecho que só caberia com letra menor que a do resto da linha, ou que deixaria buraco, troca pela linha inteira (`alt`);
a família da fonte do trecho vem da linha inteira (`line_ref`). Em MAIÚSCULAS a altura ignora a cauda do Q (`ink_rows caps`).

## Atraso (feedback da beta)
O OCR roda num `ThreadPoolExecutor` (`App.read_screen`): enquanto lê, o laço segue conferindo as regiões a cada
0,15 s (tradução velha sai em ~0,1 s ao trocar de aba). O resultado só entra para as regiões que não mudaram durante
a leitura. Alt+Tab: `pump` confere o foco a cada 40 ms e esconde na hora; os slots ficam guardados e voltam em ~0,1 s.
Texto que sai da tela menos de 2,5 s depois de aparecer, 3 vezes em 20 s (texto no cenário 3D), fica 30 s sem
tradução (`_note_drops`/`_flaky`). Medir com o jogo simulado (`App` com `w.grab_window` devolvendo capturas).
Leitor de tela: se instalou mas o processo não enxerga, reabre o app (`restart`, `--reiniciar`); se falhou, abre
Configurações > Idioma (`ocr_by_settings`). Log do Windows em `instalar_leitor.log`.
Nome do glossário lido com erro pelo OCR ("EVE' RR@OT FOREST") fica em inglês (`Translator._garbled_name`).

## Tradução online e chat
`servidor/worker.js` (Cloudflare Worker + DeepL, ver `servidor/LEIAME.md`) traduz o que não está na biblioteca e guarda
numa memória compartilhada (KV + Cache API). App: `online_mt.OnlineMT` (marcadores `<k>Z0</k>`, números `<k>N0</k>`
para "Level 10"/"Level 11" serem um texto só); `mt._backend` usa o servidor e cai na offline; opção na janela só aparece
com `config.ONLINE_MT_URL`. Flags por texto: True = tela (guarda), False = chat (só cache 1 h), "offline" = nunca vai.
Servidor limita por dia, por IP (cifrado) e reserva a cota: >80% do mês o chat fica na offline.
Chat (`pipeline.chat_split`): traduz só a mensagem, vai para a fila na hora; português (`looks_portuguese`) e gírias
(`chat_girias` do glossário) não gastam nada; mensagem de até 3 palavras vai só para a offline.
"Nome + frase da biblioteca" (`Translator._name_then_phrase`: "Kwaxu has joined") traduz só a frase.
Chat só com o cursor visível (chat aberto) e só a mensagem sob o mouse (`Translator.pointer`, `_chat_blocks` junta as
linhas de continuação; caixas `chat: True` somem do slot quando o mouse sai). `chat_ao_passar_o_mouse` no config.
Memória compartilhada: `.github/workflows/memoria.yml` roda `tools/baixar_memoria.py` todo dia (segredo
`TRADUTOR_ADMIN` = ADMIN_TOKEN do servidor) e grava `app/data/compartilhada.json` ({texto protegido: tradução});
o app sincroniza como a biblioteca e consulta antes do servidor (`online_mt.from_shared`), mesmo offline.
O servidor aceita texto de qualquer um (código público): `baixar_memoria.good`/`game_text` só deixam entrar texto com
cara de tela do jogo (sem link, só inglês) e no máximo 500 novos por dia. Endereço do servidor:
`https://tradutor-runeteria.translator-runeteria.workers.dev`.

## Tela parada não pisca nem muda (`App.settle`)
Cada lugar da tela é um "slot" que guarda a tradução até os pixels do jogo ali mudarem (`region_changed`). Leitura
nova só troca se for mais completa, se o mesmo texto couber numa caixa bem mais estreita, ou se discordar 3 leituras
seguidas. Fonte e cor ficam memorizadas por slot (`stable_face`/`stable_colors`). Medir com 8 leituras da mesma
captura: nada deve piscar nem trocar de texto/lugar/fonte/cor (só a troca única por leitura mais completa).

## Usuário final é leigo
Quem usa não é técnico: instalar e usar tem que ser quase um clique. Nada de pedir PowerShell, editar JSON ou ler log
para o fluxo normal. Cada problema aparece na janela em linguagem simples, com um botão que resolve
(ex.: linha "Leitor de tela" → botão Instalar chama `winutil.install_english_ocr`, que abre o UAC).

## Janela do app (Runeteria Design System)
`theme.py` tem os tokens do "Runeteria Design System" (artifact do dono no claude.ai, UI KIT V2): rampa navy base-bg,
dourado primary como único destaque, cantos de 4–6 px, filete dourado com losango, rótulos de botão/seção em MAIÚSCULAS.
Fontes em `app/fonts` (OFL, carregadas só para o processo): Cormorant (título), Lexend (botões/rótulos), Inter (texto).
Sem emoji. Marca: logos oficiais do Runeteria em `app/assets` (logo completo no cabeçalho, "R" dourado no ícone);
`tools/gerar_icone.py <pasta dos logos>` regenera `icone.ico` e as imagens. Não usar cores fora dos tokens.
`main._build_window` monta a janela; `refresh_status` decide a frase de estado e as linhas de "Preparação".
Só um botão de ação além de Ligar/Desligar: "Verificar atualizações" (`main.check_updates`: recarrega correções do
usuário, baixa biblioteca/glossário do GitHub, avisa de versão nova, procura telas novas no cache). Não adicionar
botões técnicos (pasta, recarregar, telas novas): o usuário é leigo.

## Internet (opcional, desligável)
`online.py` só lê do GitHub (`Toshiharo/tradutor-runeteria`): `app/data/biblioteca.json` e `glossario.json` do branch
main (com ETag, validados, gravados em `%APPDATA%\RuneteriaTradutor\online`) e a tag da última release para avisar de
versão nova. Nunca envia dados. Corrigir uma tradução = commit no main; os jogadores recebem ao abrir o app.
Versão: `config.APP_VERSION` (o build passa para o instalador); publicar = release com tag `vX.Y.Z` e o instalador anexado.

## Build
`build.bat`: cria `.venv`, instala `requirements.txt` + pyinstaller, roda `baixar_modelo.py` (Argos en_pt 1.9 → `modelos/en_pt`),
gera `dist\TradutorRuneteria\` (onedir, windowed) e, com o Inno Setup 6 instalado, `dist\TradutorRuneteria-Instalar.exe`
(`instalador.iss`: por usuário, sem administrador, atalhos, opção de abrir com o Windows).
