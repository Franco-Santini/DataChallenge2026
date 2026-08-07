# Librerias
library(dplyr)
library(tidyr)
library(purrr)
library(stringr)

# Lectura de los conjuntos de datos
asignacion_producto_cluster <- read.csv("outputs/entrega_kaggle_optimo_10.csv")
procurement <- read.csv("Datos modificados/procurement_modificado.csv")
especificaciones_caja <- read.csv("Datos modificados/especificaciones_caja.csv")
catalogo_especificaciones_operaciones <- read.csv("Datos modificados/catalogo_especificaciones_operaciones.csv")

#
asignacion_producto_cluster <- asignacion_producto_cluster |> 
  mutate(caja_interior_largo = caja_exterior_largo - 2*caja_grosor_mm,
         caja_interior_ancho = caja_exterior_ancho - 2*caja_grosor_mm,
         caja_interior_alto = caja_exterior_alto - 2*caja_grosor_mm) |> 
  mutate(perimetro_caja_m = 2 * (caja_exterior_largo + caja_exterior_ancho) / 1000,
         cantidad_cajas_alto = floor(1800 / caja_exterior_alto),
         cantidad_cajas_largo = floor(800 / caja_exterior_largo),
         cantidad_cajas_ancho = floor(1200 / caja_exterior_ancho)) |> 
  mutate(cantidad_cajas_total = cantidad_cajas_alto * cantidad_cajas_largo * cantidad_cajas_ancho) |> 
  mutate(utilizacion = cantidad_cajas_total * (caja_exterior_largo * caja_exterior_ancho * caja_exterior_alto) /
           (1200 * 800 * 1800))

# Cantidad de cajas distintas
asignacion_producto_cluster <- asignacion_producto_cluster |> 
  group_by(caja_exterior_largo, caja_exterior_ancho, caja_exterior_alto) |> 
  mutate(caja_tipo_id = cur_group_id()) |> 
  ungroup()

# Asignación producto cluster join con operaciones
asignacion_producto_cluster_operaciones <- asignacion_producto_cluster |> 
  left_join(operaciones |> select(codigo_producto, volumen_producto_canal_servicios_comida, volumen_producto_canal_minorista,
                                  volumen_producto_canal_cadenas_corporativas, volumen_producto_canal_otros, volumen_producto_total,
                                  volumen_producto_planta_buenos_aires, volumen_producto_planta_curitiba, volumen_producto_planta_santiago,
                                  volumen_producto_planta_bakersfield, volumen_producto_planta_monterrey, cantidad_pallets_planta_buenos_aires,
                                  cantidad_pallets_planta_curitiba, cantidad_pallets_planta_santiago, cantidad_pallets_planta_monterrey,
                                  cantidad_pallets_planta_bakersfield, cantidad_pallets_total), by = "codigo_producto")

# Construcción de la base procurement optimizado
################################
volumenes_cluster <- asignacion_producto_cluster_operaciones |> 
  group_by(caja_tipo_id) |> 
  summarise(
    cantidad_productos = n_distinct(codigo_producto),
    volumen_producto_planta_buenos_aires = sum(volumen_producto_planta_buenos_aires),
    volumen_producto_planta_santiago = sum(volumen_producto_planta_santiago),
    volumen_producto_planta_curitiba = sum(volumen_producto_planta_curitiba),
    volumen_producto_planta_monterrey = sum(volumen_producto_planta_monterrey),
    volumen_producto_planta_bakersfield = sum(volumen_producto_planta_bakersfield),
    volumen_producto_total = sum(volumen_producto_total)
  )

procurement_optimizado <- volumenes_cluster |> 
  dplyr::transmute(
    caja_tipo_id,
    cantidad_productos,
    volumen_producto_total,
    volumen_tipo_planta_buenos_aires = cantidad_productos * volumen_producto_planta_buenos_aires,
    volumen_tipo_planta_curitiba = cantidad_productos * volumen_producto_planta_curitiba,
    volumen_tipo_planta_santiago = cantidad_productos * volumen_producto_planta_santiago,
    volumen_tipo_planta_monterrey = cantidad_productos * volumen_producto_planta_monterrey,
    volumen_tipo_planta_bakersfield = cantidad_productos * volumen_producto_planta_bakersfield
  )

# Creo la función descuento
descuento <- function(x) {
  case_when(
    x < 20000 ~ 10,
    x < 50000 ~ 0,
    x < 100000 ~ -10,
    x < 500000 ~ -20,
    TRUE ~ -30
  )
}

procurement_optimizado <- procurement_optimizado |> 
  mutate(costo_unitario_base = rep(0.6, nrow(procurement_optimizado))) |> 
  mutate(costo_total_base = volumen_producto_total * costo_unitario_base) |> 
  mutate(
    descuento_planta_buenos_aires = descuento(volumen_tipo_planta_buenos_aires/cantidad_productos),
    descuento_planta_curitiba = descuento(volumen_tipo_planta_curitiba/cantidad_productos),
    descuento_planta_santiago = descuento(volumen_tipo_planta_santiago/cantidad_productos),
    descuento_planta_monterrey = descuento(volumen_tipo_planta_monterrey/cantidad_productos),
    descuento_planta_bakersfield = descuento(volumen_tipo_planta_bakersfield/cantidad_productos)
  ) |> 
  mutate(
    costo_unitario_planta_buenos_aires = costo_unitario_base * (1 + descuento_planta_buenos_aires/100),
    costo_unitario_planta_curitiba = costo_unitario_base * (1 + descuento_planta_curitiba/100),
    costo_unitario_planta_santiago = costo_unitario_base * (1 + descuento_planta_santiago/100),
    costo_unitario_planta_monterrey = costo_unitario_base * (1 + descuento_planta_monterrey/100),
    costo_unitario_planta_bakersfield = costo_unitario_base * (1 + descuento_planta_bakersfield/100),
  ) |> 
  mutate(costo_por_pallet = rep(150, nrow(procurement_optimizado)))

################################
# Join asignacion_producto_cluster_operaciones con procurement
################################
asignacion_producto_cluster_procurement <- asignacion_producto_cluster_operaciones |> 
  left_join(procurement_optimizado |> select(-volumen_producto_total), by = "caja_tipo_id") |> 
  mutate(
    costo_total_planta_buenos_aires = volumen_producto_planta_buenos_aires * costo_unitario_planta_buenos_aires,
    costo_total_planta_curitiba = volumen_producto_planta_curitiba * costo_unitario_planta_curitiba,
    costo_total_planta_santiago = volumen_producto_planta_santiago * costo_unitario_planta_santiago,
    costo_total_planta_monterrey = volumen_producto_planta_monterrey * costo_unitario_planta_monterrey,
    costo_total_planta_bakersfield = volumen_producto_planta_bakersfield * costo_unitario_planta_bakersfield,
  ) |> 
  mutate(costo_total = costo_total_planta_buenos_aires + costo_total_planta_curitiba + costo_total_planta_santiago +
           costo_total_planta_monterrey + costo_total_planta_bakersfield) |> 
  mutate(
    cantidad_pallets_planta_buenos_aires = volumen_producto_planta_buenos_aires / cantidad_cajas_total,
    cantidad_pallets_planta_curitiba = volumen_producto_planta_curitiba / cantidad_cajas_total,
    cantidad_pallets_planta_santiago = volumen_producto_planta_santiago / cantidad_cajas_total,
    cantidad_pallets_planta_monterrey = volumen_producto_planta_monterrey / cantidad_cajas_total,
    cantidad_pallets_planta_bakersfield = volumen_producto_planta_bakersfield / cantidad_cajas_total,
  ) |> 
  mutate(
    cantidad_pallets_total = cantidad_pallets_planta_buenos_aires + cantidad_pallets_planta_curitiba +
      cantidad_pallets_planta_santiago + cantidad_pallets_planta_monterrey + cantidad_pallets_planta_bakersfield,
    costo_pallet_planta_buenos_aires = cantidad_pallets_planta_buenos_aires * 150,
    costo_pallet_planta_curitiba = cantidad_pallets_planta_curitiba * 150,
    costo_pallet_planta_santiago = cantidad_pallets_planta_santiago * 150,
    costo_pallet_planta_monterrey = cantidad_pallets_planta_monterrey * 150,
    costo_pallet_planta_bakersfield = cantidad_pallets_planta_bakersfield * 150,
  ) |> 
  mutate(
    costo_pallets_total = costo_pallet_planta_buenos_aires + costo_pallet_planta_curitiba + 
      costo_pallet_planta_santiago + costo_pallet_planta_monterrey + costo_pallet_planta_bakersfield
  )

# Ahorro conseguido
################################
costo_optimizado <- sum(asignacion_producto_cluster_procurement$costo_pallets_total) + sum(asignacion_producto_cluster_procurement$costo_total)
costo_total_sit_actual <- sum(catalogo_especificaciones_operaciones$costo_pallets_total) + sum(catalogo_especificaciones_operaciones$costo_total)
ahorro       <- costo_total_sit_actual - costo_optimizado
ahorro_pct   <- ahorro / costo_total_sit_actual * 100

cat("\nCosto actual (baseline):", format(costo_total_sit_actual, big.mark = ","), "USD\n")
cat("Ahorro estimado:", format(ahorro, big.mark = ","),
    "USD (", round(ahorro_pct, 2), "%)\n")

write.csv(asignacion_producto_cluster_procurement, "Datos modificados/asignacion_producto_cluster_procurement.csv", row.names = FALSE)

