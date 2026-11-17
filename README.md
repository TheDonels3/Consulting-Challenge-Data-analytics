# Consulting Challenge — EcoFood

Consultoría de datos para **EcoFood**, que quiere lanzar una línea de productos alimenticios sostenibles en Buenos Aires.

> **Estado:** los cuatro puntos tienen su notebook en el repo. Este README documenta en detalle los puntos **1 (oferta gastronómica)** y **3 (reseñas de consumidores)**; los puntos 2 (tendencias de búsqueda) y 4 (competencia) están en `notebooks/google_trends_ecofood_eda.ipynb` y `notebooks/punto4_competencia_oportunidades.ipynb`. Falta la síntesis final (3 insights ejecutivos) y el deck.

## Objetivo del cliente

Identificar zonas y categorías de Buenos Aires con mayor potencial para el lanzamiento de una línea de productos alimenticios sostenibles, y entender qué valora y qué castiga el consumidor.

## Fuentes de datos

| Archivo | Contenido | Origen |
|---|---|---|
| `data/raw/oferta_gastronomica.csv` | Oferta y Establecimientos Gastronómicos (2.823 registros crudos) | dataset abierto GCBA, publicado por el Ente de Turismo |
| `data/raw/poblacion_por_barrio.csv` | Población por barrio, Censo 2010 | dataset abierto GCBA |
| `data/raw/barrios_caba.geojson` | Polígonos y superficie de los 48 barrios | dataset abierto GCBA |
| `data/raw/espacios_verdes.csv` | 2.176 espacios verdes con superficie | dataset abierto GCBA |
| `data/raw/guiaoleo_restaurantes.jsonl` | 2.318 restaurantes de CABA con 1.075 reseñas públicas (captura vigente) | scraping de Guía Óleo |
| `data/raw/guiaoleo_captura.json` | Fecha de la captura vigente y resultado del último intento de actualizarla | generado por el scraper |
| `data/raw/trends_juntos.csv` | Interés de búsqueda semanal de 5 términos, Argentina, 5 años | Google Trends vía `pytrends` (punto 2) |
| `data/processed/establecimientos_clean.csv` | Resultado de la limpieza (2.811 locales) | generado por notebook 01 |
| `data/processed/barrios_sin_registro.csv` | Barrios oficiales sin ningún local (Parque Chas) | generado por notebook 01 |
| `data/processed/resenas_clean.csv` | 1.075 reseñas limpias con barrio, puntajes y precio | generado por notebook 03 |

## Metodología

1. **Limpieza de la oferta** (`notebooks/01_limpieza_oferta.ipynb`): reparación de encoding, normalización a los 48 barrios oficiales, 12 duplicados eliminados, nulos etiquetados como `SIN DATO`, variables derivadas (`es_saludable_estricto`, `es_saludable_amplio`, `zona`).
2. **EDA de la oferta** (`notebooks/02_eda_oferta.ipynb`): siete lentes en paralelo (volumen y concentración, densidad, composición de rubros, nivel de precio revelado, espacios verdes, oferta saludable, cruce final). Cada lente descarta una explicación alternativa distinta. Los rankings usan un umbral de volumen de 20 locales, y los candidatos a brecha se comparan contra el azar con una binomial.
3. **Reseñas de consumidores** (`notebooks/03_resenas_punto3.ipynb`): scraping ético de Guía Óleo con captura de respaldo, asignación de barrio por punto en polígono, análisis de puntajes (comida, servicio, ambiente), análisis de texto por diccionario (ajustado leyendo el contexto de cada palabra dudosa, con test de dos proporciones), y cruce con la oferta del punto 1 y la búsqueda del punto 2.

**Definición de "saludable"** (decisión del equipo, sobre la columna `cocina`): estricto = `NATURISTA` + `VEGETARIANA` (11 locales); amplio = estricto + `MEDITERRANEA`, `SUSHI`, `JAPONESA` (80 locales).

## Scraping: por qué Guía Óleo y cómo se hizo

El punto 3 no tiene dataset: hay que ir a buscar el dato. Antes de escribir código se verificó **si el sitio permite que un programa lo lea**:

| Fuente | `robots.txt` | Términos de uso | Resultado |
|---|---|---|---|
| Google Maps | bloquea rutas de contenido | prohíbe extracción automatizada | descartado |
| TripAdvisor | `Disallow` sobre `/AllReviews`, `/api` y cientos de rutas | prohíbe scraping | descartado |
| **Guía Óleo** | `Allow: /` para `*`; bloquea solo `/admin/`, `/api/`, `/search?`, `/map?` | no prohíbe la lectura automatizada | **elegido** |

El scraper (`scripts/scrape_guiaoleo.py`) aplica buenas prácticas:

- **User-agent honesto** (`ConsultingChallenge-EcoFood/1.0`), no simula un navegador.
- **Ritmo limitado**: 3 pedidos en paralelo y pausa entre pedidos (≈2 por segundo).
- **Solo páginas públicas** del sitemap; la API bloqueada no se usa.
- **Reanudable**: salida JSONL incremental, si se corta sigue donde quedó.
- **Respeto del bloqueo**: si el sitio hubiera prohibido la lectura, se buscaba otra fuente; no se evade ningún bloqueo.

- **Captura de respaldo**: si una corrida falla, se sigue usando la última captura buena (ver abajo).

Cada página declara cuántas reseñas tiene el local. Se bajó el **98,9%** de las que el sitio declara para CABA (1.075 de 1.087; el tope de reseñas visibles solo recorta 7 locales), así que no es una muestra de Guía Óleo: es prácticamente toda su comunidad en CABA. El límite real es que esa comunidad es **chica y nueva** (todas las reseñas son del último año) y que el scraper no identifica autores, así que no se sabe cuántas personas distintas escribieron.

### Captura de respaldo

El scraper nunca escribe a medias sobre los datos que usa el notebook:

1. Cada corrida baja todo a `data/raw/guiaoleo_restaurantes.parcial.jsonl` (reanudable, no se versiona).
2. Al terminar valida la captura nueva: al menos 90% del sitemap bajado sin error, al menos 90% de las páginas con nombre parseado (si el sitio cambia de diseño, el parser deja de encontrarlos) y no menos de la mitad de las reseñas de la captura anterior.
3. Si pasa, reemplaza a `guiaoleo_restaurantes.jsonl` de una sola vez. Los locales que fallaron en esa corrida se completan con su registro de la captura anterior, marcados con `"de_captura_anterior": true`.
4. Si falla cualquier cosa (sin red, sitio caído, `robots.txt` que deja de permitir la lectura, parser roto), **la captura vigente queda intacta** y el notebook sigue funcionando con ella. El motivo queda en `data/raw/guiaoleo_captura.json` y el notebook lo avisa al cargar los datos.

Si el sitemap no se puede bajar, se usa el último guardado. Si el `robots.txt` no se puede leer, no se scrapea: sin poder verificar el permiso, no se avanza.

## Principales hallazgos (punto 1 — oferta)

- **La oferta está concentrada:** 5 barrios (Palermo, San Nicolás, Recoleta, Balvanera, Monserrat) reúnen el 57% de los locales.
- **El segmento saludable es chico:** 2,85% de los locales con el criterio amplio, 0,4% con el estricto. El Norte tiene el mayor peso (4,8%); el Sur casi no tiene (1 local en 363).
- **Hay 16 candidatos a brecha de segmento** (barrios con volumen suficiente y peso saludable bajo la media), pero **solo 3 se distinguen del azar**: Balvanera, Monserrat y Flores. El resto son hipótesis.
- **23 de 47 barrios no son concluyentes** por tener menos de 20 locales.
- La asociación entre oferta saludable, perfil de consumo y espacio verde es débil y en parte mecánica; no se toma como señal de demanda.

## Principales hallazgos (punto 3 — reseñas)

Sobre 2.318 restaurantes relevados y 1.075 reseñas (948 con texto, 497 con precio declarado):

- **Lo saludable que la gente busca y menciona es sin TACC.** Es el subtema saludable más mencionado en las reseñas (20 de 39), con lenguaje de escasez ("de esos pocos refugios", "no se consigue en todos lados"). En Google Trends, "sin TACC" promedia 73,5 de interés contra 3,9 de "alimentación saludable". Y la oferta especializada es mínima: 13 de 2.235 locales de Guía Óleo (0,6%); el registro del GCBA ni siquiera tiene la categoría. Es el cruce búsqueda alta / oferta baja que pide el bonus, y apunta a producto (panificados, almacén, para llevar).
- **Lo que más castiga una reseña es la espera.** La comida es la dimensión mejor puntuada (2,35/3, 48% "Excelente"). En el texto, el único tema que separa con firmeza las reseñas peor puntuadas de las mejores es la espera: 8,1% contra 2,4% (p = 0,003), y 13,2% contra 2,4% con un corte más estricto. La atención va al revés: se nombra para elogiar.
- **Entre quienes ya consumen, el precio no predice la satisfacción.** Precio contra puntaje: r = 0,12. El precio se menciona parecido en reseñas buenas y malas (18,4% contra 15,7%, p = 0,38). Esto **no** dice que el precio no frene a quien no compra: quien no compra no reseña.
- **Validación parcial del proxy del punto 1.** La oferta saludable correlaciona con el nivel de precios (mediana r = 0,43, media r = 0,54, percentil 75 r = 0,54) pero no con el porcentaje de reseñas con precio de $40.000 o más, y el proxy de ambientación premium no se sostiene.
- **Las fuentes de oferta no ven el mismo mercado.** El Centro pesa 39% de los locales en el registro de Turismo y 18% en Guía Óleo; el Oeste, 13% contra 27%. Las conclusiones geográficas del punto 1 hablan de oferta registrada, no del mercado completo.

> **Corrección respecto de la versión anterior:** el diccionario contaba "tener en cuenta" como precio y "rápido" como espera, y el léxico de sentimiento era circular con los temas ("caro" ya hacía negativa una reseña). Corregido, desaparece el hallazgo "el precio se menciona más cuando algo falla" y la espera se sostiene con números más chicos. La lectura "lo saludable casi no se habla" se descartó: no tenía vara de comparación contra la oferta existente.

## Recomendaciones preliminares

- Priorizar la validación de demanda (punto 2) en **Balvanera, Monserrat y Flores** antes de hablar de oportunidad.
- No leer "poca oferta saludable" como oportunidad sin cruzarla con demanda: el dataset describe oferta, no demanda.
- **Para el producto:** validar una línea **sin TACC** (panificados y productos para llevar) como primera apuesta: es donde coinciden búsqueda alta, oferta especializada mínima y consumidores que dicen que cuesta encontrarla. Antes de invertir, medir el tamaño real de esa demanda (las reseñas son pocas y no se sabe de cuántas personas).
- **Para la experiencia:** si EcoFood vende en local propio o a través de cafés y restaurantes, el tiempo de espera es el punto crítico a cuidar.
- **Para el precio:** el precio alto no castiga a quien ya compra. Si frena a quien no compra, estos datos no lo dicen: hace falta una encuesta o un relevamiento de precios de góndola.

## Limitaciones

- No hay precios, alquileres ni ingresos en la fuente oficial; el poder adquisitivo se aproxima con la composición de la oferta y queda **parcialmente validado** contra precios reales, no confirmado.
- La población es del Censo 2010.
- El dataset de oferta es una foto, no una serie temporal.
- Parque Chas no tiene registros: no se puede afirmar que no tenga oferta.
- La definición de "saludable" es una decisión nuestra y los resultados cambian si cambia.
- Las reseñas son de quien escribe reseñas: un subconjunto autoseleccionado, no el público general.
- El registro del GCBA lo publica el Ente de Turismo: no es un censo de la gastronomía. Guía Óleo tampoco (cubre locales con visibilidad), y las dos reparten la oferta entre zonas muy distinto.
- La comunidad de Guía Óleo es chica y nueva (1.075 reseñas en CABA, todas del último año) y el scraper no identifica autores: no se sabe cuántas personas distintas escribieron.
- Las reseñas son de quien ya compró: no pueden medir si el precio frena a quien no compra.
- El análisis de texto usa un diccionario explícito, no un modelo de lenguaje: es auditable, pero puede fallar con ironía y negaciones.
- `trends_juntos.csv` (punto 2) se guardó sin la columna de fechas, así que hoy no se puede ver la evolución en el tiempo.

## Estructura del repositorio

```text
├── data/
│   ├── raw/          # fuentes originales y scrape crudo
│   └── processed/    # datos limpios (oferta y reseñas)
├── notebooks/        # 01 limpieza, 02 EDA oferta, 03 reseñas, Google Trends (punto 2), competencia (punto 4)
├── scripts/          # scraper de Guía Óleo
├── images/           # gráficos para el deck
├── presentation/     # deck ejecutivo (pendiente)
└── README.md
```

## Cómo reproducir

```bash
python -m venv .venv && source .venv/bin/activate
pip install pandas numpy matplotlib jupyter requests beautifulsoup4 lxml
cd notebooks
jupyter lab   # ejecutar 01, luego 02, luego 03
```

Para actualizar el scrape (opcional, tarda ~18 minutos y es reanudable; si falla, se mantiene la captura anterior):

```bash
python scripts/scrape_guiaoleo.py              # actualiza la captura vigente
python scripts/scrape_guiaoleo.py --limit 20   # muestra de prueba, no toca la vigente
```

El notebook 01 regenera `data/processed/establecimientos_clean.csv`; el 02 regenera los gráficos `01` a `03`; el 03 regenera `data/processed/resenas_clean.csv` y los gráficos `04` a `07`. Las rutas son relativas a `notebooks/`.
