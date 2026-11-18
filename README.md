# Tradutor Runeteria

As telas do servidor **Runeteria** (Hytale) em português do Brasil. O programa lê o texto da tela do jogo e desenha a tradução por cima, com as mesmas cores e tamanho do texto original.

## Instalar

1. Baixe o **TradutorRuneteria-Instalar.exe** na página de [versões](https://github.com/Toshiharo/tradutor-runeteria/releases/latest).
2. Dê dois cliques nele e depois em **Instalar**. Não precisa de senha de administrador.
3. O tradutor abre sozinho no final.

O Windows pode mostrar o aviso "O Windows protegeu o computador", porque o programa não tem assinatura digital paga. Clique em **Mais informações** e depois em **Executar assim mesmo**.

## Usar

1. Abra o Tradutor Runeteria.
2. Abra o Hytale e entre em `play.runeteria.com`.
3. A tradução aparece por cima das telas do jogo.

Na primeira vez, clique em **Instalar** na linha "Leitor de tela" e aceite o pedido do Windows. Isso instala o leitor de texto em inglês do próprio Windows.

Deixe o jogo em **Janela** ou **Tela cheia sem borda**; em tela cheia exclusiva a tradução não aparece.

| Atalho | O que faz |
| --- | --- |
| F8 | Liga ou desliga a tradução |
| F9 | Mostra o texto original |
| F10 | Salva os textos da tela em um arquivo, para corrigir uma tradução |

## Como funciona

- Só funciona dentro do Runeteria. Em outro servidor ou no menu ele fica parado.
- Não mexe no jogo: só lê a tela e os arquivos de registro do Hytale.
- A tradução funciona sem internet. Com a opção "Buscar traduções novas na internet" ligada, ele baixa a lista de traduções mais nova deste repositório e avisa quando sai uma versão nova. Nada do seu computador é enviado.
- As traduções vêm de uma biblioteca com mais de 2.700 textos revisados à mão ([`app/data/biblioteca.json`](app/data/biblioteca.json)). O que não está nela é traduzido automaticamente e aparece em *itálico*.
- Termos de jogo ficam em inglês, como a gente fala: Hotbar, loot, boss, buff, HP, XP, tier, rank, pet.

## Ajudar com as traduções

Achou uma tradução errada? Abra uma [issue](https://github.com/Toshiharo/tradutor-runeteria/issues) com o texto em inglês e a tradução certa, ou envie um pull request alterando `app/data/biblioteca.json`. Quem tem o programa instalado recebe a correção na próxima vez que abrir.

## Gerar o programa a partir do código

Precisa do Windows 10 ou 11 e do Python 3.12. Rode `build.bat`: ele cria o ambiente, baixa o modelo de tradução offline e gera `dist\TradutorRuneteria\`. Com o [Inno Setup](https://jrsoftware.org/isinfo.php) instalado, gera também `dist\TradutorRuneteria-Instalar.exe`.

Feito por Toshi, da equipe de UI/UX do Runeteria, com autorização do dono do servidor. Não é um produto oficial do Hytale.
