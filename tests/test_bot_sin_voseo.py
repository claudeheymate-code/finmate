"""El bot de WhatsApp tutea (español de Chile): sin voseo en sus textos."""
import pathlib
import re

VOSEO = re.compile(
    r"(?<![\wáéíóúñ])(Sos|podés|Podés|tenés|Tenés|querés|Querés|Probá|probá|Decime|decime|"
    r"mostrame|Mostrame|agregá|Agregá|avisame|Avisale|seguí|Seguí|Escribime|Pedime|usá|"
    r"hablás|contás|ajustá|jugá|desarrollá|Respondé|respondé|Elegí|Contame|Fijate|acá)(?![\wáéíóúñ])"
)
CARPETAS = ["finmate/agent", "finmate/alerts", "finmate/podcasts", "finmate/whatsapp"]


def test_bot_sin_voseo():
    raiz = pathlib.Path(__file__).resolve().parents[1]
    hallazgos = []
    for carpeta in CARPETAS:
        for p in (raiz / carpeta).rglob("*.py"):
            for i, linea in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                # Ejemplos de lo que el usuario puede escribir (p. ej. 'mostrame') se permiten.
                if "mostrame'" in linea or "'mostrame" in linea:
                    continue
                # La instrucción del system prompt que prohíbe el voseo los nombra entre comillas.
                if "voseo" in linea or '"decime"' in linea:
                    continue
                if VOSEO.search(linea):
                    hallazgos.append(f"{p.relative_to(raiz)}:{i}: {linea.strip()}")
    assert not hallazgos, "Voseo en textos del bot:\n" + "\n".join(hallazgos)
