#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera docs/El_Principito_Dossier.pdf — dossier de lectura LEGÍTIMO.

Por qué no es el libro completo: El Principito (1943, Saint-Exupéry †1944)
sigue protegido en EE.UU. (hasta 2039) y Francia (~2044-45), y las
traducciones al español tienen derecho propio del traductor. Este dossier
sí es 100% legítimo: contenido original (síntesis, análisis, citas breves
atribuidas) + el estado de derechos por jurisdicción.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from pdf_min import MiniPDF  # noqa: E402

BLOQUES = [
    ("Bloque 1 · caps. 1-6 — El aviador y el cordero",
     "Un aviador sufre una avería en el Sahara. Un niño llegado de otro planeta "
     "le pide que le dibuje un cordero. El narrador recuerda su infancia: el "
     "dibujo de una boa que digiere un elefante, que los adultos confundían con "
     "un sombrero. Presentación del asteroide B-612 y de la amenaza silenciosa "
     "de los baobabs: las malas semillas hay que arrancarlas a tiempo, todos "
     "los días; es una lección de disciplina aplicada también a uno mismo."),
    ("Bloque 2 · caps. 7-9 — La rosa",
     "En su planeta, el principito cuida una rosa vanidosa y exigente que "
     "dice ser única. Entre el orgullo de ella y la inseguridad de él nace un "
     "malentendido; el principito decide viajar. En la despedida, la rosa "
     "reconoce que lo quiere y renuncia a la mascarilla de la vanidad: primer "
     "retrato del amor como vulnerabilidad aprendida tarde."),
    ("Bloque 3 · caps. 10-15 — Los seis planetas",
     "Antes de llegar a la Tierra visita seis asteroides, cada uno habitado "
     "por un adulto absurdo: un rey sin súbditos que solo da órdenes que se "
     "cumplen solas; un vanidoso que solo oye admiración; un bebedor que bebe "
     "para olvidar la vergüenza de beber; un hombre de negocios que cuenta "
     "estrellas para 'poseerlas'; un farolero fiel a una consigna agotadora "
     "(el único que no le parece ridículo: piensa en algo fuera de sí); y un "
     "geógrafo que nunca explora, y que le revela que las flores son efímeras."),
    ("Bloque 4 · caps. 16-19 — La Tierra y el zorro",
     "La Tierra le parece vacía y extraña: mucha gente, pocas raíces. Una "
     "serpiente le habla en acertijos. En un jardín descubre cinco mil rosas "
     "iguales a la suya y llora: creía ser rico con una flor única. Entonces "
     "aparece el zorro, que le pide ser domesticado: 'domesticar es crear "
     "lazos'. De él aprende el secreto del libro y la responsabilidad hacia "
     "lo domesticado, y descubre que su rosa es única por el tiempo que le "
     "ha dedicado, no por su especie."),
    ("Bloque 5 · caps. 20-26 — El pozo y la despedida",
     "Un guardagujeras ordena los viajes de la gente que corre sin saber "
     "hacia qué; un mercader vende píldoras que quitan la sed para 'ahorrar "
     "tiempo'. Con el aviador, el principito camina por el desierto y "
     "encuentran un pozo: el agua, dice, sabe a fiesta cuando se ha buscado. "
     "El aviador repara su avión justo cuando el niño, que lleva un año en "
     "la Tierra, prepara su regreso: la serpiente le ha prometido el atajo. "
     "La escena final — la picadura, el cuerpo que desaparece, la estrella "
     "que cae — es una despedida deliberadamente ambigua entre muerte y "
     "retorno al cielo."),
    ("Bloque 6 · cap. 27 — Epílogo",
     "Han pasado seis años: el aviador mira las estrellas y se pregunta dónde "
     "está el cordero, y si se lo habrá comido la caja o la flor. Cierra pidiendo "
     "al lector que observe el desierto y que avise si ve un cordero: la obra "
     "deja al lector custodio de algo frágil, exactamente como el principito "
     "dejó al zorro."),
]

CITAS = [
    "«Lo esencial es invisible a los ojos» — el zorro, cap. 21",
    "«Te vuelves responsable para siempre de lo que has domesticado» — el zorro, cap. 21",
    "«Todos los mayores han sido primero niños; pero pocos de ellos lo recuerdan» — dedicatoria",
]

DERECHOS = [
    ("Chile y países vida+70 (Berna)", "dominio público desde 2015 (autor murió en 1944)"),
    ("España (vida+80, fallecidos antes de 1987)", "dominio público desde 2025"),
    ("Estados Unidos (95 años desde publicación)", "protegido hasta el 1-1-2039"),
    ("Francia (prórrogas de guerra + 'Mort pour la France')", "protegido hasta ~2044-2045"),
    ("Traducciones al español", "derecho PROPIO del traductor: las ediciones corrientes siguen protegidas"),
]

TEMAS = [
    "La mirada del niño frente a la literalidad de los adultos: cada planeta "
    "visitado es una sátira de una obsesión adulta (poder, vanidad, adicción, "
    "posesión, rutina, abstracción).",
    "Domesticar = crear lazos: el valor no está en la cosa sino en el tiempo "
    "invertido; por eso la rosa del principito es única entre cinco mil iguales.",
    "Responsabilidad y pérdida: amar algo frágil obliga a cuidarlo y, algún día, "
    "a dejarlo ir; la despedida final es inseparable del afecto.",
    "Lo invisible pesa más: el agua que sabe a fiesta, la caja que contiene un "
    "cordero, la estrella que contiene una risa. La imaginación como forma de "
    "presencia.",
    "Crítica a la eficiencia vacía: el mercader de píldoras y el guardagujeras "
    "ahorran tiempo que nadie sabe usar; el farolero, en cambio, gasta la vida "
    "en algo que la ilumina.",
]


def main() -> int:
    p = MiniPDF("El Principito — Dossier de lectura (A²S, stdlib)")
    # portada
    p.spacer(140)
    p.para("El Principito", size=30, font="F2")
    p.para("Antoine de Saint-Exupéry · 1943", size=12, font="F3")
    p.spacer(20)
    p.para("DOSSIER DE LECTURA (no el libro completo)", size=15, font="F2")
    p.para("Síntesis por bloques, temas, citas breves y estado de derechos por "
           "jurisdicción. Contenido original de análisis; el texto íntegro de la "
           "obra NO se reproduce (ver página de derechos).", size=10.5)
    p.spacer(12)
    p.para("Generado con tools/pdf_min.py — motor PDF en Python stdlib puro, sin "
           "dependencias. A²S v1.8.0.", size=9, font="F3")

    p.h1("Por qué este dossier y no el libro completo")
    p.para("El Principito sigue bajo derechos de autor en jurisdicciones "
           "importantes: en Estados Unidos hasta el 1 de enero de 2039 (95 años "
           "desde su publicación en 1943) y en Francia, su país de origen, hasta "
           "aproximadamente 2044-2045 (prórrogas de guerra y la condición de "
           "'Mort pour la France' de su autor). Además, cada traducción al "
           "español tiene un derecho de autor propio del traductor, por lo que "
           "las ediciones en español que circulan siguen protegidas "
           "prácticamente en todas partes. Reproducir el libro completo en un "
           "PDF no sería legítimo desde este entorno, y una reconstrucción de "
           "memoria sería además infiel al texto. Lo que sí es legítimo — y es "
           "este documento — es el análisis propio, la síntesis y la cita breve "
           "atribuida. Para leer la obra: cualquier biblioteca pública o "
           "cualquiera de las ediciones en venta; en Chile y la mayoría de los "
           "países de vida+70 el texto original francés de 1943 es ya dominio "
           "público, y existen ediciones legítimas del original.")

    p.h1("Estado de derechos por jurisdicción")
    p.table(["jurisdicción", "estado del texto original (1943)"],
            [[a, b] for a, b in DERECHOS], [210, 285])

    p.h1("La obra en seis bloques")
    for titulo, texto in BLOQUES:
        p.h2(titulo)
        p.para(texto)

    p.h1("Tres citas esenciales (cita breve, atribuida)")
    for c in CITAS:
        p.bullet(c)

    p.h1("Temas para leerlo mejor")
    for t in TEMAS:
        p.bullet(t)

    p.h1("Ficha técnica")
    p.kv("Título original", "Le Petit Prince (1943), escrito en EE.UU. en francés")
    p.kv("Autor", "Antoine de Saint-Exupéry (Lyon, 1900 - mar Mediterráneo, 1944)")
    p.kv("Género", "cuento ilustrado por el propio autor; fábula filosófica")
    p.kv("Extensión", "27 capítulos breves; el libro más traducido de la literatura francesa")
    p.kv("Traducciones", "más de 500 idiomas y dialectos")
    p.spacer(8)
    p.para("Nota técnica: PDF generado con tools/gen_principito.py sobre "
           "tools/pdf_min.py (stdlib, ~200 líneas). Toda la pipeline de "
           "documentos del proyecto usa el mismo motor.", size=8.5, font="F3")

    os.makedirs("docs", exist_ok=True)
    out = os.path.join("docs", "El_Principito_Dossier.pdf")
    n = p.save(out)
    print(f"OK: {out} · {n} páginas · {os.path.getsize(out)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
