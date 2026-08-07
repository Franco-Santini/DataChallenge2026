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

\[
C_{total} = C_{packaging} + C_{flete}
\]

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

Los datos originales utilizados en el desafío se encuentran distribuidos en cuatro archivos:

```text
Data/
├── catalogo_productos.csv
├── especificaciones_cajas.csv
├── operaciones_planta.csv
└── procurement_cajas.csv
```

Estos archivos contienen, respectivamente:

* información y características de los productos;
* dimensiones y especificaciones de las cajas actuales;
* volúmenes de producción y costos logísticos;
* información de compras y costos de packaging.

Los archivos derivados durante el procesamiento se almacenan separadamente en `Datos modificados/` y los resultados intermedios de optimización en `outputs/`.

---

# Requisitos

El proyecto utiliza **R** para el procesamiento inicial, análisis exploratorio y desarrollo de las heurísticas, y **Python** para la generación de candidatas y la optimización matemática.

## R

Principales paquetes utilizados:

```r
dplyr
tidyr
readr
stringr
ggplot2
plotly
scales
forcats
ggridges
```

## Python

Principales dependencias:

```text
pandas
numpy
ortools
```

Se recomienda utilizar un entorno virtual de Python antes de instalar las dependencias.

Por ejemplo:

```bash
python -m venv .venv
```

En Windows:

```bash
.venv\Scripts\activate
```

En Linux/macOS:

```bash
source .venv/bin/activate
```

Luego instalar las dependencias necesarias:

```bash
pip install pandas numpy ortools
```

---

# Organización del repositorio

```text
.
├── Data/
│   ├── catalogo_productos.csv
│   ├── especificaciones_cajas.csv
│   ├── operaciones_planta.csv
│   └── procurement_cajas.csv
│
├── Datos modificados/
│   ├── catalogo_especificaciones_operaciones.csv
│   └── catalogo_especificaciones_operaciones.csv
│
├── Código/
│   ├── R/
│   │   ├── 01 data_prep.R
│   │   ├── 02 EDA.R
│   │   ├── 03 matriz de compatibilidad.R
│   │   └── 04 heuristica.R
│   │
│   └── python/
│       ├── 01_generar_candidatas.py
│       ├── 02_matriz_factibilidad.py
│       ├── 03_auditar_insumos.py
│       ├── 04_mip_flete_packaging.py
│       ├── 05_generar_entrega_kaggle.py
│
├── outputs/
│   ├── cajas_candidatas.csv
│   ├── matriz_factibilidad.csv
│   ├── entrega_kaggle.csv
│   └── solucion_final.csv
│
├── Informe.Rmd
├── Informe.html
├── .gitignore
└── README.md
```

Las carpetas `Datos modificados/` y `outputs/` contienen archivos generados durante la ejecución del proyecto y pueden excluirse del control de versiones cuando corresponda.

---

# Ejecución del proyecto

Para reproducir el análisis completo, los scripts deben ejecutarse siguiendo el orden indicado a continuación.

## 1. Preparación de los datos

```text
Código/R/01 data_prep.R
```

Realiza la limpieza de las fuentes originales, tratamiento de valores faltantes e inconsistencias y construcción de las bases integradas utilizadas posteriormente.

---

## 2. Análisis exploratorio

```text
Código/R/02 EDA.R
```

Contiene el análisis descriptivo del portafolio actual de productos y cajas, incluyendo dimensiones, utilización de pallets, estructura de costos y descuentos por planta.

---

## 3. Matriz de compatibilidad inicial

```text
Código/R/03 matriz de compatibilidad.R
```

Evalúa las combinaciones entre productos, cajas y grosores disponibles, verificando las restricciones físicas del problema.

---

## 4. Heurística de consolidación

```text
Código/R/04 heuristica.R
```

Construye una solución inicial mediante clustering aglomerativo orientado a minimizar el costo total y permite comparar los tres escenarios de grosor.

---

## 5. Generación de cajas candidatas

```bash
python "Código/python/01_generar_candidatas.py"
```

Genera nuevos diseños potenciales de caja a partir de las características geométricas de los productos y de las soluciones obtenidas previamente.

---

## 6. Matriz de factibilidad

```bash
python "Código/python/02_matriz_factibilidad.py"
```

Determina todas las asignaciones factibles entre productos y cajas candidatas y precalcula el costo de flete asociado a cada alternativa.

---

## 7. Auditoría de los insumos

```bash
python "Código/python/03_auditar_insumos.py"
```

Verifica que todos los productos cuenten con al menos una caja candidata factible y genera estadísticas de diagnóstico antes de ejecutar el modelo de optimización.

---

## 8. Optimización

El modelo principal que incorpora simultáneamente los costos de packaging y flete:

```bash
python "Código/python/04_mip_flete_packaging.py"
```

---

## 9. Generación de la entrega

Una vez obtenida la solución, se genera el entregable para Kaggle:

```bash
python "Código/python/05_generar_entrega_kaggle.py"
```

---

# Resultado

El procedimiento permitió obtener una solución factible utilizando un único grosor global de **3,0 mm**, reduciendo significativamente el costo total respecto de la situación inicial.

La solución final alcanzó un **score de 10.11098 en Kaggle**, correspondiente al mejor nivel de ahorro identificado durante el desarrollo del desafío.

El resultado combina la mejora en la utilización logística con la consolidación del volumen de compra de cajas, permitiendo capturar simultáneamente reducciones en los costos de **flete y packaging**.

---

# Reproducibilidad

El pipeline fue diseñado para separar claramente:

1. los **datos originales**;
2. los **datos procesados**;
3. la **generación de alternativas factibles**;
4. la **optimización**;
5. la **validación de la solución**;
6. la **generación del archivo final de entrega**.

De esta manera, los resultados pueden reproducirse desde las fuentes originales y cada etapa puede auditarse de manera independiente.
