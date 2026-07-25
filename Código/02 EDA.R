# Librerias a utilizar
library(dplyr)
library(ggplot2)
library(plotly)

# Lectura de los data sets
procurement <- read.csv("Datos modificados/procurement_modificado.csv")
catalogo_especificaciones <- read.csv("Datos modificados/catalogo_especificaciones.csv")
catalogo_operaciones <- read.csv("Datos modificados/catalogo_operaciones.csv")
catalogo_especificaciones_operaciones <- read.csv("Datos modificados/catalogo_especificaciones_operaciones.csv")
catalogo_especificaciones_procurement <- read.csv("Datos modificados/catalogo_especificaciones_procurement.csv")
especificaciones_procurement <- read.csv("Datos modificados/especificaciones_procurement.csv")

G = 9.81
################------------------- Gráfico posibles -------------------################
# Cantidad de productos por tipo de caja
catalogo_especificaciones_operaciones |> 
  group_by(caja_tipo_id) |> 
  summarise(
    n_prod = n_distinct(codigo_producto)
  ) |> 
  ungroup() |> 
  ggplot() +
  aes(x = n_prod) +
  geom_bar(color = "black", fill = "steelblue") +
  labs(x = "Productos por caja", y = "Cantidad") +
  theme_bw()

# Cantidad de productos segun categoria
catalogo_especificaciones_operaciones |> 
  group_by(categoria) |> 
  summarise(
    n_prod = n_distinct(codigo_producto)
  ) |> 
  ggplot() +
  aes(x = categoria, y = n_prod) +
  geom_col(color = "black", fill = "steelblue") +
  theme_bw() +
  theme(axis.text.x = element_text(angle = 45))

# Cantidad de productos segund tipo de proyecto
catalogo_especificaciones_operaciones |> 
  group_by(tipo_proyecto) |> 
  summarise(
    n = n_distinct(codigo_producto)
  ) |> 
  ggplot() +
  aes(x = tipo_proyecto, y = n) +
  geom_col(color = "black", fill = "steelblue") +
  theme_bw() +
  theme(axis.text.x = element_text(angle = 45))

# Distribución de las dimensiones de las cajas
catalogo_especificaciones_operaciones |> 
  ggplot() +
  aes(x = caja_interior_largo) +
  geom_density() +
  theme_bw()

catalogo_especificaciones_operaciones |> 
  ggplot() +
  aes(x = caja_interior_ancho) +
  geom_density() +
  theme_bw()

catalogo_especificaciones_operaciones |> 
  ggplot() +
  aes(x = caja_interior_alto) +
  geom_density() +
  theme_bw()

# Distribución de la utilización del pallet
catalogo_especificaciones_operaciones |> 
  ggplot() +
  aes(y = utilizacion) +
  geom_boxplot(fill = "steelblue") +
  theme_bw()

# Distribución de la utilización del pallet según categoría de producto
catalogo_especificaciones_operaciones |> 
  ggplot() +
  aes(x = factor(categoria), y = utilizacion) +
  geom_boxplot(fill = "steelblue") +
  theme_bw() +
  theme(axis.text.x = element_text(angle = 90))

# Distribución de la utilización del pallet según tipo de proyecto
catalogo_especificaciones_operaciones |> 
  ggplot() +
  aes(x = factor(tipo_proyecto), y = utilizacion) +
  geom_boxplot(fill = "steelblue") +
  theme_bw() +
  theme(axis.text.x = element_text(angle = 90))

# Cruces de las dimensiones de las cajas
plot_ly(data = especificaciones_caja, x = ~caja_interior_ancho, y = ~caja_interior_largo, z = ~caja_interior_alto,
        type = 'scatter3d', mode = 'markers')

# Grosor de la caja que mayor soporta el peso de las cargas
catalogo_especificaciones_operaciones |> 
  group_by(caja_grosor_mm) |> 
  summarise(
    n = n_distinct(codigo_producto),
    cumple_resistencia = sum(cumple_resistencia)
  )

# Distribución del peso de las capas superiores
percentiles_peso_capas_superiores <- quantile(catalogo_especificaciones_operaciones$peso_capas_superiores_kg,
                                              probs = seq(0.1, 1, 0.1))

# Analisis del perimetro de las cajas
perimetro_cajas <- catalogo_especificaciones_operaciones |> 
  group_by(perimetro_caja_m) |> 
  summarise(
    n = n_distinct(caja_tipo_id)
  )

# Peso max con los grosores permitidos
carga_max_3mm_grosor <- perimetro_cajas$perimetro_caja_m * 1000 / G
carga_max_4.5mm_grosor <- perimetro_cajas$perimetro_caja_m * 1400 / G
carga_max_5mm_grosor <- perimetro_cajas$perimetro_caja_m * 1650 / G

######################### EDA Asociado al costo total #########################
# Costo total por planta
costo_por_planta <- colSums(catalogo_especificaciones_operaciones |> select(costo_total_planta_bakersfield,
                                                                            costo_total_planta_buenos_aires,
                                                                            costo_total_planta_curitiba,
                                                                            costo_total_planta_monterrey,
                                                                            costo_total_planta_santiago))

# Costo total de todos los productos vendidos en la situación actual
costo_total_actual <- sum(catalogo_especificaciones_operaciones$costo_total)
cat("El costo total de la situación actual es de:", costo_total_actual, "USD")

# Representación del costo total por planta
representacion_costo_por_planta_actual <- round(costo_por_planta/costo_total_actual, 4)

