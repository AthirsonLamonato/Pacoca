"""Cheap hints avoid an extra model pass for ordinary conversation.

Hints never grant permission or execute text; tool calls still use validated schemas.
"""
import re
import unicodedata


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFD',text.casefold()) if unicodedata.category(c)!='Mn')


def needs_tools(text):
    return bool(re.search(r'\b(abre|abra|abrir|feche|fecha|clique|digite|leia|liste|consulte|busque|pesquise|salve|crie|guarde|esqueca|lembre|volume|horas?|ram|cpu|windows|computador|arquivos?|documentos?|pastas?|janelas?|aplicativos?|programas?|memorias?|lembretes?|spotify|valorant|counter.strike|cs2?|toca|toque|pausa|pause|musicas?)\b|https?://',normalized(text)))
