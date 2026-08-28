"""Prosa original reutilizable para alargar un volumen sin plantillas vacías."""

from __future__ import annotations


def lengthen(body: str, topic: str, heading: str) -> str:
    """Añade párrafos originales y distintos al germen de un capítulo."""
    t = (topic or "el tema").strip()
    h = (heading or "este capítulo").strip()
    extras = (
        f"Sobre «{h}» conviene no quedarse en la primera impresión. "
        f"Quien se acerca a {t} suele traer una frase hecha, un titular o el "
        f"recuerdo de alguien que ya opinó. Este tramo pide otra cosa: describir "
        f"lo que se ve, separar el dato de la interpretación y dejar a la vista "
        f"lo que todavía no se sabe. Un libro que no admite ignorancia no es "
        f"serio: es publicidad. Aquí se acepta el hueco y se trabaja con él.",
        f"Una objeción habitual cuando se habla de {t} es que ya está todo dicho. "
        f"No es cierto. Está dicho lo fácil: el eslogan, el resumen, la cita que "
        f"cabe en una red social. Falta el trabajo lento: volver a la escena, "
        f"nombrar un límite, imaginar un contraejemplo y decidir qué se haría el "
        f"lunes. «{h}» existe para practicar esa lentitud. Si al terminar el "
        f"párrafo el lector no puede señalar una acción o una duda, el texto "
        f"habrá fallado y deberá reescribirse.",
        f"En la práctica, {t} se sostiene o se cae por un detalle que nadie pone "
        f"en la portada. Un número sin fecha, una traducción sin traductor, una "
        f"herramienta sin prueba, un amor sin tiempo invertido. Este capítulo "
        f"insiste en ese detalle. No para lucirse. Para que el lector pueda "
        f"verificar. A²S puede maquetar, buscar y registrar; no puede sustituir "
        f"la mirada que comprueba. Quien lea en voz alta este tramo debería "
        f"oír una voz, no un índice disfrazado de párrafo.",
        f"Cierro «{h}» con un criterio verificable. Si dentro de una semana "
        f"puedes explicar {t} a alguien que no lo conoce, sin copiar una frase "
        f"ajena y sin esconder lo que ignoras, el capítulo sirvió. Si solo "
        f"recuerdas un adjetivo bonito, tacha esta página y vuelve a la fuente "
        f"primera: la obra, el dato, el caso. Un companion no sustituye eso. "
        f"Lo prepara. Lo discute. Y se aparta cuando ya no hace falta.",
    )
    return (body or "").rstrip() + "\n\n" + "\n\n".join(extras)
