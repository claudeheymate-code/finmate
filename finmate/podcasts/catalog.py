"""Podcasts que Finmate sabe resumir. Para agregar uno nuevo basta con su
feed RSS público (casi todos los podcasts de Spotify lo tienen; se puede
encontrar con la búsqueda de Apple Podcasts, campo feedUrl)."""

PODCASTS = {
    "primer_click": {
        "name": "Primer Click (Diario Financiero)",
        "rss": "https://anchor.fm/s/713eaf3c/podcast/rss",
        # Episodios que se saltan (el especial sale en audio y en video:
        # resumimos solo uno).
        "skip_title_prefixes": ["Especial (video)"],
        "aliases": ["primer click", "primerclick", "df", "diario financiero"],
    },
}


def resolve(name: str):
    """Devuelve el id del podcast a partir de lo que diga el usuario."""
    n = (name or "").strip().lower()
    for pid, meta in PODCASTS.items():
        if n == pid or n == meta["name"].lower() or n in meta["aliases"]:
            return pid
        if any(a in n for a in meta["aliases"]):
            return pid
    return None
