# Consulting Challenge — EcoFood

Consultoría de datos para **EcoFood**, que quiere lanzar una línea de productos alimenticios sostenibles en Buenos Aires.

> **Estado:** este README documenta el **punto 1 (oferta gastronómica y mercado actual)**. Los puntos 2 (tendencias), 3 (reseñas) y 4 (competencia) los trabajan otros integrantes del equipo y se completan al integrar.

## Objetivo del cliente

Identificar zonas y categorías de Buenos Aires con mayor potencial para el lanzamiento de una línea de productos alimenticios sostenibles.

## Fuentes de datos

Todas son datos abiertos del Gobierno de la Ciudad de Buenos Aires (GCBA). No hay scraping ni fuentes pagas.

| Archivo | Contenido |
|---|---|
| `data/raw/oferta_gastronomica.csv` | Oferta y Establecimientos Gastronómicos (2.823 registros crudos) |
| `data/raw/poblacion_por_barrio.csv` | Población por barrio, Censo 2010 |
| `data/raw/barrios_caba.geojson` | Polígonos y superficie de los 48 barrios |
| `data/raw/espacios_verdes.csv` | 2.176 espacios verdes con superficie |
| `data/processed/establecimientos_clean.csv` | Resultado de la limpieza (2.811 locales) |
| `data/processed/barrios_sin_registro.csv` | Barrios oficiales sin ningún local (Parque Chas) |

## Metodología

1. **Limpieza** (`notebooks/01_limpieza_oferta.ipynb`): reparación de encoding, normalización a los 48 barrios oficiales, 12 duplicados eliminados, nulos etiquetados como `SIN DATO`, variables derivadas (`es_saludable_estricto`, `es_saludable_amplio`, `zona`).
2. **EDA** (`notebooks/02_eda_oferta.ipynb`): siete lentes en paralelo (volumen y concentración, densidad, composición de rubros, nivel de precio revelado, espacios verdes, oferta saludable, cruce final). Cada lente descarta una explicación alternativa distinta. Los rankings usan un umbral de volumen de 20 locales, y los candidatos a brecha se comparan contra el azar con una binomial.

**Definición de "saludable"** (decisión del equipo, sobre la columna `cocina`): estricto = `NATURISTA` + `VEGETARIANA` (11 locales); amplio = estricto + `MEDITERRANEA`, `SUSHI`, `JAPONESA` (80 locales).

## Principales hallazgos (punto 1)

- **La oferta está concentrada:** 5 barrios (Palermo, San Nicolás, Recoleta, Balvanera, Monserrat) reúnen el 57% de los locales.
- **El segmento saludable es chico:** 2,85% de los locales con el criterio amplio, 0,4% con el estricto. El Norte tiene el mayor peso (4,8%); el Sur casi no tiene (1 local en 363).
- **Hay 16 candidatos a brecha de segmento** (barrios con volumen suficiente y peso saludable bajo la media), pero **solo 3 se distinguen del azar**: Balvanera, Monserrat y Flores. El resto son hipótesis.
- **23 de 47 barrios no son concluyentes** por tener menos de 20 locales.
- La asociación entre oferta saludable, perfil de consumo y espacio verde es débil y en parte mecánica; no se toma como señal de demanda.

## Recomendaciones preliminares

- Priorizar la validación de demanda (punto 2 y punto 3) en **Balvanera, Monserrat y Flores** antes de hablar de oportunidad.
- No leer "poca oferta saludable" como oportunidad sin cruzarla con demanda: el dataset describe oferta, no demanda.

## Limitaciones

- No hay precios, alquileres ni ingresos; el poder adquisitivo se aproxima con la composición de la oferta y no está validado contra datos externos.
- La población es del Censo 2010.
- El dataset es una foto, no una serie temporal.
- Parque Chas no tiene registros: no se puede afirmar que no tenga oferta.
- La definición de "saludable" es una decisión nuestra y los resultados cambian si cambia.

## Estructura del repositorio

```text
├── data/
│   ├── raw/          # fuentes originales, sin tocar
│   └── processed/    # datos limpios
├── notebooks/        # 01 limpieza, 02 EDA
├── images/           # gráficos para el deck
├── presentation/     # deck ejecutivo (pendiente)
└── README.md
```

## Cómo reproducir

```bash
python -m venv .venv && source .venv/bin/activate
pip install pandas numpy matplotlib jupyter
cd notebooks
jupyter lab   # ejecutar 01_limpieza_oferta.ipynb y luego 02_eda_oferta.ipynb
```

El notebook 01 regenera `data/processed/`; el 02 regenera los gráficos en `images/`. Las rutas son relativas a `notebooks/`.
