library(dplyr)
library(ggplot2)
library(plotly)
library(tidyr)
library(igraph)
library(scales)
library(forcats)
library(ggridges)

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
                                                               .keep = "none" #deja solo las variables que elegimos
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
  tidyr::crossing(caja_candidatas) %>%
  tidyr::crossing(grosores_std)


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
#     hs_L = ifelse(L_int > L_prod, (L_int - L_prod) <= pmin(pct_hs*L_int, 40), TRUE),
#     L_min = pmin(pct_hs*L_prod, 40),
#     hs_W = ifelse(W_int > W_prod, (W_int - W_prod) <= pmin(pct_hs*W_int, 40), TRUE),
#     W_min = pmin(pct_hs*W_prod, 40),
#     hs_H = ifelse(H_int > H_prod, (H_int - H_prod) <= pmin(pct_hs*H_int, 40), TRUE),
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
# 
# saveRDS(compat, "Datos modificados/compatibilidad_producto_caja.rds")

#Una vez armada la matriz de compatibilidad vemos que, de 261.234 combinaciones posibles, solo 14.379 cumplen con todas las
#restricciones (5.5%).

compat <- readRDS("Datos modificados/compatibilidad_producto_caja.rds")

#Primeras impresiones

# El grosor es necesario para poder cumplir el requisito de resistencia de las cajas, y vemos que se cumple siempre para cualquier grosor
# Pero también sirve para el Headspace, a mayor grosor se permite un mayor headspace.

#Un heatmap de una muestra podría ser para "mostrar" como funciona la matriz

# La ditribución de en cuantas cajas entraría cada producto y de cuantos productos entrarían en cada caja


#1) De las 427x204x3 = 261.324 combinaciones posibles, se busca identificar cuales de ellas superan las restricciones
#   presentadas (fit, volumen, headspace y resistencia). Se encuentra que:
#   .)El filtro de fit elimina aproximadamente el 86% de las combinaciones.
#   .)Los grosores no influyen hasta evaluar el headspace; recién ahí comienza a observarse su efecto.
#   .)la resistencia no elimina ninguna combinación adicional entre aquellas que ya superaron fit, volumen y headspace


# Gráfico de embudo

etapas <- c(
  "Todas las combinaciones",
  "+ Fit ±10%",
  "+ Volumen",
  "+ Headspace",
  "+ Resistencia"
)

embudo_estatico <- compat %>%
  group_by(grosor) %>%
  summarise(
    `Todas las combinaciones` = n(),
    
    `+ Fit ±10%` =
      sum(fit_ok, na.rm = TRUE),
    
    `+ Volumen` =
      sum(fit_ok & volumen_ok, na.rm = TRUE),
    
    `+ Headspace` =
      sum(
        fit_ok &
          volumen_ok &
          headspace_ok,
        na.rm = TRUE
      ),
    
    `+ Resistencia` =
      sum(
        fit_ok &
          volumen_ok &
          headspace_ok &
          resistencia_ok,
        na.rm = TRUE
      ),
    
    .groups = "drop"
  ) %>%
  pivot_longer(
    cols = -grosor,
    names_to = "etapa",
    values_to = "combinaciones"
  ) %>%
  mutate(
    etapa = factor(etapa, levels = etapas),
    grosor = factor(
      grosor,
      levels = c(3, 4.5, 5),
      labels = c("Grosor: 3,0 mm", "Grosor: 4,5 mm", "Grosor: 5,0 mm")
    )
  ) %>%
  arrange(grosor, etapa) %>%
  group_by(grosor) %>%
  mutate(
    porcentaje = combinaciones / first(combinaciones),
    
    etiqueta = paste0(
      number(
        combinaciones,
        big.mark = ".",
        decimal.mark = ","
      ),
      " (",
      percent(
        porcentaje,
        accuracy = 0.1,
        decimal.mark = ","
      ),
      ")"
    ),
    
    # Centra cada barra para darle forma de embudo
    xmin = -combinaciones / 2,
    xmax =  combinaciones / 2,
    
    posicion = as.numeric(etapa),
    ymin = posicion - 0.38,
    ymax = posicion + 0.38
  ) %>%
  ungroup()

colores_etapas <- c(
  "Todas las combinaciones" = "#1565C0",
  "+ Fit ±10%"              = "#1976D2",
  "+ Volumen"               = "#00897B",
  "+ Headspace"             = "#43A047",
  "+ Resistencia"           = "#7CB342"
)

grafico_embudos <- ggplot(embudo_estatico) +
  
  geom_rect(
    aes(
      xmin = xmin,
      xmax = xmax,
      ymin = ymin,
      ymax = ymax,
      fill = etapa
    ),
    color = "white",
    linewidth = 1
  ) +
  
  geom_text(
    aes(
      x = 0,
      y = ymin - 0.14,
      label = etiqueta
    ),
    color = "#263238",
    fontface = "bold",
    lineheight = 0.9,
    size = 3.2,
    vjust = 1
  )+
  
  facet_wrap(
    ~grosor,
    nrow = 1
  ) +
  
  scale_y_reverse(
    breaks = seq_along(etapas),
    labels = etapas,
    expand = expansion(add = 0.5)
  ) +
  
  scale_x_continuous(
    limits = c(-45000, 45000),
    breaks = c(-40000, -20000, 0, 20000, 40000),
    labels = function(x) {
      number(
        abs(x),
        big.mark = ".",
        decimal.mark = ","
      )
    }
  ) +
  
  scale_fill_manual(
    values = colores_etapas,
    guide = "none"
  ) +
  
  labs(
    title = "Embudo de compatibilidad producto–caja",
    subtitle = paste0(
      "Cantidad de combinaciones que superan acumulativamente ",
      "cada restricción"
    ),
    x = "Cantidad de combinaciones",
    y = NULL,
    caption = paste0(
      "Cada escenario parte de 87.108 combinaciones producto–caja. ",
      "El porcentaje se calcula respecto del total inicial."
    )
  ) +
  
  theme_minimal(
    base_family = "Roboto",
    base_size = 11
  ) +
  
  theme(
    plot.title = element_text(
      face = "bold",
      size = 16,
      color = "#263238"
    ),
    
    plot.subtitle = element_text(
      size = 11,
      color = "#546E7A",
      margin = margin(b = 15)
    ),
    
    strip.text = element_text(
      face = "bold",
      size = 12,
      color = "#37474F"
    ),
    
    strip.background = element_rect(
      fill = "#ECEFF1",
      color = NA
    ),
    
    axis.text.y = element_text(
      face = "bold",
      color = "#455A64",
      size = 10
    ),
    
    axis.text.x = element_text(
      color = "#607D8B"
    ),
    
    panel.grid.major.y = element_blank(),
    panel.grid.minor = element_blank(),
    
    panel.spacing = unit(1.2, "lines"),
    
    plot.caption = element_text(
      color = "#78909C",
      hjust = 0,
      margin = margin(t = 12)
    )
  )

grafico_embudos


# Heatmap

# --- Filtrar al grosor que quieras mostrar (ejemplo: 3) ---
compat_grosor <- compat %>% filter(grosor == 3)

# --- Elegir una muestra legible: cajas "hub" (compatibles con más productos) ---
top_cajas <- compat_grosor %>%
  filter(compatible) %>%
  count(caja_tipo_id, sort = TRUE) %>%
  slice_head(n = 18) %>%
  pull(caja_tipo_id)

# --- y los productos más "flexibles" dentro de esas cajas ---
top_productos <- compat_grosor %>%
  filter(compatible, caja_tipo_id %in% top_cajas) %>%
  count(codigo_producto, sort = TRUE) %>%
  slice_head(n = 35) %>%
  pull(codigo_producto)

# --- armar la muestra final, con IDs cortos para que el eje x sea legible ---
muestra <- compat_grosor %>%
  filter(codigo_producto %in% top_productos, caja_tipo_id %in% top_cajas) %>%
  mutate(
    caja_id_corto  = paste0("k", as.integer(factor(caja_tipo_id, levels = top_cajas))),
    producto_f     = factor(codigo_producto, levels = top_productos),
    compatible_lbl = factor(compatible, levels = c(TRUE, FALSE),
                            labels = c("Compatible", "No compatible"))
  )

# --- el heatmap ---
ggplot(muestra, aes(x = caja_id_corto, y = fct_rev(producto_f), fill = compatible_lbl)) +
  geom_tile(color = "white", linewidth = 0.5) +
  scale_fill_manual(
    values = c("Compatible" = "#7CB342", "No compatible" = "#E53935"),
    name = NULL
  ) +
  labs(
    title    = "Matriz de compatibilidad producto–caja",
    subtitle = "Grosor 3 mm · muestra de 35 productos y 18 cajas candidatas",
    x = "Caja candidata",
    y = "Producto"
  ) +
  theme_minimal(base_size = 11) +
  theme(
    axis.text.x     = element_text(angle = 90, vjust = 0.5, hjust = 1, size = 8),
    axis.text.y     = element_text(size = 7),
    panel.grid      = element_blank(),
    plot.title      = element_text(face = "bold", size = 14),
    plot.subtitle   = element_text(color = "grey40", size = 10),
    legend.position = "top",
    legend.text     = element_text(size = 10)
  )

# Gráfico de cantidad de cajas compatibles para cada producto según grosor (flexibilidad de los productos)

# Para cada producto, cuento cuántas cajas candidatas compatibles tiene, y grafico la distribución para cada grosor.
# si la mayoría de los productos tiene 2-3 opciones nomás (catálogo "rígido", consolidación limitada) o si hay una cola larga de productos con 15-20+ opciones (catálogo "flexible", buen margen de consolidación). Esto también te avisa temprano si algún grosor es sistemáticamente mejor en este sentido — compará las 3 distribuciones superpuestas.

compat_ok <- compat %>%
  filter(compatible == TRUE)

prod_comp_cajas = compat_ok %>% group_by(codigo_producto, grosor) %>% summarise(Cantidad = n())

ggplot(data = prod_comp_cajas)+
  aes(x = Cantidad, fill = factor(grosor), y = factor(grosor))+
  geom_density_ridges(alpha=0.7) +
  theme_ridges() + 
  theme(legend.position = "none")

#A mayor grosor, las




































# grafos
# compat_ok <- compat %>%
#   filter(compatible == TRUE)
# 
# # Para un grosor a la vez (arrancá con uno, ej. 3, para prototipar)
# compat_g <- compat_ok %>% filter(grosor == 3)
# 
# # df con el id del producto y una lista con todas las cajas candidatas que sirven ese producto
# cajas_por_producto <- compat_g %>%
#   group_by(codigo_producto) %>%
#   summarise(cajas_validas = list(caja_tipo_id))
# 
# # Pares de productos que comparten al menos una caja candidata
# pares_compatibles <- compat_g %>%
#   select(codigo_producto, caja_tipo_id) %>%
#   inner_join(compat_g %>% select(codigo_producto, caja_tipo_id),
#              by = "caja_tipo_id", relationship = "many-to-many") %>%
#   filter(codigo_producto.x < codigo_producto.y) %>%   # evitar duplicados y auto-pares
#   distinct(codigo_producto.x, codigo_producto.y)
# 
# g = graph_from_data_frame(pares_compatibles, directed = FALSE)
# comm <- cluster_louvain(g)
# plot(comm, g)
