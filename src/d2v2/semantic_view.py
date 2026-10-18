"""Shared model-only view; leave executable text and rule detection unchanged."""
import re
import unicodedata
from .normalization import HOMOGLYPHS, GREEK

_WORDS = re.compile(r'\w+', re.UNICODE)


def letter_scripts(word):
    """Only scripts with registered visual confusables affect folding."""
    return {name.split(' ', 1)[0] for c in word
            if (name := unicodedata.name(c, '')).startswith(('LATIN ', 'CYRILLIC ', 'GREEK '))}


def _invisible(c):
    cp = ord(c)
    return (unicodedata.category(c) in ('Cf', 'Cs')
            or (unicodedata.category(c) == 'Cc' and c not in '\n\r\t')
            or cp in (0x034F, 0x115F, 0x1160, 0x3164, 0xFFA0)
            or 0xFE00 <= cp <= 0xFE0F or 0xE0100 <= cp <= 0xE01EF)


def semantic_view(raw):
    text = ''.join(c for c in unicodedata.normalize('NFKC', raw) if not _invisible(c))
    def fold(match):
        word = match.group()
        return word.translate(HOMOGLYPHS).translate(GREEK) if len(letter_scripts(word)) > 1 else word
    return _WORDS.sub(fold, text)


def mixed_word_statistics(texts):
    words = [w for text in texts for w in _WORDS.findall(text) if any(c.isalpha() for c in w)]
    mixed = sum(len(letter_scripts(w)) > 1 for w in words)
    return {'words':len(words),'mixed_words':mixed,'fraction':mixed/len(words) if words else 0.,
            'definition':'Unicode word with letters; mixed means at least two of Latin/Cyrillic/Greek. CJK orthography is preserved.'}
