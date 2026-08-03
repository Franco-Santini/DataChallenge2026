# Librerias a utilizar
library(dplyr)
library(tidyr)
library(stringr)

# Conjuntos de datos
catalogo <- read.csv("Data/catalogo_productos.csv")
especificaciones_caja <- read.csv("Data/especificaciones_cajas.csv")
operaciones <- read.csv("Data/operaciones_planta.csv")
procurement <- read.csv("Data/procurement_cajas.csv")

## Tabla ECT (N/m) por grosor de cartón para calcular carga max
ect_tabla <- tibble(
  grosor = c(2.5, 2.7, 3.0, 4.1, 4.5, 4.6, 4.7, 4.8, 5.0),
  ect_n_m = c(600, 730, 1000, 1200, 1400, 1450, 1500, 1550, 1650)
)

G <- 9.81 # Constante 

# Tabla precio base x grosor
precio_base_grosor <- tibble(
  grosor = c(3.0, 4.5, 5.0),
  precio_base_usd = c(0.60, 0.65, 0.70)
)

## Verificar datos faltantes en todos los data sets
colSums(is.na(catalogo)) # Tiene datos faltantes 
colSums(is.na(especificaciones_caja)) # Tiene datos faltantes
colSums(is.na(operaciones)) # No tiene datos faltantes
colSums(is.na(procurement)) # No tiene datos faltantes

###############------------- Completamos el conjunto de datos de catalogo -------------###############
# Seleccionar columnas de utilidad y filtrar por cantidad_paquetes faltantes
paquetes_faltantes <- catalogo |> 
  select(codigo_producto, tamaño_paquete, cantidad_paquetes) |> 
  filter(is.na(cantidad_paquetes))

# Seleccionar columnas de utilidad y filtrar por peso_neto_paquete faltante
peso_neto_faltantes <- catalogo |> 
  select(codigo_producto, tamaño_paquete, peso_neto_paquete) |> 
  filter(is.na(peso_neto_paquete))

# Extraemos la cantidad de paquetes dentro de la columna tamaño paquete
cant_paq_faltantes <- data.frame(
  codigo_producto = paquetes_faltantes$codigo_producto,
  cantidad_paquetes = as.numeric(str_extract(paquetes_faltantes$tamaño_paquete, "^\\d+"))
  )

# Reemplazamos la cantidad de paquetes con los datos completos
paquetes_faltantes <- paquetes_faltantes |>
  select(codigo_producto, tamaño_paquete) |> 
  left_join(cant_paq_faltantes, by = "codigo_producto")

# Extraemos el peso_neto_paquete dentro de la columna tamaño paquete
peso_neto_falt <- data.frame(
  codigo_producto = peso_neto_faltantes$codigo_producto,
  peso_neto_paquete = (peso_neto_faltantes$tamaño_paquete |>
  str_extract("\\d+[,.]?\\d*(?=\\s*[Kk][Gg])") |>
  str_replace(",", ".") |>
  as.numeric())
  )

# Reemplazamos el peso_neto_paquete con los datos completos
peso_neto_faltantes <- peso_neto_faltantes |> 
  select(codigo_producto, tamaño_paquete) |> 
  left_join(peso_neto_falt, by = "codigo_producto")

# Reemplazamos en el dataframe de catalogo la cantidad de paquetes faltantes
catalogo <- catalogo |> 
  left_join(paquetes_faltantes, by = "codigo_producto", suffix = c("", "_cat")) |> 
  mutate(
    cantidad_paquetes = coalesce(cantidad_paquetes, cantidad_paquetes_cat),
    tamaño_paquete = coalesce(tamaño_paquete, tamaño_paquete_cat)
  ) |> 
  select(-ends_with("_cat"))

# Reemplazamos en el dataframe de catalogo la cantidad de peso_neto_paquete faltantes
catalogo <- catalogo |> 
  left_join(peso_neto_faltantes, by = "codigo_producto", suffix = c("", "_cat")) |> 
  mutate(
    peso_neto_paquete = coalesce(peso_neto_paquete, peso_neto_paquete_cat),
    tamaño_paquete = coalesce(tamaño_paquete, tamaño_paquete_cat)
  ) |> 
  select(-ends_with("_cat"))

# Verificamos que no haya datos faltantes
colSums(is.na(catalogo)) # No hay más datos faltantes

###############------------- Completamos el conjunto de datos de especificaciones de cajas -------------###############
# Seleccionar columnas de utilidad y filtrar por cantidad_cajas_total faltantes
total_cajas_faltantes <- especificaciones_caja |> 
  select(caja_tipo_id, cantidad_cajas_alto, cantidad_cajas_largo, cantidad_cajas_ancho, cantidad_cajas_total) |> 
  filter(is.na(cantidad_cajas_total)) |> 
  mutate(cantidad_cajas_total = cantidad_cajas_alto * cantidad_cajas_largo * cantidad_cajas_ancho)

# Reemplazamos las cajas faltantes con los totales
especificaciones_caja <- especificaciones_caja |> 
  left_join(total_cajas_faltantes, by = "caja_tipo_id", suffix = c("", "_cat")) |> 
  mutate(
    cantidad_cajas_total = coalesce(cantidad_cajas_total, cantidad_cajas_total_cat)
  ) |> 
  select(-ends_with("_cat"))

# Modificamos caja_grosor_mm todo al mismo formato
especificaciones_caja <- especificaciones_caja |> 
  mutate(caja_grosor_mm = as.numeric(str_extract(caja_grosor_mm, "\\d[,.]\\d+") |> str_replace(",", ".")))

# Verificamos que no haya valores faltantes
colSums(is.na(especificaciones_caja)) # No hay mas valores faltantes

# Agregamos un ID más fácil y único para las cajas
especificaciones_caja <- especificaciones_caja |> 
  mutate(id_sencillo = seq(1, nrow(especificaciones_caja), 1)) |> 
  relocate(id_sencillo, .before = caja_tipo_id)

###############------------- Trabajamos sobre el conjunto de datos procurement -------------###############
# Función para dejar los descuentos en formato numérico
regex_pct <- function(x) {
  x |> 
    str_remove_all("%") |> 
    str_replace(",", ".") |> 
    str_remove_all("[^0-9\\.\\-]") |> 
    as.numeric()
}

# Plantas de operaciones
plantas <- c("buenos_aires", "curitiba", "santiago", "monterrey", "bakersfield")

# Aplicamos la función que encuentra expresiones regulares para pasar los descuentos de formato caracter a numérico
procurement2 <- procurement |> 
  mutate(across(all_of(paste0("descuento_planta_", plantas)), regex_pct)) |> 
  mutate(across(all_of(paste0("costo_unitario_planta_", plantas)), as.numeric))

# Filtrar por aquellos costos unitarios faltantes
costos_unitarios_faltantes <- procurement2 |> 
  filter(if_any(paste0("costo_unitario_planta_", plantas), is.na))

# Imputar aquellos costos unitarios faltantes por su valor correspondiente
costos_unitarios_faltantes <- costos_unitarios_faltantes |> 
  mutate(
    costo_unitario_planta_bakersfield = ifelse(is.na(costo_unitario_planta_bakersfield), costo_unitario_base * (1 + descuento_planta_bakersfield/100), costo_unitario_planta_bakersfield),
    costo_unitario_planta_buenos_aires = ifelse(is.na(costo_unitario_planta_buenos_aires), costo_unitario_base * (1 + descuento_planta_buenos_aires/100), costo_unitario_planta_buenos_aires),
    costo_unitario_planta_curitiba = ifelse(is.na(costo_unitario_planta_curitiba), costo_unitario_base * (1 + descuento_planta_curitiba/100), costo_unitario_planta_curitiba),
    costo_unitario_planta_santiago = ifelse(is.na(costo_unitario_planta_santiago), costo_unitario_base * (1 + descuento_planta_santiago/100), costo_unitario_planta_santiago),
    costo_unitario_planta_monterrey = ifelse(is.na(costo_unitario_planta_monterrey), costo_unitario_base * (1 + descuento_planta_monterrey/100), costo_unitario_planta_monterrey)
    ) |> 
  select(caja_tipo_id, costo_unitario_planta_bakersfield, costo_unitario_planta_buenos_aires, costo_unitario_planta_curitiba, costo_unitario_planta_monterrey, costo_unitario_planta_santiago)

# Hacemos el join para poder cambiar los valores "ERROR" por su respectivo valor
procurement2 <- procurement2 |> 
  left_join(costos_unitarios_faltantes, by = "caja_tipo_id", suffix = c("", "_cat")) |> 
  mutate(
    costo_unitario_planta_bakersfield = coalesce(costo_unitario_planta_bakersfield, costo_unitario_planta_bakersfield_cat),
    costo_unitario_planta_buenos_aires = coalesce(costo_unitario_planta_buenos_aires, costo_unitario_planta_buenos_aires_cat),
    costo_unitario_planta_curitiba = coalesce(costo_unitario_planta_curitiba, costo_unitario_planta_curitiba_cat),
    costo_unitario_planta_santiago = coalesce(costo_unitario_planta_santiago, costo_unitario_planta_santiago_cat),
    costo_unitario_planta_monterrey = coalesce(costo_unitario_planta_monterrey, costo_unitario_planta_monterrey_cat),
  ) |> 
  select(-ends_with("_cat"))

###############------------- Feature Engineering a nivel Caja -------------###############
# Crear algunas variables que puedan resultar de interes
especificaciones_caja <- especificaciones_caja |> 
  mutate(
    volumen_interior_caja_mm3 = caja_interior_largo * caja_interior_ancho * caja_interior_alto,
    volumen_exterior_caja_mm3 = caja_exterior_largo * caja_exterior_ancho * caja_exterior_alto,
    volumen_pallet_mm3 = pallet_largo * pallet_ancho * pallet_alto,
    perimetro_caja_m = 2 * (caja_exterior_largo + caja_exterior_ancho) / 1000,
    headspace_max_pct = case_when(
      caja_grosor_mm <= 3.0 ~ 0.06,
      caja_grosor_mm <= 4.5 ~ 0.08,
      TRUE ~ 0.10
    )
  ) |> 
  left_join(ect_tabla, by = c("caja_grosor_mm" = "grosor")) |> 
  mutate(carga_max_kg = ect_n_m * perimetro_caja_m / G)

###############------------- Join de las bases catalogo y especificaciones de la caja -------------###############
catalogo_especificaciones <- catalogo |> 
  left_join(especificaciones_caja, by = "caja_tipo_id")

###############------------- Join de las bases catalogo, especificaciones de la caja y procurement -------------###############
catalogo_especificaciones_procurement <- catalogo |> 
  left_join(especificaciones_caja, by = "caja_tipo_id") |> 
  left_join(procurement2, by = "caja_tipo_id")

###############------------- Join de las bases especificaciones de la caja y procurement -------------###############
especificaciones_procurement <- especificaciones_caja |> 
  left_join(procurement2, by = "caja_tipo_id")

###############------------- Join de las bases catalogo y operaciones -------------###############
catalogo_operaciones <- catalogo |> 
  left_join(operaciones, by = "codigo_producto")

###############------------- Join de las bases catalogo, especificaciones de la caja y operaciones -------------###############
catalogo_especificaciones_operaciones <- catalogo |> 
  left_join(especificaciones_caja, by = "caja_tipo_id") |> 
  left_join(operaciones, by = "codigo_producto") |> 
  mutate(
    capas_apiladas = cantidad_cajas_alto,
    peso_capas_superiores_kg = peso_neto_caja * pmax(capas_apiladas - 1, 0),
    cumple_resistencia = carga_max_kg >= peso_capas_superiores_kg,
    utilizacion_cajas = volumen_producto_total / volumen_interior_caja_mm3
  )

###############------------- Guardamos los datos para su posterior uso -------------###############
write.csv(procurement2, "Datos modificados/procurement_modificado.csv", row.names = FALSE)
write.csv(catalogo_especificaciones_operaciones, "Datos modificados/catalogo_especificaciones_operaciones.csv", row.names = FALSE)
write.csv(especificaciones_caja, "Datos modificados/especificaciones_caja.csv", row.names = FALSE)
write.csv(catalogo_especificaciones, "Datos modificados/catalogo_especificaciones.csv", row.names = FALSE)
write.csv(catalogo_especificaciones_procurement, "Datos modificados/catalogo_especificaciones_procurement.csv", row.names = FALSE)
write.csv(especificaciones_procurement, "Datos modificados/especificaciones_procurement.csv", row.names = FALSE)
write.csv(catalogo_operaciones, "Datos modificados/catalogo_operaciones.csv", row.names = FALSE)