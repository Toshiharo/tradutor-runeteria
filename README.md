# Tradutor Runeteria

As telas do servidor **Runeteria** (Hytale) em português do Brasil. O programa lê o texto da tela do jogo e desenha a tradução por cima, com a mesma fonte, cor, tamanho e posição do texto original: inventário, missões, lojas, guilda, classes, habilidades, tooltips e o resto da interface.

Precisa do **Windows 10 ou 11** (64 bits). O instalador tem cerca de 100 MB.

> [!WARNING]
> **Versão beta, ainda em testes.** Algumas traduções podem sair erradas ou ficar em inglês, e textos longos (descrições de missão, avisos) são traduzidos automaticamente e podem sair estranhos. Se achar um problema, avise em uma [issue](https://github.com/Toshiharo/tradutor-runeteria/issues) ou no Discord do Runeteria. Se atrapalhar, aperte **F8** para desligar a tradução na hora.

## Instalar

1. Baixe o **TradutorRuneteria-Instalar.exe** na página de [versões](https://github.com/Toshiharo/tradutor-runeteria/releases/latest).
2. Abra o arquivo baixado.
3. O Windows vai mostrar **"O Windows protegeu o computador"**. Clique em **Mais informações** e depois em **Executar assim mesmo**.
4. Clique em **Instalar**. Não precisa de senha de administrador.
5. O tradutor abre sozinho no final, e fica um atalho na área de trabalho.

### Por que aparece o aviso do Windows?

O Windows mostra esse aviso para todo programa que não tem uma assinatura digital paga da Microsoft. Ele não quer dizer que o programa tem vírus. O código do tradutor é aberto e está todo neste repositório.

Baixe sempre pelo link oficial acima. Se pegou o arquivo de outro lugar, não abra.

## Primeira vez

Quando o tradutor abrir, olhe a parte **Preparação** da janela:

- **Leitor de tela vermelho ou amarelo:** clique em **Instalar** ao lado dele e aceite o pedido do Windows. Isso instala o leitor de texto em inglês do próprio Windows e leva cerca de um minuto. Só é preciso fazer uma vez.
- **Tudo verde:** está pronto.

## Usar

1. Abra o **Tradutor Runeteria**.
2. Abra o Hytale e entre em `play.runeteria.com`.
3. A tradução aparece por cima das telas do jogo.

Deixe o jogo em **Janela** ou **Tela cheia sem borda**: em tela cheia exclusiva a tradução não aparece. O tradutor liga sozinho com o jogo aberto. Ele foi feito para as telas do Runeteria: fora dele também tenta traduzir o que aparece, mas as traduções revisadas são só as do Runeteria.

| Atalho | O que faz |
| --- | --- |
| F8 | Liga ou desliga a tradução |
| F9 | Mostra o texto original |
| F10 | Salva os textos da tela em um arquivo, para corrigir uma tradução |

Na janela do tradutor dá para ligar **Abrir junto com o Windows**, para ele já estar pronto quando você entrar no jogo.

## Atualizações

Clique em **Verificar atualizações** na janela do tradutor. Ele baixa as traduções corrigidas e avisa quando sai uma versão nova do programa; nesse caso, clique em **Atualizar**: o tradutor baixa a versão nova, instala sozinho e abre de novo (a partir da versão 1.1.3; nas anteriores, baixe o instalador e instale por cima).

## Problemas comuns

**A tradução não aparece**
- Confira se o jogo está em Janela ou Tela cheia sem borda.
- Confira se você está dentro do `play.runeteria.com`. A janela do tradutor mostra "Traduzindo" quando está tudo certo.
- Aperte **F8**: a tradução pode ter sido desligada.

**Algum texto continua em inglês**
- Nomes de skills, itens, montarias, masmorras e jogadores ficam em inglês de propósito.
- Termos que o jogador brasileiro usa em inglês também ficam: Hotbar, loot, boss, buff, HP, XP, tier, rank, pet.
- Rótulos muito curtos cuja tradução não cabe no espaço ficam em inglês para não ficarem ilegíveis.
- Texto que o tradutor nunca viu é traduzido automaticamente em poucos segundos e aparece em *itálico*.

**O antivírus reclamou**
- Programas novos e sem assinatura às vezes são barrados por engano. Baixe só pelo link oficial e, se precisar, adicione uma exceção no antivírus.

## Desinstalar

Configurações do Windows > Aplicativos > **Tradutor Runeteria** > Desinstalar. Suas correções ficam em `%APPDATA%\RuneteriaTradutor`; apague a pasta se quiser remover tudo.

## Como funciona e privacidade

- Não mexe no jogo: só lê a tela e os arquivos de registro do Hytale.
- A tradução funciona sem internet. A internet é usada para baixar traduções novas deste repositório, saber se saiu versão nova e, com a **Tradução online** ligada, traduzir texto que ainda não está na biblioteca. Cada uma dessas opções pode ser desligada na janela.
- Com a Tradução online ligada, o texto em inglês do jogo que o tradutor não conhece (e, se você ligar a opção **Traduzir o chat (não recomendado)**, a mensagem do chat sob o mouse) é enviado ao servidor do projeto, que traduz com o DeepL. As traduções de telas ficam guardadas para os outros jogadores; mensagens de chat não são guardadas. Nada do seu computador é enviado e nem o seu nome nem o seu IP são gravados (o IP só é usado, cifrado, para limitar o uso por dia). Com a opção desligada, nada sai do seu computador.
- As traduções vêm de uma biblioteca com mais de 2.700 textos revisados à mão ([`app/data/biblioteca.json`](app/data/biblioteca.json)).

## Ajudar com as traduções

Achou uma tradução errada? Abra uma [issue](https://github.com/Toshiharo/tradutor-runeteria/issues) com o texto em inglês e a tradução certa, ou envie um pull request alterando `app/data/biblioteca.json`. Quem tem o programa instalado recebe a correção ao clicar em **Verificar atualizações**.

## Gerar o programa a partir do código

Precisa do Windows 10 ou 11 e do Python 3.12. Rode `build.bat`: ele cria o ambiente, baixa o modelo de tradução offline e gera `dist\TradutorRuneteria\`. Com o [Inno Setup](https://jrsoftware.org/isinfo.php) instalado, gera também `dist\TradutorRuneteria-Instalar.exe`.

Testes: `.venv\Scripts\python.exe -m unittest discover -s tests`

---

Feito por Toshi, da equipe de UI/UX do Runeteria, com autorização do dono do servidor. Não é um produto oficial do Hytale.
