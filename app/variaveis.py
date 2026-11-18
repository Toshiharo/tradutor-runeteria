"""Partes variaveis do texto do jogo: valores, nomes proprios e nomes de jogador.

Usado pelo pipeline para:
- nao traduzir nomes (skills, itens, montarias, masmorras, jogadores) - eles ficam em ingles;
- montar a traducao de linhas de tooltip por partes ("Armor 15 Vitality +7");
- proteger os nomes dentro de frases antes de mandar para a traducao automatica.
Sem dependencia do Windows: testavel em tests/test_variaveis.py.
"""
import re

WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")
SEP_RE = re.compile(r"(\s*[•·|]\s*)")  # separadores de tooltip: "143 damage • 7.7s • 32"

# palavras que nao aparecem em nome proprio: com elas, e frase ou rotulo de interface
FUNC = {"a", "an", "and", "or", "to", "for", "in", "on", "at", "by", "with", "from", "your", "you", "my",
        "our", "not", "no", "all", "is", "are", "be", "this", "that", "these", "it", "its", "more", "less",
        "per", "than", "up", "out", "off", "into", "if", "when", "then", "here", "there", "now", "new",
        "can", "will", "has", "have", "get", "use", "each", "every", "any", "some", "only", "yet"}
NAME_JOIN = {"of", "the", "de"}  # podem aparecer no meio de nome ("Aegis of Faith", "The Deepworks")

_VALUE_RE = re.compile(r"""^(
      [+\-−~]?\(?[+\-−]?\d[\d.,:/%\-]*\)?(?:[a-zA-Z]{1,2}\b)?\.{0,3}   # 143  +7  7.7s  1-22%  (1-6%)  4/4  18:12  32...
    | \(?[+\-−]?\d[\d.,%\-]*%?\)?
    | (?:lv|nv|lvl)\.?\s?\d+                                         # Lv.20
    | x\d+ | \d+x                                                    # x3  3x
    | \.{2,} | [#/\-+×:=()\[\]]+
)$""", re.X | re.I)


def is_value_token(tok):
    """Pedaco que nao se traduz: numero, porcentagem, intervalo, tempo, nivel, tecla (Q, E, R)."""
    t = tok.strip()
    if not t:
        return True
    if len(t) == 1 and t.isupper():
        return True  # tecla de atalho
    return bool(_VALUE_RE.match(t))


def only_values(text):
    return all(is_value_token(t) for t in text.split())


def _has_fixed_term(low, fixed_terms):
    return any(re.search(r"(?<![\w])" + re.escape(t) + r"(?![\w])", low) for t in fixed_terms)


def is_name_phrase(text, fixed_terms=(), unknown_word=None):
    """O texto inteiro e um nome proprio? (skill, item, montaria, masmorra, regiao, jogador)

    - 2 a 5 palavras, todas com inicial maiuscula ("Precision Strike", "Epic Gatherer's Vest",
      "The Deepworks"), sem palavras de frase (to, your, not...) -> nome.
    - 1 palavra: nome so se o modelo de traducao nao conhece a palavra (Boomshroom, Velcorne).
    - TUDO EM MAIUSCULAS nao conta: e o jeito do jogo escrever botoes e titulos.
    - Contem um termo de jogo que tem traducao fixa (slot, quest, bag...) -> nao e nome, e rotulo.
    """
    t = text.strip()
    words = WORD_RE.findall(t)
    if not words or len(words) > 5 or t.isupper():
        return False
    if re.search(r"[.!?:]$", t) or re.search(r"[\d()\[\]]", t):  # "Agility (Scaling)" e rotulo
        return False
    if any(w.lower() in FUNC for w in words):
        return False
    caps = [w for w in words if w.lower() not in NAME_JOIN]
    if not caps or not all(w[0].isupper() for w in caps):
        return False
    if words[0].lower() in NAME_JOIN and words[0] != "The":
        return False
    if _has_fixed_term(t.lower(), fixed_terms):
        return False
    if len(caps) >= 2 or words[0] == "The":  # "The Deepworks", "The Hollow": nome de lugar
        return True
    return bool(unknown_word and unknown_word(caps[0]))


def is_noise(text, unknown_word=None):
    """Lixo que nao vale traduzir: nome de jogador solto no chat ("honkdaddy"), apelido com numero."""
    t = text.strip()
    if " " in t:
        return False
    if re.search(r"[A-Za-z]", t) and re.search(r"\d", t) and not is_value_token(t):
        return True  # Ver0420, xX_Pro99
    return bool(t.islower() and unknown_word and unknown_word(t))


def find_names(text, fixed_terms=(), unknown_word=None):
    """Nomes dentro de uma frase, para proteger antes da traducao automatica.

    - sequencias de 2+ palavras com inicial maiuscula ("cast Shadow Dance on", "Halloween Demonic Warhorse");
    - palavra com inicial maiuscula que o modelo nao conhece (Velcorne, Adamantite), fora do inicio da frase;
    - apelidos: palavra com numero ou sublinhado (Ver0420, _Toshi).
    """
    names = []
    tokens = text.split()
    i = 0
    while i < len(tokens):
        core = tokens[i].strip(".,;:!?()[]\"")
        if core[:1].isupper() and not core.isupper() and core.lower() not in FUNC and not re.search(r"[\d_]", core):
            j = i + 1
            run = [core]
            while j < len(tokens):
                nxt = tokens[j].strip(".,;:!?()[]\"")
                if re.search(r"[\d_]", nxt):
                    break  # apelido (Ver0420, _Toshi) e tratado sozinho, nao gruda no nome do lado
                if (nxt[:1].isupper() and not nxt.isupper()) or (nxt.lower() in NAME_JOIN and j + 1 < len(tokens)
                                                                  and tokens[j + 1][:1].isupper()):
                    run.append(nxt)
                    j += 1
                    if not tokens[j - 1].rstrip().endswith((",", ".", ";", ":")):
                        continue
                break
            while run and run[-1].lower() in NAME_JOIN:
                run.pop()
            # no comeco da frase toda palavra ja vem com maiuscula: "Cast Shadow Dance" -> o verbo nao e nome
            sentence_start = i == 0 or tokens[i - 1].rstrip().endswith((".", "!", "?", ":"))
            if sentence_start and len(run) >= 3 and not (unknown_word and unknown_word(run[0])):
                run = run[1:]
                i += 1
            phrase = " ".join(run)
            if len(run) >= 2 and not _has_fixed_term(phrase.lower(), fixed_terms) and \
                    not any(w.lower() in FUNC for w in run):
                names.append(phrase)
                i = j
                continue
            if i > 0 and unknown_word and len(core) >= 5 and unknown_word(core) and \
                    not _has_fixed_term(core.lower(), fixed_terms):
                names.append(core)
        if ("_" in core or (re.search(r"\d", core) and re.search(r"[A-Za-z]", core))) and not is_value_token(core):
            names.append(core)
        i += 1
    out = []
    for n in names:
        if n and n not in out:
            out.append(n)
    return out
