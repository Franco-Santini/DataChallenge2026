library(dplyr)
library(ggplot2)
library(plotly)
library(tidyr)
library(igraph)

catalogo_especificaciones_operaciones <- read.csv("Datos modificados/catalogo_especificaciones_operaciones.csv")

grosores_std <- tibble(
  grosor  = c(3.0, 4.5, 5.0),
  ect     = c(1000, 1400, 1650),   # N/m, tabla de la consigna
  pct_hs  = c(0.06, 0.08, 0.10)    # % headspace máximo según grosor
)

# codigo_producto × caja_tipo_id (todas las posibles) × grosor (3.0 / 4.5 / 5.0)

producto_dims = catalogo_especificaciones_operaciones %>% mutate(
                                                               codigo_producto,
                                                               L_prod = caja_interior_largo,
                                                               W_prod = caja_interior_ancho,
                                                               H_prod = caja_interior_alto,
                                                               peso_neto_caja,
                                                               .keep = "none"
                                                              )
caja_candidatas = catalogo_especificaciones_operaciones %>% 
                                              distinct(caja_tipo_id, .keep_all = TRUE) %>%
                                              mutate(
                                                caja_tipo_id,
                                                L_int = caja_interior_largo,
                                                W_int = caja_interior_ancho,
                                                H_int = caja_interior_alto,
                                                .keep = "none"
                                              )

#Creo una base de 427x204x3 con todas las combinaciones posibles de productos, cajas existentes (en caso de no encontrar la solución óptima, podríamos probar con cajas inexistentes) y grosores

combos <- producto_dims %>%
  crossing(caja_candidatas) %>%
  crossing(grosores_std)


#Armo la matriz de compatibilidad, donde se chequea si los productos podrían
#ser utilizados en cada una de las cajas en base a las restricciones.

# compat <- combos %>%
#   mutate(
#     # exteriores recalculados para ESTE grosor (no el original del archivo)
#     L_ext = L_int + 2*grosor,
#     W_ext = W_int + 2*grosor,
#     H_ext = H_int + 2*grosor,
#     
#     # 1) Fit +-10% por eje (comparación eje a eje, sin rotar)
#     fit_L = L_int >= 0.9*L_prod & L_int <= 1.1*L_prod,
#     fit_W = W_int >= 0.9*W_prod & W_int <= 1.1*W_prod,
#     fit_H = H_int >= 0.9*H_prod & H_int <= 1.1*H_prod,
#     fit_ok = fit_L & fit_W & fit_H,
#     
#     # 2) Volumen interno >= volumen del producto
#     vol_prod = L_prod*W_prod*H_prod,
#     vol_cand = L_int*W_int*H_int,
#     volumen_ok = vol_cand >= vol_prod,
#     
#     # 3) Headspace máximo (solo aplica al lado que CRECE; si se achica, no se evalúa)
#     hs_L = ifelse(L_int > L_prod, (L_int - L_prod) <= pmin(pct_hs*L_prod, 40), TRUE),
#     L_min = pmin(pct_hs*L_prod, 40),
#     hs_W = ifelse(W_int > W_prod, (W_int - W_prod) <= pmin(pct_hs*W_prod, 40), TRUE),
#     W_min = pmin(pct_hs*W_prod, 40),
#     hs_H = ifelse(H_int > H_prod, (H_int - H_prod) <= pmin(pct_hs*H_prod, 40), TRUE),
#     H_min = pmin(pct_hs*H_prod, 40),
#     headspace_ok = hs_L & hs_W & hs_H,
#     
#     # 4) Resistencia a compresion (ECT recalculado para este grosor)
#     capas_alto   = floor(1800 / H_ext),
#     perimetro_m  = 2*(L_ext + W_ext) / 1000,
#     carga_max    = ect * perimetro_m / 9.81,
#     peso_encima  = pmax(capas_alto - 1, 0) * peso_neto_caja,
#     resistencia_ok = carga_max >= peso_encima,
#     
#     # chequeo final
#     compatible = fit_ok & volumen_ok & headspace_ok & resistencia_ok
#   ) %>%
#   select(codigo_producto, caja_tipo_id, L_min, W_min, H_min, grosor, fit_ok, volumen_ok,
#          headspace_ok, resistencia_ok, compatible)

#saveRDS(compat, "Datos_modificados/compatibilidad_producto_caja.rds")

compat <- readRDS("Datos modificados/compatibilidad_producto_caja.rds")

#Primeras impresiones

# El grosor es necesario para poder cumplir el requisito de resistencia de las cajas, y vemos que se cumple siempre para cualquier grosor
# Pero también sirve para el Headspace, a mayor grosor se permite un mayor headspace.

# Haría un gráfico de como las distintas restricciones van limitando la cantidad de combinaciones producto*caja

#de las 427*204*3 combinaciones iniciales después del +-10% quedaron tantas, después del volúmen quedaron tantas, después del headspace quedaron tantas y por último la restricción de la resistencia no te limita nada.

#Un heatmap de una muestra podría ser para "mostrar" como funciona la matriz

# La ditribución de en cuantas cajas entraría cada producto y de cuantos productos entrarían en cada caja





















compat_ok <- compat %>%
  filter(compatible == TRUE)

# Para un grosor a la vez (arrancá con uno, ej. 3, para prototipar)
compat_g <- compat_ok %>% filter(grosor == 3)

# df con el id del producto y una lista con todas las cajas candidatas que sirven ese producto
cajas_por_producto <- compat_g %>%
  group_by(codigo_producto) %>%
  summarise(cajas_validas = list(caja_tipo_id))

# Pares de productos que comparten al menos una caja candidata
pares_compatibles <- compat_g %>%
  select(codigo_producto, caja_tipo_id) %>%
  inner_join(compat_g %>% select(codigo_producto, caja_tipo_id),
             by = "caja_tipo_id", relationship = "many-to-many") %>%
  filter(codigo_producto.x < codigo_producto.y) %>%   # evitar duplicados y auto-pares
  distinct(codigo_producto.x, codigo_producto.y)

g = graph_from_data_frame(pares_compatibles, directed = FALSE)
comm <- cluster_louvain(g)
plot(comm, g)
