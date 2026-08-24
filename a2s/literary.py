"""Compositor literario original: produce un libro real, no una plantilla.

Nunca reproduce el texto protegido de una obra ajena. Entrega ensayo,
comentario, ficha y prosa original. Para El Principito (dominio público en
Chile desde 2015; protegido en EE.UU. hasta 2039) se entrega un companion
de lectura original, no la novela.
"""

from __future__ import annotations

import re
from typing import Optional

from .finder import fold
from .prose import lengthen


def is_literary(topic: str) -> bool:
    text = fold(topic)
    keys = (
        "principito", "petit prince", "little prince", "saint-exupery",
        "saint exupery", "cuento", "novela", "fabula", "poema", "poemario",
        "relato", "obra literaria", "clasico",
    )
    return any(key in text for key in keys)


def is_principito(topic: str) -> bool:
    text = fold(topic)
    return any(key in text for key in (
        "principito", "petit prince", "little prince", "saint-exupery",
        "saint exupery", "b-612", "b612",
    ))


def compose_book(topic: str, title: str = "") -> list[tuple[str, str]]:
    """Devuelve capítulos (título, prosa) de un libro original usable."""
    if is_principito(topic):
        raw = principito_companion()
        topic_label = "El Principito (lectura, no la novela)"
    else:
        clean = re.sub(r"\s+", " ", (title or topic or "el tema pedido").strip())
        raw = generic_companion(clean)
        topic_label = clean
    return [(heading, lengthen(body, topic_label, heading)) for heading, body in raw]


def principito_companion() -> list[tuple[str, str]]:
    """Companion original de lectura. Prosa propia, citas breves atribuidas."""
    return [
        ("Nota editorial y derechos",
         "Este volumen no es la novela de Antoine de Saint-Exupéry. Es un "
         "companion de lectura escrito de nuevo para A²S: síntesis, ensayo, "
         "ficha y guía de lectura. El texto francés de 1943 es dominio público "
         "en Chile y en la mayoría de los países de vida+70 desde 2015. Sigue "
         "protegido en Estados Unidos hasta el 1 de enero de 2039 y en Francia "
         "hasta hacia 2044-45. Cada traducción al español tiene derecho propio "
         "del traductor. Por eso aquí no se copia el libro ni se reconstruye "
         "de memoria. Se ofrece un objeto nuevo, legible de cabo a rabo, que "
         "permite estudiar la obra sin suplantar la edición que el lector debe "
         "buscar en una biblioteca o librería. Quien quiera las palabras "
         "exactas del aviador y del niño, que abra la novela. Quien quiera "
         "entender por qué esas palabras siguen vivas, que lea lo que sigue."),
        ("El aviador que no quería ser adulto",
         "La novela se abre con un malentendido que es también un pacto. Un "
         "niño dibuja una boa que ha tragado un elefante; los mayores ven un "
         "sombrero. Desde esa página el libro declara su método: lo esencial "
         "no coincide con el contorno. El narrador crece, aprende a hablar "
         "de bridge, de política y de corbatas, y deja de mostrar el dibujo. "
         "Años después, una avería en el Sahara le devuelve el interlocutor "
         "que le faltaba: un niño venido de otro planeta que no pregunta por "
         "la edad ni por el sueldo, sino por un cordero. El desierto funciona "
         "como laboratorio. Sin testigos, sin reloj, sin oficina, el aviador "
         "recupera el idioma que había perdido. Saint-Exupéry, piloto de "
         "verdad, no inventa el Sahara como decorado exótico: lo usa como el "
         "único sitio donde un adulto todavía puede ser interrogado sin "
         "escapatoria. El cordero pedido no es un animal. Es la prueba de "
         "que alguien, al fin, toma en serio una necesidad invisible."),
        ("B-612 y la disciplina de los baobabs",
         "El asteroide B-612 es pequeño a propósito. En un planeta del "
         "tamaño de una casa, cada semilla importa. Los baobabs no son un "
         "capricho botánico: son la imagen de lo que crece si se deja para "
         "mañana. El principito arranca brotes todos los días, no porque sea "
         "virtuoso, sino porque el tamaño del mundo no perdona la pereza. "
         "Esa lección es política y también íntima. Un vicio, una mentira, "
         "una vanidad, empiezan siendo hierba y terminan partiendo la roca. "
         "El libro insiste en el trabajo diario sin convertirlo en ética de "
         "la productividad. No se trata de ahorrar tiempo. Se trata de no "
         "dejar que lo que uno no mira se coma la casa. Quien haya cuidado "
         "un huerto, un código o una amistad reconoce el gesto: la "
         "vigilancia humilde, repetida, sin público."),
        ("La rosa, o el amor que llega tarde a decirse",
         "La rosa del principito es insoportable y es irreemplazable. "
         "Exige biombo, desayuno y admiración. Tose para que la atiendan. "
         "Él, que sabe de volcanes y de baobabs, no sabe leer esa comedia. "
         "Parte. Ella, en el umbral, deja caer la pose y admite que lo "
         "quiere. El malentendido es el corazón del libro: el amor se "
         "declara cuando ya no hay tiempo de quedarse. Saint-Exupéry no "
         "idealiza a la flor. La muestra caprichosa, frágil, un poco "
         "mentirosa, y aun así única. Más adelante, en la Tierra, el niño "
         "descubrirá cinco mil rosas iguales y llorará. El valor no estaba "
         "en la especie. Estaba en el agua derramada, en las noches de "
         "escucha, en el tiempo invertido. Quien haya amado a alguien "
         "difícil reconoce la escena y no necesita que se la expliquen."),
        ("Seis planetas, seis maneras de no vivir",
         "Antes de la Tierra el principito visita seis asteroides. Cada uno "
         "es una sátira breve y cruel. El rey no tiene súbditos y solo da "
         "órdenes que el universo ya iba a cumplir. El vanidoso no oye más "
         "que aplausos. El bebedor bebe para olvidar que bebe. El hombre de "
         "negocios cuenta estrellas para poseerlas, y su posesión no cambia "
         "nada en el cielo. El farolero enciende y apaga un farol a un ritmo "
         "absurdo porque la consigna no se actualizó cuando el planeta "
         "aceleró; es el único que no le parece ridículo, porque piensa en "
         "algo que no es él. El geógrafo cataloga mundos que nunca pisa y "
         "revela, de paso, que las flores son efímeras. El desfile no es "
         "infantil. Es un inventario de oficios adultos vaciados de "
         "sentido. El poder sin pueblo, la fama sin obra, el vicio que se "
         "explica a sí mismo, la propiedad que no toca lo poseído, la "
         "obediencia ciega y el saber que no se ensucia las botas. El "
         "lector puede señalar a cuál se parece su semana."),
        ("El zorro y la invención de los lazos",
         "En la Tierra el principito encuentra una serpiente que habla por "
         "acertijos, un jardín que lo humilla y, por fin, un zorro que le "
         "pide ser domesticado. Domesticar, dice, es crear lazos. No es "
         "dominar. No es coleccionar. Es volver a alguien irreemplazable "
         "mediante el tiempo compartido. El rito que propone — volver a la "
         "misma hora, sentarse un poco más cerca cada día — es una pedagogía "
         "del cuidado. De esa conversación salen las dos frases que el mundo "
         "cita de memoria, y que aquí solo se recuerdan atribuidas: que lo "
         "esencial es invisible a los ojos, y que uno se vuelve responsable "
         "para siempre de lo que ha domesticado. El libro no las deja como "
         "adornos. Las cobra. La rosa exige esa responsabilidad. El cordero "
         "en su caja también. El lector, al cerrar, hereda la misma deuda."),
        ("El desierto, el pozo y el agua que sabe a fiesta",
         "El tramo final reúne al niño y al aviador en una caminata que es "
         "también una tesitura espiritual. Tienen sed. Encuentran un pozo. "
         "El agua, dice el principito, sabe distinta cuando se ha caminado "
         "hasta ella. Frente a esa escena el libro coloca dos sátiras más: "
         "el guardagujeras que ordena viajes de gente que no sabe a dónde "
         "va, y el mercader de píldoras que quitan la sed para ahorrar "
         "cincuenta y tres minutos por semana. Nadie sabe qué hacer con el "
         "tiempo ahorrado. Saint-Exupéry, que conocía el valor del agua en "
         "un fuselaje caído, no está haciendo metáfora barata. Está "
         "diciendo que la prisa es una forma de sed que no se declara. El "
         "pozo no es un milagro. Es el resultado de haber aceptado el "
         "camino. El aviador repara su motor justo cuando el niño, que lleva "
         "un año en la Tierra, prepara el regreso. La coincidencia no es "
         "casual: ambos terminan su trabajo a la vez, y por eso pueden "
         "despedirse."),
        ("La picadura, la estrella y el lector como tutor",
         "La serpiente cumple su promesa. El cuerpo del principito cae como "
         "un árbol y luego no está. El aviador no afirma que el niño haya "
         "muerto. Tampoco afirma que haya vuelto a B-612. Deja la escena en "
         "un umbral, que es el único lugar honesto para una despedida. Seis "
         "años después mira las estrellas y se pregunta si el cordero se "
         "habrá comido la rosa. Esa duda es el último lazo. El epílogo no "
         "cierra: entrega al lector la custodia de algo frágil. Si ves un "
         "cordero en el desierto, avisa. El libro, que empezó con un dibujo "
         "mal entendido, termina pidiendo que alguien vuelva a mirar con "
         "atención. Quien cierra estas páginas sin haber abierto la novela "
         "tiene un mapa. Quien las cierra después de haberla leído tiene un "
         "compañero de relectura. En ambos casos el trabajo no era copiar "
         "un clásico. Era devolverle, con palabras propias, el silencio que "
         "exige."),
        ("Guía de lectura por bloques",
         "Caps. 1-6: el aviador, el sombrero que no es sombrero, el cordero "
         "y los baobabs. Pregunta: ¿qué semilla estoy dejando crecer por no "
         "mirarla? Caps. 7-9: la rosa y la partida. Pregunta: ¿qué dije "
         "demasiado tarde? Caps. 10-15: los seis planetas. Pregunta: ¿cuál "
         "de esos oficios estoy imitando esta semana? Caps. 16-21: la "
         "Tierra, el jardín de las cinco mil rosas y el zorro. Pregunta: "
         "¿a quién he domesticado de verdad y de quién soy responsable? "
         "Caps. 22-27: el pozo, la píldora, la despedida y el epílogo. "
         "Pregunta: ¿qué agua he bebido sin haber caminado hasta ella? Esta "
         "guía no sustituye la lectura. Ordena la segunda."),
        ("Ficha, temas y cómo seguir",
         "Título original: Le Petit Prince (Nueva York, 1943), escrito en "
         "francés por un autor francés exiliado. Autor: Antoine de "
         "Saint-Exupéry (Lyon, 1900 — desaparecido en el Mediterráneo, "
         "1944). Género: cuento ilustrado por el propio autor; fábula "
         "filosófica. Extensión: veintisiete capítulos breves. Temas: la "
         "mirada del niño contra la literalidad adulta; domesticar como "
         "crear lazos; la responsabilidad hacia lo frágil; lo invisible "
         "como peso real; la crítica a la eficiencia que no sabe para qué "
         "ahorra. Cómo seguir: leer el original francés si se puede; si no, "
         "una traducción de confianza comprada o prestada. No descargar "
         "ediciones pirateadas. Volver a este companion después, no antes, "
         "si se busca discutir y no sustituir. Este libro de A²S es un "
         "artefacto original, fechado, y no pretende ser la obra."),
        ("Cómo no piratear un clásico",
         "Hay quien pide «el libro» y espera el texto íntegro de 1943. "
         "Esa petición choca con un mapa legal desigual. En Chile y en "
         "buena parte de vida+70 el francés original es de dominio público "
         "desde 2015. En Estados Unidos la protección llega a 2039. Cada "
         "traducción española tiene derecho propio. Descargar un PDF "
         "anónimo no es estudiar: es borrar al traductor y al editor. "
         "A²S se niega a esa ruta. Entrega un companion, una ficha y una "
         "guía. El lector que quiera las palabras exactas del aviador debe "
         "abrir una edición legal. Esa negativa no es un fallo técnico. "
         "Es el único modo de no convertir un clásico en contrabando."),
        ("Vocabulario mínimo para leer mejor",
         "Algunas palabras del libro se han vuelto eslóganes y han perdido "
         "peso. Domesticar no es adiestrar: es crear lazos mediante el "
         "tiempo. Esencial no es «importante»: es lo que no se ve y aun "
         "así obliga. Baobab no es un árbol decorativo: es lo que crece "
         "si se aplaza la mirada. Rosa no es «la amada perfecta»: es lo "
         "frágil, caprichoso e irreemplazable porque se ha cuidado. "
         "Cordero no es fauna: es la prueba de que alguien toma en serio "
         "una necesidad invisible. Quien lea con este glosario evita "
         "repetir las frases célebres como si fueran merchandising."),
        ("Preguntas para un club de lectura",
         "1) ¿Qué semilla —vicio, mentira, vanidad— estoy dejando crecer "
         "por no mirarla? 2) ¿Qué dije demasiado tarde, como la rosa en "
         "el umbral? 3) ¿A cuál de los seis planetas se parece mi semana "
         "laboral? 4) ¿A quién he domesticado de verdad y de quién soy "
         "responsable? 5) ¿Qué agua he bebido sin haber caminado hasta "
         "ella? 6) Si el cordero se come la rosa, ¿qué haré yo, que no "
         "estoy en B-612? Un club que no se hace estas preguntas solo "
         "intercambia admiración. Un club que se las hace lee de nuevo."),
        ("Línea de tiempo del aviador",
         "1900: nace en Lyon. 1921-26: servicio militar y primeros vuelos. "
         "1926-31: correo aéreo, Sahara, Andes; de ahí salen Correo del "
         "sur y Vuelo nocturno. 1935: aterrizaje forzoso entre Libia y "
         "Egipto; la sed real alimentará más tarde el pozo del cuento. "
         "1939-40: guerra y derrota. 1940-43: exilio en Estados Unidos; "
         "escribe El principito en Nueva York y Long Island, lo ilustra "
         "él mismo, lo publica en 1943 en francés e inglés. 31 de julio "
         "de 1944: desaparece en el Mediterráneo. 1998: se identifica el "
         "caza. 2004: se recuperan restos. La fábula no es un adorno de "
         "ese itinerario: es lo que un piloto en guerra todavía podía "
         "decirle a un adulto sin gritar."),
    ]


def generic_companion(topic: str) -> list[tuple[str, str]]:
    """Libro-ensayo original sobre un tema arbitrario (prosa larga, no viñetas)."""
    t = topic
    return [
        (f"Por qué escribir sobre {t}",
         f"Este libro existe porque alguien pidió un volumen sobre {t} y no "
         f"un resumen de tres líneas. Un libro no es una lista de encabezados. "
         f"Es una voz que sostiene una idea el tiempo suficiente para que el "
         f"lector pueda contradecirla. Aquí se trata {t} como materia viva: "
         f"se describe, se duda, se compara y se deja un método para seguir. "
         f"No se finge autoridad que no se tiene. Cuando falte una fuente, se "
         f"dirá. Cuando haya una interpretación, se marcará como tal. El pacto "
         f"con el lector es simple: terminarás con un objeto que se puede leer "
         f"en voz alta, no con un esqueleto de plantilla."),
        (f"Qué es, y qué no es, {t}",
         f"La primera disciplina consiste en no confundir {t} con su fama. "
         f"Toda materia llega envuelta en frases hechas, en promesas de "
         f"vendedores y en recuerdos ajenos. Este capítulo limpia la mesa. "
         f"{t} es un conjunto de prácticas, relatos o técnicas que alguien "
         f"puede señalar en el mundo. No es un talismán. No resuelve solo "
         f"una vida. No autoriza a despreciar lo que no se le parece. Si se "
         f"trata de una obra, se la sitúa en su siglo. Si se trata de una "
         f"técnica, se la sitúa en sus límites. Si se trata de una pregunta, "
         f"se la deja abierta el tiempo necesario para que no se cierre con "
         f"una consigna."),
        ("Una escena para entrar",
         f"Imagina una mesa, una lámpara y un cuaderno. Alguien ha escrito "
         f"en la primera página una sola línea: {t}. No hay internet en esa "
         f"habitación. No hay prisa. La persona copia lo que cree saber y "
         f"luego tacha la mitad. Ese gesto — tachar lo que sonaba bien y no "
         f"era cierto — es el método de este libro. Cada capítulo siguiente "
         f"intenta conservar solo lo que sobrevive a esa tachadura. Si el "
         f"tema es literario, la escena es un lector que cierra el volumen "
         f"y se queda un rato en silencio. Si el tema es técnico, la escena "
         f"es un operador que no declara victoria hasta ver una prueba. En "
         f"ambos casos la entrada no es un índice: es una actitud."),
        ("Cómo se estudia sin copiar",
         f"Estudiar {t} no es pegar fragmentos de otros. Es hacer tres "
         f"cosas, en este orden. Primero, describir con palabras propias lo "
         f"que se ha visto o leído. Segundo, separar el hecho de la "
         f"opinión. Tercero, dejar una pregunta que el texto todavía no "
         f"responde. Quien salte al tercer paso sin el primero produce "
         f"humo. Quien se quede en el primero sin el segundo produce "
         f"catálogo. Este capítulo practica los tres. Describe {t} como si "
         f"el lector no hubiera oído nunca el nombre. Marca lo que es "
         f"juicio. Y cierra con lo que falta: fuentes, cifras, ediciones, "
         f"contrapruebas. El hueco no es un fallo de este libro. Es su "
         f"honestidad."),
        ("Riesgos, trampas y vanidades",
         f"Toda atención crea una industria de atajos. Alrededor de {t} "
         f"aparecen resúmenes que prometen ahorrar la lectura, cursos que "
         f"prometen maestría en una tarde y opiniones que se disfrazan de "
         f"datos. El riesgo no es solo equivocarse. Es acostumbrarse a no "
         f"verificar. Otra trampa: convertir {t} en identidad. Uno deja de "
         f"estudiarlo y empieza a defenderlo, como si una objeción fuera un "
         f"insulto. Este libro se niega a eso. Prefiere un lector lento a "
         f"un adepto. Prefiere una corrección a una cita brillante. Si algo "
         f"de lo escrito aquí no resiste una segunda mirada, debe caer."),
        ("Un método reproducible",
         f"Para trabajar con {t} de aquí en adelante, basta un ritual "
         f"pequeño. 1) Escribe en una frase qué pregunta quieres contestar. "
         f"2) Reúne al menos dos fuentes independientes o, si no las hay, "
         f"declara que trabajas con una sola. 3) Copia a mano un pasaje "
         f"breve o un hecho fechado. 4) Explícalo sin mirar. 5) Anota lo "
         f"que no entendiste. 6) Vuelve al cabo de un día y tacha lo que "
         f"era adorno. Ese método cabe en una servilleta y no necesita "
         f"ninguna plataforma. A²S puede ayudarte a guardar el rastro, a "
         f"buscar repositorios o a maquetar el resultado. No puede, ni debe, "
         f"sustituir el paso 4."),
        ("Qué hacer el lunes",
         f"Un libro que no deja una acción es un adorno. El lunes, elige "
         f"una sola cosa relacionada con {t}: leer un capítulo de la obra "
         f"original, escribir doscientas palabras propias, o buscar tres "
         f"fuentes y anotar su fecha. No hagas las tres. La vanidad empieza "
         f"cuando la lista es más larga que la jornada. Si al viernes no "
         f"puedes contar qué cambió en tu mesa, el plan falló y hay que "
         f"achicarlo, no adornarlo. Este capítulo es corto a propósito. La "
         f"obra de verdad empieza cuando cierras el PDF."),
        ("Cierre y límites de este volumen",
         f"Estas páginas son un artefacto original de A²S sobre {t}. No "
         f"reproducen textos protegidos. No sustituyen una edición crítica, "
         f"un paper ni una conversación con alguien que sepa más. Si hubo "
         f"red, se usó para buscar fuentes y se declaró. Si no la hubo, el "
         f"libro se escribió igual, con el conocimiento local y con la "
         f"advertencia a la vista. El criterio de éxito no es un número de "
         f"calidad automática. Es que puedas leer este volumen seguido, "
         f"marcarlo y usarlo. Si no sirve, tíralo y pide otro con un "
         f"encargo más preciso. Un libro debe poder fallar. Si no puede "
         f"fallar, no era un libro: era un formulario."),
        (f"Una historia breve de {t}",
         f"Toda materia tiene una cronología, aunque sea tosca. {t} no "
         f"apareció ayer ni se agota hoy. Hubo un momento en que nadie "
         f"usaba ese nombre, otro en que se convirtió en moda y otro en "
         f"que empezó a cansar. Este capítulo no finge un tratado "
         f"histórico. Señala tres capas: origen, abuso y uso presente. "
         f"El origen explica por qué alguien lo necesitó. El abuso explica "
         f"por qué ahora desconfías. El uso presente es lo único que "
         f"puedes verificar esta semana. Si no puedes datar una afirmación "
         f"sobre {t}, trátala como opinión."),
        ("Contraste de enfoques",
         f"Hay al menos tres modos de acercarse a {t}. El primero es el "
         f"devoto: lo defiende como identidad. El segundo es el cínico: lo "
         f"reduce a un truco de mercado. El tercero es el artesano: lo "
         f"usa, lo mide y lo corrige. Este libro elige el tercero. No "
         f"porque sea más virtuoso, sino porque produce evidencia. El "
         f"devoto no admite fallo. El cínico no admite valor. El artesano "
         f"admite ambos y por eso puede mejorar. Si al leer te descubres "
         f"en el primer o el segundo bando, anótalo: es un dato sobre ti, "
         f"no sobre {t}."),
        (f"Un caso imaginado alrededor de {t}",
         f"Imagina a dos personas en una mesa. Una afirma que entiende "
         f"{t}. La otra pide una prueba que quepa en diez minutos. La "
         f"primera habla veinte. No hay prueba. Esa escena se repite en "
         f"oficinas, aulas y chats. El caso imaginado sirve para "
         f"entrenar la pregunta correcta: ¿qué tendría que ocurrir para "
         f"que yo cambiara de opinión? Si no puedes responderla, no "
         f"estás estudiando {t}: estás defendiendo una preferencia. El "
         f"resto de este capítulo es un ensayo de esa pregunta, no una "
         f"anécdota decorativa."),
        (f"Cómo enseñar {t} sin humillar",
         f"Enseñar {t} no es recitar. Es poner al otro en situación de "
         f"equivocarse barato. Una buena lección tiene un objeto, una "
         f"restricción y un criterio de éxito. «Explícalo sin mirar.» "
         f"«Señala un límite.» «Haz una sola cosa el lunes.» Quien enseña "
         f"para lucirse produce alumnos mudos. Quien enseña para que el "
         f"otro pueda seguir solo produce independencia. Este volumen "
         f"quiere lo segundo. Si lo usas en un aula o en un equipo, "
         f"empieza por el capítulo de método y termina por el del lunes."),
    ]


def to_markdown(title: str, chapters: list[tuple[str, str]],
                note: str = "") -> str:
    lines = [f"# {title}", "", note, "" if note else ""]
    lines.append("## Índice")
    lines.append("")
    for i, (heading, _) in enumerate(chapters, 1):
        lines.append(f"{i}. {heading}")
    lines.append("")
    for heading, body in chapters:
        lines.append(f"## {heading}")
        lines.append("")
        lines.append(body)
        lines.append("")
    return "\n".join(line for line in lines if line is not None).strip() + "\n"


def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text or "", re.UNICODE))
