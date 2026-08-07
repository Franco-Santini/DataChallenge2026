# Bonsai Corp Data Challenge — Optimización de Packaging y Logística

## Integrantes

* Franco Santini
* Manuel Moresi
* Simón Gazze

---

# Objetivo

Este repositorio contiene el desarrollo realizado para el **Bonsai Corp Data Challenge**, organizado por **AlixPartners**.

El desafío consiste en optimizar el portafolio de cajas utilizadas por Bonsai Corp para la distribución de productos de brócoli congelado desde cinco plantas, buscando reducir los costos asociados a **packaging y logística** sin incumplir las restricciones físicas y operativas del problema.

El objetivo general puede expresarse como:

$C_{total} = C_{packaging} + C_{flete}$

Para ello, se busca consolidar distintos productos en un menor número de diseños de caja, teniendo en cuenta:

* compatibilidad geométrica entre producto y caja;
* límites de modificación de dimensiones;
* headspace máximo permitido;
* resistencia a compresión según el grosor del cartón;
* utilización y capacidad del pallet;
* volúmenes de producción por planta;
* descuentos de packaging por volumen consolidado;
* costo logístico asociado a la cantidad de pallets requeridos.

---

# Datos

Los datos originales del desafío están en:

```text
Data/
├── catalogo_productos.csv
├── especificaciones_cajas.csv
├── operaciones_planta.csv
└── procurement_cajas.csv
```

Estos archivos contienen, respectivamente: características de los productos; dimensiones y especificaciones de las cajas actuales; volúmenes de producción y costos logísticos por planta; e información de compras y costos de packaging.

`Data/archive/` conserva una copia de estos mismos archivos tal como se entregaron originalmente, y `Data/alix-partners-data-challenge.zip` es el paquete de datos sin descomprimir. Ninguno de los dos es necesario para reproducir los resultados: alcanza con los cuatro CSV listados arriba.

Los archivos derivados durante el preprocesamiento en R se guardan en `Datos modificados/`, y las corridas de la heurística exploratoria en `outputs/`. **El pipeline final de optimización (CP-SAT) no depende de ninguno de los dos**: lee directamente desde `Data/` y desde los certificados versionados en `Código/python/CP-SAT/certificados/` (ver sección de Reproducibilidad).

---

# Organización del repositorio

```text
.
├── Data/                                    # Datos originales del desafío
│   ├── catalogo_productos.csv
│   ├── especificaciones_cajas.csv
│   ├── operaciones_planta.csv
│   ├── procurement_cajas.csv
│   └── archive/                             # Copia de respaldo de los CSV originales
│
├── Datos modificados/                       # Salidas del preprocesamiento en R (01 data_prep.R)
│
├── Código/
│   ├── 01 data_prep.R                       # Limpieza e imputación de los datos crudos
│   ├── 02 EDA.R                             # Análisis exploratorio del portafolio actual
│   ├── 03 matriz de compatibilidad.R        # Matriz producto × caja × grosor y su exploración
│   ├── 04 gastos_resultado_optimo.R         # Costos de packaging/flete de la solución final, para el informe
│   │
│   └── python/
│       ├── Heuristica/                      # Enfoque exploratorio previo (greedy + búsqueda local)
│       │   ├── 01_generar_candidatas.py     #   candidatas por k-vecinos más cercanos, no exhaustivo
│       │   └── 02_matriz_factibilidad.py
│       │
│       └── CP-SAT/                          # Pipeline final: optimización exacta con OR-Tools CP-SAT
│           ├── requirements.txt             #   versiones fijas (numpy, pandas, ortools)
│           ├── src/
│           │   ├── repo_paths.py            #   resuelve las rutas del repo (Data/, certificados/, etc.)
│           │   ├── 01_generar_candidatas.py #   genera los diseños de caja candidatos
│           │   ├── 02_construir_matriz.py   #   matriz de factibilidad producto × candidata + flete
│           │   ├── 03_resolver_cp_sat.py    #   modelo y resolución CP-SAT (packaging + flete)
│           │   └── 04_validar_exportar.py   #   validación estricta y generación de la entrega Kaggle
│           ├── certificados/                #   insumos versionados para reproducir sin depender de R
│           ├── intermedios/                 #   candidatas y matriz ya calculadas (atajo opcional)
│           └── resultados_referencia/       #   entrega y solución de referencia (score 10.11098)
│
├── outputs/                                 # Corridas de la heurística exploratoria (greedy + búsqueda local)
│   └── runs/
│
├── img/                                     # Imágenes usadas en Informe.Rmd
├── consigna_DataChallenge_AlixPartners.pdf  # Enunciado del desafío
├── Informe.Rmd / Informe.html               # Informe final
├── DataChallenge2026.Rproj
├── .gitignore
└── README.md
```

---

# Requisitos

## R

Paquetes utilizados a lo largo de los scripts de `Código/*.R` y de `Informe.Rmd`:

```r
dplyr
tidyr
stringr
purrr
ggplot2
plotly
scales
igraph
forcats
ggridges
kableExtra
```

## Python

El pipeline final (`Código/python/CP-SAT/`) fija versiones exactas en su propio `requirements.txt`:

```text
numpy>=2.0,<3
pandas>=2.2,<3
ortools==9.14.6206
```

Se recomienda un entorno virtual dedicado:

```powershell
cd "Código/python/CP-SAT"
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

La carpeta `Código/python/Heuristica/` (enfoque exploratorio, no necesario para reproducir el resultado final) solo requiere `numpy` y `pandas`.

---

# Ejecución del proyecto

El resultado final y reproducible del desafío se obtiene íntegramente con el pipeline de `Código/python/CP-SAT/` (sección siguiente), que **no depende de correr antes los scripts de R**: todos los insumos que necesita ya están versionados en `Data/` y en `Código/python/CP-SAT/certificados/`.

Los pasos de R y la heurística exploratoria documentan el camino recorrido (preprocesamiento, análisis exploratorio, matriz de compatibilidad y un primer enfoque greedy + búsqueda local) antes de llegar al modelo exacto en CP-SAT, y son los que sustentan las figuras de `Informe.Rmd`.

## 1. Preparación de los datos (R)

```text
Código/01 data_prep.R
```

Limpieza de las fuentes originales, imputación de valores faltantes y construcción de las bases integradas en `Datos modificados/`.

## 2. Análisis exploratorio (R)

```text
Código/02 EDA.R
```

Análisis descriptivo del portafolio actual: dimensiones, utilización de pallets, estructura de costos y descuentos por planta.

## 3. Matriz de compatibilidad (R)

```text
Código/03 matriz de compatibilidad.R
```

Evalúa la compatibilidad geométrica y estructural entre productos, cajas y grosores (fit, volumen, headspace, resistencia a compresión), con visualizaciones exploratorias (heatmap, embudo, agrupamiento por grafos).

## 4. Heurística exploratoria — greedy + búsqueda local (Python, opcional)

```bash
python "Código/python/Heuristica/01_generar_candidatas.py"
python "Código/python/Heuristica/02_matriz_factibilidad.py"
```

Primer enfoque de consolidación: genera candidatas restringiendo cada SKU a sus *k* vecinos geométricamente más parecidos (en vez de evaluar todos los pares) y arma una matriz de factibilidad reducida. Sirvió para explorar el espacio de soluciones antes de pasar al modelo exacto; no es necesario para reproducir la entrega final.

## 5. Optimización final — CP-SAT (Python, pipeline reproducible)

Parado en `Código/python/CP-SAT`, con el entorno virtual activado:

**Camino rápido — validar la entrega ganadora sin resolver nada:**

```bash
python src/04_validar_exportar.py --no-reference-check
```

Valida las 427 asignaciones contra todas las restricciones físicas y recalcula costo y score desde cero. En Linux/macOS puede omitirse `--no-reference-check` para exigir además coincidencia byte a byte con `resultados_referencia/entrega_kaggle_optimo_10_11098.csv` (en Windows esa comparación falla por una diferencia de precisión de `numpy.longdouble` de 64 vs. 80 bits — ver Reproducibilidad).

**Camino completo — reproducir todo desde los datos crudos:**

```bash
python src/01_generar_candidatas.py
python src/02_construir_matriz.py
python src/03_resolver_cp_sat.py --intermediate-dir intermedios_reconstruidos
python src/04_validar_exportar.py --input resultados/solucion_busqueda.csv --no-reference-check
```

* `01_generar_candidatas.py` genera los diseños de caja candidatos (individuales y por pares de SKU compatibles).
* `02_construir_matriz.py` arma la matriz de factibilidad producto × candidata y su costo de flete.
* `03_resolver_cp_sat.py` reduce el universo a las cajas no dominadas y resuelve el modelo CP-SAT (packaging por tramos + flete), partiendo de un incumbente ya certificado como *hint*.
* `04_validar_exportar.py` repite la validación estricta sobre la solución del solver y genera la entrega para Kaggle.

Si se omite `--intermediate-dir intermedios_reconstruidos` en el paso 3, se usan por defecto los intermedios ya versionados en `CP-SAT/intermedios/`, salteando los pasos 1 y 2.

## 6. Métricas finales para el informe (R)

```text
Código/04 gastos_resultado_optimo.R
```

Toma la entrega generada por CP-SAT (`outputs/entrega_kaggle_optimo_10.csv`) y calcula los costos de packaging y flete resultantes por planta, usados en `Informe.Rmd`. No participa en la búsqueda de la solución óptima.

---

# Resultado

El procedimiento permitió obtener una solución factible utilizando un único grosor global de **3,0 mm**, reduciendo significativamente el costo total respecto de la situación inicial.

La solución final alcanzó un **score de 10.11098 en Kaggle** (costo total USD 188.079.384,24), correspondiente al mejor nivel de ahorro identificado durante el desafío.

El resultado combina la mejora en la utilización logística con la consolidación del volumen de compra de cajas, permitiendo capturar simultáneamente reducciones en los costos de **flete y packaging**.

---

# Reproducibilidad

El pipeline final (`Código/python/CP-SAT/`) fue verificado de punta a punta: instalando las versiones fijas de `requirements.txt` en un entorno limpio y corriendo los 4 scripts en orden (`01` → `02` → `03` → `04`), la reconstrucción completa desde `Data/` reprodujo exactamente el costo y el score de la entrega certificada:

| Etapa | Resultado obtenido |
|---|---|
| Candidatas físicas generadas | 5.894 |
| Aristas producto × candidata | 184.457 |
| Cajas no dominadas / aristas tras reducción | 953 / 32.808 |
| Costo total del solver | USD 188.079.384,24 |
| Score | 10.11098 |

Todo lo necesario está versionado en el repositorio (`Data/` + `Código/python/CP-SAT/certificados/`), por lo que este pipeline puede reproducirse sin ejecutar antes los scripts de R.

**Nota de plataforma:** en Windows, `numpy.longdouble` es equivalente a `float64` (64 bits), mientras que en Linux/macOS tiene precisión extendida (80 bits). Esto hace que el paso 4 (`04_validar_exportar.py`) produzca dimensiones con una diferencia en el último decimal (12ª cifra) frente al CSV de referencia, y por lo tanto la comparación *byte a byte* falla en Windows aun cuando el costo y el score coincidan exactamente. Usar `--no-reference-check` en ese caso, o correr la validación en Linux/macOS para la comparación estricta.

**Nota de tiempos:** el paso 3 usa un incumbente casi óptimo como *hint* y detiene la búsqueda apenas alcanza el costo objetivo conocido (en las pruebas, ~135 s de tiempo interno del solver). La solución mejorada se graba en `resultados/solucion_busqueda.csv` en cuanto se encuentra; el proceso puede demorar más en cerrar limpiamente sus 8 workers en paralelo, pero no hace falta esperar a que termine para disponer del resultado.
