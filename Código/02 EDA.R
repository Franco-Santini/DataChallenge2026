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

# Porcentajes de utilización del pallet
cuadrados_porcentaje <- function(porcentajes, etiquetas = NULL, espacio = 0.4, titulo = "") {
  
  n <- length(porcentajes)
  if (is.null(etiquetas)) etiquetas <- paste0("Item ", 1:n)
  
  shapes_list <- list()
  annotations_list <- list()
  
  for (i in seq_len(n)) {
    
    porcentaje <- max(0, min(100, porcentajes[i]))
    frac <- porcentaje / 100
    offset <- (i - 1) * (1 + espacio)
    
    shapes_list[[length(shapes_list) + 1]] <- list(
      type = "rect",
      x0 = offset, x1 = offset + 1, y0 = 0, y1 = 1,
      fillcolor = "gray90",
      line = list(color = "black", width = 2)
    )
    
    shapes_list[[length(shapes_list) + 1]] <- list(
      type = "rect",
      x0 = offset + 0.5 - frac/2, x1 = offset + 0.5 + frac/2,
      y0 = 0.5 - frac/2, y1 = 0.5 + frac/2,
      fillcolor = "steelblue",
      line = list(width = 0)
    )
    
    annotations_list[[length(annotations_list) + 1]] <- list(
      x = offset + 0.5, y = 0.5, text = paste0(round(porcentaje), "%"),
      showarrow = FALSE, font = list(size = 17, color = "black")
    )
    
    annotations_list[[length(annotations_list) + 1]] <- list(
      x = offset + 0.5, y = -0.2, text = etiquetas[i],
      showarrow = FALSE, font = list(size = 14, color = "black")
    )
  }
  
  plot_ly() %>%
    layout(
      title = titulo,
      xaxis = list(range = c(-0.3, (n - 1) * (1 + espacio) + 1.3),
                   showgrid = FALSE, zeroline = FALSE, showticklabels = FALSE,
                   scaleanchor = "y"),
      yaxis = list(range = c(-0.4, 1.3),
                   showgrid = FALSE, zeroline = FALSE, showticklabels = FALSE),
      shapes = shapes_list,
      annotations = annotations_list,
      margin = list(l = 20, r = 20, t = 50, b = 20)
    )
}

prom_uti_pallet = mean(catalogo_especificaciones_operaciones$utilizacion)

cuadrados_porcentaje(
  porcentajes = prom_uti_pallet * 100,
  etiquetas = "Total",
  titulo = list(
    text = "Utilización promedio del pallet",
    font = list(size = 17, color = "black"),
    x = 0.5
  )
)

# Porcentajes de utilización del pallet por categoria
uti_pallet <- catalogo_especificaciones_operaciones %>%
  group_by(categoria) %>%
  summarise(promedio = mean(utilizacion, na.rm = TRUE)) %>%
  ungroup()

cuadrados_porcentaje(
  porcentajes = uti_pallet$promedio * 100,
  etiquetas = uti_pallet$categoria,
  titulo = list(
    text = "Utilización promedio del pallet por categoría",
    font = list(size = 17, color = "black"),
    x = 0.5
  )
)

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

