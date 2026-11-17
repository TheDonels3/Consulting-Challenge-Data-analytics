# Consulting Challenge — EcoFood

Consultoría de datos para **EcoFood**, que quiere lanzar una línea de productos alimenticios sostenibles en Buenos Aires.

> **Estado:** puntos **1 (oferta gastronómica)** y **3 (reseñas de consumidores)** completos. Los puntos 2 (tendencias de búsqueda) y 4 (competencia) los trabajan otros integrantes del equipo y se integran al final.

## Objetivo del cliente

Identificar zonas y categorías de Buenos Aires con mayor potencial para el lanzamiento de una línea de productos alimenticios sostenibles, y entender qué valora y qué castiga el consumidor.

## Fuentes de datos

| Archivo | Contenido | Origen |
|---|---|---|
| `data/raw/oferta_gastronomica.csv` | Oferta y Establecimientos Gastronómicos (2.823 registros crudos) | dataset abierto GCBA |
| `data/raw/poblacion_por_barrio.csv` | Población por barrio, Censo 2010 | dataset abierto GCBA |
| `data/raw/barrios_caba.geojson` | Polígonos y superficie de los 48 barrios | dataset abierto GCBA |
| `data/raw/espacios_verdes.csv` | 2.176 espacios verdes con superficie | dataset abierto GCBA |
| `data/raw/guiaoleo_restaurantes.jsonl` | 2.318 restaurantes de CABA con 1.075 reseñas públicas | scraping de Guía Óleo |
| `data/processed/establecimientos_clean.csv` | Resultado de la limpieza (2.811 locales) | generado por notebook 01 |
| `data/processed/barrios_sin_registro.csv` | Barrios oficiales sin ningún local (Parque Chas) | generado por notebook 01 |
| `data/processed/resenas_clean.csv` | 1.075 reseñas limpias con barrio, puntajes y precio | generado por notebook 03 |

## Metodología

1. **Limpieza de la oferta** (`notebooks/01_limpieza_oferta.ipynb`): reparación de encoding, normalización a los 48 barrios oficiales, 12 duplicados eliminados, nulos etiquetados como `SIN DATO`, variables derivadas (`es_saludable_estricto`, `es_saludable_amplio`, `zona`).
2. **EDA de la oferta** (`notebooks/02_eda_oferta.ipynb`): siete lentes en paralelo (volumen y concentración, densidad, composición de rubros, nivel de precio revelado, espacios verdes, oferta saludable, cruce final). Cada lente descarta una explicación alternativa distinta. Los rankings usan un umbral de volumen de 20 locales, y los candidatos a brecha se comparan contra el azar con una binomial.
3. **Reseñas de consumidores** (`notebooks/03_resenas_punto3.ipynb`): scraping ético de Guía Óleo, asignación de barrio por punto en polígono, análisis de puntajes (comida, servicio, ambiente), análisis de texto por diccionario, y cruce con la oferta del punto 1.

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

Guía Óleo muestra solo las reseñas más recientes de cada local (máximo 5 visibles), no el historial completo. Eso se declara como límite.

## Principales hallazgos (punto 1 — oferta)

- **La oferta está concentrada:** 5 barrios (Palermo, San Nicolás, Recoleta, Balvanera, Monserrat) reúnen el 57% de los locales.
- **El segmento saludable es chico:** 2,85% de los locales con el criterio amplio, 0,4% con el estricto. El Norte tiene el mayor peso (4,8%); el Sur casi no tiene (1 local en 363).
- **Hay 16 candidatos a brecha de segmento** (barrios con volumen suficiente y peso saludable bajo la media), pero **solo 3 se distinguen del azar**: Balvanera, Monserrat y Flores. El resto son hipótesis.
- **23 de 47 barrios no son concluyentes** por tener menos de 20 locales.
- La asociación entre oferta saludable, perfil de consumo y espacio verde es débil y en parte mecánica; no se toma como señal de demanda.

## Principales hallazgos (punto 3 — reseñas)

Sobre 2.318 restaurantes relevados y 1.075 reseñas (948 con texto, 497 con precio declarado):

- **La comida convence; la experiencia se rompe en la espera.** La comida es la dimensión mejor puntuada (2,35/3, 48% "Excelente") y el servicio concentra las peores evaluaciones (18% "Bueno" o menos). En el texto, el tema que más separa una buena reseña de una mala es **la espera**: 13,8% en reseñas de puntaje bajo contra 4,4% en las de puntaje alto.
- **El precio no explica la satisfacción.** Precio contra puntaje: r = 0,12 (comida r = 0,06). El precio se menciona más cuando algo falla (42,9% en reseñas negativas contra 20,0% en positivas), pero lo caro no se castiga por caro.
- **La categoría saludable casi no se habla.** Solo 3,2% de las reseñas mencionan vegano, vegetariano, orgánico, sin gluten o natural (6,0% con un léxico ampliado). El sello saludable no vende solo: es un plus, no una propuesta de valor suficiente.
- **Validación parcial del proxy del punto 1.** La oferta saludable correlaciona con el nivel de precios (mediana r = 0,43, media r = 0,54, percentil 75 r = 0,54) pero no con la proporción de locales caros, y el proxy de ambientación premium no se sostiene.

## Recomendaciones preliminares

- Priorizar la validación de demanda (punto 2) en **Balvanera, Monserrat y Flores** antes de hablar de oportunidad.
- No leer "poca oferta saludable" como oportunidad sin cruzarla con demanda: el dataset describe oferta, no demanda.
- **Para el producto:** competir por sabor y conveniencia, no por el sello "saludable". La comunicación saludable funciona como refuerzo, no como argumento principal.
- **Para la experiencia:** si EcoFood se vende en locales de terceros o en formato propio, el tiempo de espera es el punto crítico a cuidar.
- **Para el precio:** no posicionar como "barato para ser saludable"; el consumidor no castiga el precio alto, castiga la experiencia que no lo justifica.

## Limitaciones

- No hay precios, alquileres ni ingresos en la fuente oficial; el poder adquisitivo se aproxima con la composición de la oferta y queda **parcialmente validado** contra precios reales, no confirmado.
- La población es del Censo 2010.
- El dataset de oferta es una foto, no una serie temporal.
- Parque Chas no tiene registros: no se puede afirmar que no tenga oferta.
- La definición de "saludable" es una decisión nuestra y los resultados cambian si cambia.
- Las reseñas son de quien escribe reseñas: un subconjunto autoseleccionado, no el público general.
- Guía Óleo cubre locales con visibilidad y muestra solo las reseñas recientes; no es el universo de la gastronomía porteña.
- El análisis de texto usa un diccionario explícito, no un modelo de lenguaje: es auditable, pero puede fallar con ironía y negaciones.

## Estructura del repositorio

```text
├── data/
│   ├── raw/          # fuentes originales y scrape crudo
│   └── processed/    # datos limpios (oferta y reseñas)
├── notebooks/        # 01 limpieza, 02 EDA oferta, 03 reseñas
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

Para regenerar el scrape (opcional, tarda ~18 minutos y es reanudable):

```bash
python scripts/scrape_guiaoleo.py
```

El notebook 01 regenera `data/processed/establecimientos_clean.csv`; el 02 regenera los gráficos `01` a `03`; el 03 regenera `data/processed/resenas_clean.csv` y los gráficos `04` a `07`. Las rutas son relativas a `notebooks/`.
