# Tradutor Runeteria — contexto para o Claude Code

Responda sempre em português (pt-BR). Feito pelo dono (Windows) para ele e para ser
compartilhado com outros jogadores brasileiros. Todas as traduções são em português do Brasil (nunca pt-PT).

## O que é
App Windows que traduz para pt-BR as telas do servidor **Runeteria** (Hytale, `play.runeteria.com:5520`),
desenhando a tradução por cima da janela do jogo. Só funciona dentro do Runeteria. 100% offline.
O cliente do Hytale não aceita mods: o app só lê a tela, os logs e o cache. **Nunca modificar o cache do jogo.**

## Status
- Roda no Windows (2026-11-18): Python 3.12.10 em `.venv`, winrt 4.x, ctranslate2 4.9, mss 10, PyInstaller 6.22.
  OCR en-US instalado; modelo em `modelos/en_pt`; `dist\TradutorRuneteria\` gerado e abre sem erro.
- Verificado de verdade: OCR, tradução offline, biblioteca/fuzzy, lock no log real, atualizador no cache real, captura da janela.
- **Ainda não conferido a olho:** o overlay desenhado por cima do jogo em foco (posição, clique atravessando,
  `SetWindowDisplayAffinity`). O jogo precisa estar em janela / janela sem bordas (tela cheia exclusiva esconde o overlay).
- A tradução automática (Argos) é fraca em rótulos curtos e puxa para pt-PT; o que importa deve ir para `biblioteca.json`.

## Arquitetura (`app/`)
- `main.py` — janela de controle tkinter + overlay transparente click-through + thread de captura (mss) a cada ~0,8 s.
  Atalhos globais F8 liga/desliga, F9 mostra original, F10 salva `ultima_tela.txt`.
- `lock.py` — lê incrementalmente o `*_client.log` mais recente em `%APPDATA%\Hytale\UserData\Logs`.
  Classe `Session`: "Direct connecting to multiplayer server at X" define a sessão; "Referral: A -> B" e reconexões
  mantêm a sessão (o Runeteria transfere para sub-servidores por IP: 135.148.52.87, 40.160.66.98, 51.195.60.189);
  "Changing from Stage … to MainMenu/Exited" encerra. Ativo = sessão contém `runeteria.com` e estágio `InGame`.
- `ocr_engine.py` — OCR nativo do Windows (Windows.Media.Ocr via pacotes `winrt-*`), precisa do pacote OCR en-US.
- `pipeline.py` — agrupa linhas em parágrafos; biblioteca primeiro; desconhecidos vão para fila de tradução offline,
  mas só se passarem no filtro `looks_translatable` (descarta lixo de OCR do cenário) e ficarem ~1,5 s parados na tela.
  O que o modelo não traduz entra num cache negativo (`failed`) e não é tentado de novo na sessão.
- `style.py` — aparência do overlay (só PIL): `add_colors` tira da captura a cor de fundo/letra de cada linha e o
  espaço de fundo liso dos lados (`room_l`/`room_r`); `font_px` corrige o tamanho (caixa do OCR sem descendentes
  mede ~0,74 da fonte); `guess_align`/`block_align` decidem esquerda/centro. `main.draw` usa isso, detecta negrito
  comparando larguras e não redesenha se nada mudou. Tradução automática aparece em itálico.
  `usar_cores_da_tela: false` no config volta às cores fixas.
- `library.py` — prioridade: `minhas_traducoes.json` (usuário) > `data/biblioteca.json` (2.759 revisadas)
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

## Build
`build.bat`: cria `.venv`, instala `requirements.txt` + pyinstaller, roda `baixar_modelo.py` (Argos en_pt 1.9 → `modelos/en_pt`),
gera `dist\TradutorRuneteria\` (onedir, windowed).
