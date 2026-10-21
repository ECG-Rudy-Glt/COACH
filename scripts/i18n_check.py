"""Contrôle des traductions de l'interface : liste les textes de `app/static/app.js` qui n'ont pas de traduction dans `app/static/i18n/<langue>.json`.

    python scripts/i18n_check.py [en]        # code de sortie 1 s'il en manque

Le français est la langue source : tout littéral de `app.js` qui ressemble à du texte affiché (appel `__()`, enfant ou attribut de `h()`, table de libellés)
doit figurer dans le dictionnaire. Les littéraux techniques (classes CSS, styles, sélecteurs, méthodes HTTP…) sont écartés par `looks_like_text`.
Un nouveau littéral technique pris à tort pour du texte s'ajoute à `NOT_TEXT`.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOT_TEXT = {"use strict", "viewBox", "Escape", "PATCH", "GET", "POST", "PUT", "DELETE", "Enter", "INPUT", "Content-Type", "X-Lang", "serviceWorker", "PushManager",
            "Notification", "noopener noreferrer", "Aa", "{design}", "{pct}%", "{i},{kg}", "lang"}
CSS_START = ("sc-", "f-", "profile-", "bcard", "sess ", "msg ", "btn ", "card ", "stack ", "row ", "grow ", "opt ", "count ", "photo-", "iconbtn", "muted ", "translate",
             "width:", "display:", "border:", "padding:", "align-self", "font-weight", "outline", "text-align", "(")
UI_FILES = ("app.js", "stats.js")  # un nouvel écran écrit dans son propre fichier s'ajoute ici
FR_WORDS = re.compile(r"\b(le|la|les|des|une|vos|votre|pour|dans|avec|est)\b")


def literals(src: str) -> list[tuple[str, bool]]:
    """(texte, dans un appel `__()`) pour chaque littéral ; `${expr}` d'un gabarit devient `{nom}`."""
    out: list[tuple[str, bool]] = []
    i, n = 0, len(src)

    def name_of(expr: str) -> str:
        found = re.findall(r"[A-Za-z_]\w*", expr)
        return found[-1] if found else "x"

    def template(i: int) -> tuple[str, int]:
        buf: list[str] = []
        while i < n:
            c = src[i]
            if c == "\\":
                buf.append(src[i:i + 2]); i += 2; continue
            if c == "`":
                return "".join(buf), i + 1
            if c == "$" and src[i + 1] == "{":
                depth, j = 1, i + 2
                while j < n and depth:
                    if src[j] == "{":
                        depth += 1
                    elif src[j] == "}":
                        depth -= 1
                    elif src[j] == "`":
                        j = template(j + 1)[1] - 1
                    elif src[j] in "\"'":
                        q = src[j]; j += 1
                        while src[j] != q:
                            j += 2 if src[j] == "\\" else 1
                    j += 1
                buf.append("{" + name_of(src[i + 2:j - 1]) + "}"); i = j; continue
            buf.append(c); i += 1
        return "".join(buf), i

    while i < n:
        c = src[i]
        if c == "/" and src[i + 1] == "/":
            i = src.find("\n", i)
        elif c == "/" and src[i + 1] == "*":
            i = src.index("*/", i) + 2
        elif c in "\"'":
            j, buf = i + 1, []
            while src[j] != c:
                if src[j] == "\\":
                    buf.append(src[j:j + 2]); j += 2; continue
                buf.append(src[j]); j += 1
            out.append(("".join(buf), src[max(0, i - 6):i].rstrip().endswith("__("))); i = j + 1
        elif c == "`":
            text, j = template(i + 1)
            out.append((text, src[max(0, i - 6):i].rstrip().endswith("__("))); i = j
        elif c == "/" and re.search(r"[(,=:]\s*$", src[max(0, i - 3):i]):
            j = i + 1
            while src[j] != "/":
                j += 2 if src[j] == "\\" else 1
            i = j + 1
        else:
            i += 1
    return [(re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), t), w) for t, w in out]


def looks_like_text(text: str, wrapped: bool) -> bool:
    if text in NOT_TEXT or not re.search(r"[A-Za-zÀ-ÿ]{2}", text):
        return False
    if wrapped:
        return True
    if re.match(r"^(https?:|/|#|\.|\[|<|data:|M\d)", text) or text.startswith(CSS_START) or re.search(r"var\(--|;\s*[a-z-]+:", text):
        return False
    if re.fullmatch(r"[a-z0-9_.:\-\[\]=\"' ,>#*()+~!/{}]+", text) and not re.search(r"[À-ÿ]", text):
        return bool(re.search(r"[A-Za-z]{3,}\{?\w*\}? [A-Za-z{]", text)) and bool(FR_WORDS.search(text)) or text in ("plus court", "plus long", "trop facile", "trop dur")
    return True


def ui_keys() -> list[str]:
    seen: dict[str, None] = {}
    for name in UI_FILES:
        for text, wrapped in literals((ROOT / "app" / "static" / name).read_text(encoding="utf-8")):
            if looks_like_text(text, wrapped) and len(re.findall(r"[A-Za-zÀ-ÿ]", re.sub(r"\{\w+\}", "", text))) >= 4:  # « {n} min », « P {g} g » : identiques dans toutes les langues
                seen.setdefault(text)
    return list(seen)


def missing(lang: str = "en") -> list[str]:
    dictionary = json.loads((ROOT / "app" / "static" / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
    return [k for k in ui_keys() if k not in dictionary]


if __name__ == "__main__":
    lost = missing(sys.argv[1] if len(sys.argv) > 1 else "en")
    print("\n".join(lost) or "ok")
    sys.exit(1 if lost else 0)
