"""Montants en toutes lettres (français), pour les bulletins de salaire et reçus."""

_UNITS = ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix", "onze", "douze",
          "treize", "quatorze", "quinze", "seize", "dix-sept", "dix-huit", "dix-neuf"]
_TENS = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante"}


def _below_100(n):
    if n < 20:
        return _UNITS[n]
    tens, unit = divmod(n, 10)
    if tens in (7, 9):
        base = "soixante" if tens == 7 else "quatre-vingt"
        rest = 10 + unit
        if tens == 7 and unit == 1:
            return "soixante et onze"
        return f"{base}-{_UNITS[rest]}"
    if tens == 8:
        return "quatre-vingts" if unit == 0 else f"quatre-vingt-{_UNITS[unit]}"
    word = _TENS[tens]
    if unit == 0:
        return word
    if unit == 1:
        return f"{word} et un"
    return f"{word}-{_UNITS[unit]}"


def _below_1000(n):
    hundreds, rest = divmod(n, 100)
    parts = []
    if hundreds:
        if hundreds == 1:
            parts.append("cent")
        else:
            parts.append(f"{_UNITS[hundreds]} cent" + ("s" if rest == 0 else ""))
    if rest:
        parts.append(_below_100(rest))
    return " ".join(parts) if parts else "zéro"


def en_lettres(value):
    """1 250 500 → « un million deux cent cinquante mille cinq cents »."""
    n = int(round(float(value)))
    if n == 0:
        return "zéro"
    if n < 0:
        return "moins " + en_lettres(-n)
    words = []
    for size, singular, plural in ((10 ** 9, "milliard", "milliards"), (10 ** 6, "million", "millions")):
        count, n = divmod(n, size)
        if count:
            words.append(f"{_below_1000(count)} {singular if count == 1 else plural}")
    thousands, n = divmod(n, 1000)
    if thousands:
        words.append("mille" if thousands == 1 else f"{_below_1000(thousands)} mille".replace("cents mille", "cent mille"))
    if n:
        words.append(_below_1000(n))
    return " ".join(words)
