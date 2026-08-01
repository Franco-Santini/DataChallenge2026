library(dplyr)
library(ggplot2)
library(plotly)
library(tidyr)
library(igraph)
library(scales)
library(forcats)
library(ggridges)
library(readr)

catalogo_especificaciones_operaciones <- read.csv("Datos modificados/catalogo_especificaciones_operaciones.csv")
compat <- readRDS("Datos modificados/compatibilidad_producto_caja.rds")

compat_ok <- compat %>%
  filter(compatible == TRUE)

# Para un grosor a la vez (arrancá con uno, ej. 3, para prototipar)
compat_g <- compat_ok %>% filter(grosor == 3)

# df con el id del producto y una lista con todas las cajas candidatas que sirven ese producto
cajas_por_producto <- compat_g %>%
  group_by(codigo_producto) %>%
  summarise(cajas_validas = list(caja_tipo_id))

#Clustering

# --- Orden de procesamiento: por volumen de venta descendente ---
# (asumiendo que volumen_producto_total está en catalogo_especificaciones_operaciones)
volumen_producto <- catalogo_especificaciones_operaciones %>%
  distinct(codigo_producto, volumen_producto_total) %>%
  arrange(desc(volumen_producto_total))

# vector con nombre: producto -> vector de cajas_tipo_id validas
cajas_validas_list <- setNames(cajas_por_producto$cajas_validas, cajas_por_producto$codigo_producto)

# orden final, descartando productos que no aparecieron en compat_g (no deberian existir, pero por las dudas)
orden <- volumen_producto$codigo_producto[volumen_producto$codigo_producto %in% names(cajas_validas_list)]

# --- Greedy con interseccion acumulada ---
clusters <- list()

for (p in orden) {
  candidatas_p <- cajas_validas_list[[p]]
  asignado <- FALSE
  
  if (length(clusters) > 0) {
    for (i in seq_along(clusters)) {
      interseccion <- intersect(clusters[[i]]$cajas_posibles, candidatas_p)
      if (length(interseccion) > 0) {
        clusters[[i]]$productos      <- c(clusters[[i]]$productos, p)
        clusters[[i]]$cajas_posibles <- interseccion   # se achica, nunca crece
        asignado <- TRUE
        break
      }
    }
  }
  
  if (!asignado) {
    clusters[[length(clusters) + 1]] <- list(
      productos      = p,
      cajas_posibles = candidatas_p
    )
  }
}

# --- Resumen rapido ---
n_clusters   <- length(clusters)
tam_clusters <- sapply(clusters, function(cl) length(cl$productos))

cat("Productos procesados:", length(orden), "\n")
cat("Tipos de caja resultantes:", n_clusters, "\n")
cat("Tamaños de cluster (desc):\n")
print(sort(tam_clusters, decreasing = TRUE))


# --- Recalcula la capacidad real de pallet para un grosor dado (no usa la columna vieja) ---
recalcular_cajas_pallet <- function(L_int, W_int, H_int, grosor) {
  L_ext <- L_int + 2*grosor
  W_ext <- W_int + 2*grosor
  H_ext <- H_int + 2*grosor
  cajas_alto  <- floor(1800 / H_ext)
  cajas_largo <- floor(800  / L_ext)   # largo de la caja alineado al lado corto del pallet (Restriccion #19)
  cajas_ancho <- floor(1200 / W_ext)
  cajas_alto * cajas_largo * cajas_ancho
}

elegir_caja_cluster <- function(cl, especificaciones, grosor) {
  especificaciones %>%
    filter(caja_tipo_id %in% cl$cajas_posibles) %>%
    mutate(
      cantidad_cajas_total_real = recalcular_cajas_pallet(
        caja_interior_largo, caja_interior_ancho, caja_interior_alto, grosor
      )
    ) %>%
    arrange(desc(cantidad_cajas_total_real)) %>%
    slice(1)
}

grosor_elegido <- 3   # el mismo que usaste en esta corrida

asignacion_final <- bind_rows(lapply(seq_along(clusters), function(i) {
  cl <- clusters[[i]]
  caja_elegida <- elegir_caja_cluster(
    cl,
    catalogo_especificaciones_operaciones %>% distinct(caja_tipo_id, .keep_all = TRUE),
    grosor_elegido
  )
  tibble(
    codigo_producto = cl$productos,
    cluster_id      = i,
    caja_tipo_id    = caja_elegida$caja_tipo_id
  )
}))

asignacion_final_csv <- asignacion_final %>% 
  left_join(
    catalogo_especificaciones_operaciones %>% 
      select(caja_tipo_id, caja_interior_alto, caja_interior_ancho, caja_interior_largo) %>% 
      distinct(caja_tipo_id, .keep_all = TRUE),
    by = "caja_tipo_id"
  ) %>% mutate(caja_grosor_mm = 3, 
               caja_exterior_alto = (caja_grosor_mm*2)+caja_interior_alto,
               caja_exterior_ancho = (caja_grosor_mm*2)+caja_interior_ancho,
               caja_exterior_largo = (caja_grosor_mm*2)+caja_interior_largo)

resultado1_simon = asignacion_final_csv %>% select(codigo_producto, caja_grosor_mm, caja_exterior_largo, caja_exterior_ancho, caja_exterior_alto)

write_csv(resultado1_simon, "resultado1_simon.csv")

