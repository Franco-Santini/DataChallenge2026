library(dplyr)
library(readr)

# =============================================================================
# HEURISTICA DE CLUSTERING ORIENTADA A COSTO TOTAL
#
# Objetivo: minimizar packaging + flete. No es un MIP, por lo que no garantiza
# el óptimo global: parte de una caja por SKU y fusiona, de a una, los pares de
# clusters cuya unión no aumenta el costo total.
#
# La consigna exige un ÚNICO grosor para todo el catálogo. Por eso el algoritmo
# resuelve tres problemas completos (3.0, 4.5 y 5.0 mm) y compara sus costos.
# =============================================================================

# clustering aglomerativo guiado por costos: empieza con una caja por producto y une dos grupos
# únicamente si usar una misma caja para ambos no aumenta el costo total.

productos <- read.csv("Datos modificados/catalogo_especificaciones_operaciones.csv") %>%
  distinct(codigo_producto, .keep_all = TRUE)

plantas <- c("buenos_aires", "curitiba", "santiago", "monterrey", "bakersfield")
col_volumen <- paste0("volumen_producto_planta_", plantas)

columnas_necesarias <- c(
  "codigo_producto", "peso_neto_caja",
  "caja_interior_largo", "caja_interior_ancho", "caja_interior_alto",
  col_volumen
)

if (!all(columnas_necesarias %in% names(productos))) {
  stop("Faltan columnas necesarias. Ejecutá primero 01 data_prep.R.")
}

# Según la aclaración de Slack, Kaggle evalúa únicamente envíos intra-región:
# no hay volumen extra-región. Por lo tanto, todos los pallets cuestan USD 150.
COSTO_PALLET <- 150
PALLET <- c(L = 800, W = 1200, H = 1800)
G <- 9.81
MARGEN_PALLET <- 1e-5  # evita quedar exactamente sobre un límite de floor()
TOL <- 1e-8

precio_base <- c("3" = 0.60, "4.5" = 0.65, "5" = 0.70)
ect <- c("3" = 1000, "4.5" = 1400, "5" = 1650)

clave_grosor <- function(grosor) {
  format(grosor, trim = TRUE, scientific = FALSE)
}

headspace_pct <- function(grosor) {
  if (grosor <= 3.0) return(0.06)
  if (grosor <= 4.5) return(0.08)
  0.10
}

factor_descuento <- function(volumen) {
  if (volumen < 20000) return(1.10)
  if (volumen < 50000) return(1.00)
  if (volumen < 100000) return(0.90)
  if (volumen < 500000) return(0.80)
  0.70
}

# Para un producto con dimensión original d0, una dimensión interna candidata d
# debe pertenecer a [0.9*d0, min(1.1*d0, d0/(1-h), d0+40)].
#
# La cota d0/(1-h) sale de despejar el headspace cuando d > d0:
# d - d0 <= h*d  =>  d <= d0/(1-h).
# Si d <= d0, no hay headspace positivo, pero sigue rigiendo el -10%.
limites_dimension <- function(d0, grosor) {
  h <- headspace_pct(grosor)
  list(
    inferior = 0.90 * d0,
    superior = pmin(1.10 * d0, d0 / (1 - h), d0 + 40)
  )
}

# Cada cluster guarda la intersección de las regiones factibles de sus SKUs.
# volumen_min es el mayor volumen original de los productos del cluster: la
# nueva caja debe ser suficiente para todos ellos.
crear_cluster <- function(fila, grosor) {
  d0 <- c(L = as.numeric(fila[["caja_interior_largo"]]),W = as.numeric(fila[["caja_interior_ancho"]]), H = as.numeric(fila[["caja_interior_alto"]]))
  limites <- limites_dimension(d0, grosor)

  demanda <- matrix(
    as.numeric(unlist(fila[col_volumen], use.names = FALSE)),
    nrow = 1,
    dimnames = list(as.character(fila[["codigo_producto"]]), plantas)
  )

  list(
    productos = as.character(fila[["codigo_producto"]]),
    limite_inferior = limites$inferior,
    limite_superior = limites$superior,
    volumen_min = prod(d0),
    peso_maximo = as.numeric(fila[["peso_neto_caja"]]),
    volumenes = demanda
  )
}

# Dado un patrón (nL, nW, nH), busca una caja válida que conserve esa cantidad
# de cajas por eje. Para cada eje, P/n - 2t es el mayor interior que todavía
# permite n cajas. Si con esas cotas superiores no entra el mayor volumen del
# cluster, ese patrón de pallet es imposible.
caja_para_patron <- function(cluster, grosor, nL, nW, nH) {
  n <- c(L = nL, W = nW, H = nH)
  maximo_por_pallet <- PALLET / n - 2 * grosor - MARGEN_PALLET
  inferior <- cluster$limite_inferior
  superior <- pmin(cluster$limite_superior, maximo_por_pallet)

  if (any(superior + TOL < inferior)) return(NULL)
  if (prod(superior) < cluster$volumen_min) return(NULL)

  # Entre el extremo inferior y el superior existe una caja de volumen exacto
  # (salvo que el inferior ya alcance). Elegimos una expansión proporcional para
  # no privilegiar arbitrariamente una dimensión.
  if (prod(inferior) >= cluster$volumen_min) {
    dimensiones <- inferior
  } else if (prod(superior) == cluster$volumen_min) {
    dimensiones <- superior
  } else {
    f <- function(alpha) prod(inferior + alpha * (superior - inferior))
    alpha <- uniroot(
      function(alpha) f(alpha) - cluster$volumen_min,
      interval = c(0, 1), tol = 1e-12
    )$root
    # Se avanza un margen infinitesimal sobre la raíz para no quedar debajo del
    # volumen mínimo por el redondeo numérico de uniroot().
    alpha <- min(1, alpha + 1e-10)
    dimensiones <- inferior + alpha * (superior - inferior)
  }

  exterior <- dimensiones + 2 * grosor
  cajas_eje <- floor(PALLET / exterior + TOL)
  capacidad <- prod(cajas_eje)

  if (capacidad < 1) return(NULL)

  # La verificación se hace otra vez con los n reales que genera la caja,
  # porque una dimensión elegida por debajo de la cota puede habilitar más cajas.
  perimetro_m <- 2 * (exterior["L"] + exterior["W"]) / 1000
  carga_maxima <- ect[[clave_grosor(grosor)]] * perimetro_m / G
  peso_encima <- (cajas_eje["H"] - 1) * cluster$peso_maximo

  if (carga_maxima + TOL < peso_encima) return(NULL)

  list(
    dimensiones = dimensiones,
    exterior = exterior,
    cajas_eje = cajas_eje,
    capacidad = capacidad,
    carga_maxima = carga_maxima
  )
}

# Enumera todos los patrones enteros de pallet factibles en el rectángulo de
# dimensiones del cluster. Como el flete no aumenta al subir la capacidad,
# devuelve la caja de mayor capacidad. En empates conserva la de menor volumen.
mejor_caja_pallet <- function(cluster, grosor) {
  max_cajas_eje <- floor(PALLET / (cluster$limite_inferior + 2 * grosor))
  if (any(max_cajas_eje < 1)) return(NULL)

  mejor <- NULL

  for (nL in seq_len(max_cajas_eje["L"])) {
    for (nW in seq_len(max_cajas_eje["W"])) {
      for (nH in seq_len(max_cajas_eje["H"])) {
        candidata <- caja_para_patron(cluster, grosor, nL, nW, nH)
        if (is.null(candidata)) next

        if (is.null(mejor) ||
            candidata$capacidad > mejor$capacidad ||
            (candidata$capacidad == mejor$capacidad &&
             prod(candidata$dimensiones) < prod(mejor$dimensiones))) {
          mejor <- candidata
        }
      }
    }
  }
  mejor
}

# Costea un cluster. Los pallets se redondean por SKU y por planta porque la
# consigna prohíbe mezclar productos dentro de un pallet. En cambio, el tier de
# packaging se calcula sobre todo el volumen del tipo de caja en cada planta.
evaluar_cluster <- function(cluster, grosor) {
  caja <- mejor_caja_pallet(cluster, grosor)
  if (is.null(caja)) return(NULL)

  pallets_sku_planta <- ceiling(cluster$volumenes / caja$capacidad)
  pallets_planta <- colSums(pallets_sku_planta)
  costo_flete <- sum(pallets_planta) * COSTO_PALLET

  volumen_planta <- colSums(cluster$volumenes)
  costo_packaging <- sum(
    volumen_planta * precio_base[[clave_grosor(grosor)]] *
      vapply(volumen_planta, factor_descuento, numeric(1))
  )

  c(cluster, list(
    dimensiones = caja$dimensiones,
    exterior = caja$exterior,
    capacidad_pallet = caja$capacidad,
    cajas_eje = caja$cajas_eje,
    pallets_planta = pallets_planta,
    costo_packaging = costo_packaging,
    costo_flete = costo_flete,
    costo_total = costo_packaging + costo_flete
  ))
}

# Filtro barato previo a la enumeración de patrones de pallet. Es sólo una
# condición necesaria, pero descarta enseguida los pares sin intersección
# geométrica o sin volumen disponible para el producto más voluminoso.
prechequear_fusion <- function(a, b) {
  inferior <- pmax(a$limite_inferior, b$limite_inferior)
  superior <- pmin(a$limite_superior, b$limite_superior)

  !any(inferior > superior + TOL) &&
    prod(superior) + TOL >= max(a$volumen_min, b$volumen_min)
}

# La fusión es factible únicamente si las tres intersecciones dimensionales no
# están vacías y existe una caja en esa intersección que además respete volumen,
# pallet y resistencia.
fusionar_clusters <- function(a, b, grosor) {
  candidato <- list(
    productos = c(a$productos, b$productos),
    limite_inferior = pmax(a$limite_inferior, b$limite_inferior),
    limite_superior = pmin(a$limite_superior, b$limite_superior),
    volumen_min = max(a$volumen_min, b$volumen_min),
    peso_maximo = max(a$peso_maximo, b$peso_maximo),
    volumenes = rbind(a$volumenes, b$volumenes)
  )

  if (any(candidato$limite_inferior > candidato$limite_superior + TOL)) {
    return(NULL)
  }
  evaluar_cluster(candidato, grosor)
}

# Delta < 0: la fusión ahorra dinero. Delta = 0: no empeora el costo y reduce
# tipos de caja, por lo que también se acepta como desempate.
puntuar_fusion <- function(id_a, id_b, clusters, grosor) {
  a <- clusters[[as.character(id_a)]]
  b <- clusters[[as.character(id_b)]]
  if (!prechequear_fusion(a, b)) return(NA_real_)
  fusion <- fusionar_clusters(a, b, grosor)

  if (is.null(fusion)) return(NA_real_)
  fusion$costo_total - a$costo_total - b$costo_total
}

# Solo se almacenan fusiones que no empeoran la solución. Un par que ya era
# costoso no cambia mientras sus dos clusters sigan intactos; por eso no hace
# falta conservarlo ni reevaluarlo después.
armar_candidatos_iniciales <- function(ids, clusters, grosor) {
  candidatos <- list()
  k <- 0L

  for (i in seq_len(length(ids) - 1L)) {
    for (j in (i + 1L):length(ids)) {
      delta <- puntuar_fusion(ids[i], ids[j], clusters, grosor)
      if (is.finite(delta) && delta <= TOL) {
        k <- k + 1L
        candidatos[[k]] <- tibble(id_a = ids[i], id_b = ids[j], delta = delta)
      }
    }
  }

  if (k == 0L) return(tibble(id_a = integer(), id_b = integer(), delta = numeric()))
  bind_rows(candidatos)
}

optimizar_por_grosor <- function(grosor, productos) {
  # Paso 1. Punto de partida: una caja logística óptima para cada SKU.
  clusters <- lapply(seq_len(nrow(productos)), function(i) {
    base <- crear_cluster(productos[i, , drop = FALSE], grosor)
    salida <- evaluar_cluster(base, grosor)
    if (is.null(salida)) {
      stop("El producto ", productos$codigo_producto[i],
           " no es factible con grosor ", grosor, " mm.")
    }
    salida
  })
  names(clusters) <- as.character(seq_along(clusters))

  activos <- seq_along(clusters)
  candidatos <- armar_candidatos_iniciales(activos, clusters, grosor)
  proximo_id <- max(activos)
  n_fusiones <- 0L

  # Paso 2. Best improvement: en cada vuelta se toma la fusión con menor delta.
  # Luego sólo se recalculan parejas que involucren al cluster recién creado.
  while (nrow(candidatos) > 0) {
    fila <- which.min(candidatos$delta)
    id_a <- candidatos$id_a[fila]
    id_b <- candidatos$id_b[fila]

    nuevo <- fusionar_clusters(
      clusters[[as.character(id_a)]],
      clusters[[as.character(id_b)]],
      grosor
    )

    # Protección ante diferencias numéricas: el candidato se vuelve a validar.
    if (is.null(nuevo) || nuevo$costo_total >
        clusters[[as.character(id_a)]]$costo_total +
        clusters[[as.character(id_b)]]$costo_total + TOL) {
      candidatos <- candidatos[-fila, , drop = FALSE]
      next
    }

    candidatos <- candidatos %>%
      filter(!(.data$id_a %in% c(id_a, id_b) |
                 .data$id_b %in% c(id_a, id_b)))

    activos <- setdiff(activos, c(id_a, id_b))
    proximo_id <- proximo_id + 1L
    clusters[[as.character(proximo_id)]] <- nuevo

    nuevos <- lapply(activos, function(otro_id) {
      delta <- puntuar_fusion(otro_id, proximo_id, clusters, grosor)
      if (!is.finite(delta) || delta > TOL) return(NULL)
      tibble(id_a = otro_id, id_b = proximo_id, delta = delta)
    }) %>% bind_rows()

    candidatos <- bind_rows(candidatos, nuevos)
    activos <- c(activos, proximo_id)
    n_fusiones <- n_fusiones + 1L
  }

  clusters_finales <- clusters[as.character(activos)]

  asignacion <- bind_rows(lapply(seq_along(clusters_finales), function(i) {
    cl <- clusters_finales[[i]]
    tibble(
      codigo_producto = cl$productos,
      cluster_id = i,
      caja_grosor_mm = grosor,
      caja_exterior_largo = unname(cl$exterior["L"]),
      caja_exterior_ancho = unname(cl$exterior["W"]),
      caja_exterior_alto = unname(cl$exterior["H"])
    )
  }))

  resumen <- tibble(
    grosor = grosor,
    tipos_caja = length(clusters_finales),
    fusiones_aceptadas = n_fusiones,
    pallets = sum(vapply(clusters_finales,
                          function(x) sum(x$pallets_planta), numeric(1))),
    costo_packaging = sum(vapply(clusters_finales,
                                 function(x) x$costo_packaging, numeric(1))),
    costo_flete = sum(vapply(clusters_finales,
                             function(x) x$costo_flete, numeric(1)))
  ) %>%
    mutate(costo_total = costo_packaging + costo_flete)

  list(asignacion = asignacion, resumen = resumen, clusters = clusters_finales)
}

# Paso 3. La elección de grosor es global: son tres corridas independientes,
# no tres alternativas que puedan mezclarse entre cajas.
escenarios <- lapply(c(3.0, 4.5, 5.0), optimizar_por_grosor, productos = productos)
tabla_escenarios <- bind_rows(lapply(escenarios, function(x) x$resumen)) %>%
  arrange(costo_total)

print(tabla_escenarios)

mejor_indice <- which.min(vapply(
  escenarios, function(x) x$resumen$costo_total, numeric(1)
))
mejor_escenario <- escenarios[[mejor_indice]]

resultado_final <- mejor_escenario$asignacion %>%
  select(
    codigo_producto,
    caja_grosor_mm,
    caja_exterior_largo,
    caja_exterior_ancho,
    caja_exterior_alto
  ) %>%
  arrange(codigo_producto)

# Paso 4. Validación independiente de las restricciones por SKU antes de subir.
validacion <- resultado_final %>%
  left_join(
    productos %>%
      select(codigo_producto, peso_neto_caja,
             L0 = caja_interior_largo,
             W0 = caja_interior_ancho,
             H0 = caja_interior_alto),
    by = "codigo_producto"
  ) %>%
  mutate(
    L_int = caja_exterior_largo - 2 * caja_grosor_mm,
    W_int = caja_exterior_ancho - 2 * caja_grosor_mm,
    H_int = caja_exterior_alto - 2 * caja_grosor_mm,
    h = case_when(caja_grosor_mm <= 3.0 ~ 0.06,
                  caja_grosor_mm <= 4.5 ~ 0.08,
                  TRUE ~ 0.10),
    fit_ok = L_int >= 0.90 * L0 - TOL & L_int <= 1.10 * L0 + TOL &
             W_int >= 0.90 * W0 - TOL & W_int <= 1.10 * W0 + TOL &
             H_int >= 0.90 * H0 - TOL & H_int <= 1.10 * H0 + TOL,
    volumen_ok = L_int * W_int * H_int >= L0 * W0 * H0 - TOL,
    headspace_ok =
      (L_int <= L0 + TOL | L_int - L0 <= pmin(h * L_int, 40) + TOL) &
      (W_int <= W0 + TOL | W_int - W0 <= pmin(h * W_int, 40) + TOL) &
      (H_int <= H0 + TOL | H_int - H0 <= pmin(h * H_int, 40) + TOL),
    nH = floor(1800 / caja_exterior_alto + TOL),
    carga_max = if_else(
      caja_grosor_mm == 3.0,
      1000 * 2 * (caja_exterior_largo + caja_exterior_ancho) / 1000 / G,
      if_else(caja_grosor_mm == 4.5,
              1400 * 2 * (caja_exterior_largo + caja_exterior_ancho) / 1000 / G,
              1650 * 2 * (caja_exterior_largo + caja_exterior_ancho) / 1000 / G)
    ),
    resistencia_ok = carga_max + TOL >= (nH - 1) * peso_neto_caja
  )

if (!all(validacion$fit_ok & validacion$volumen_ok &
         validacion$headspace_ok & validacion$resistencia_ok)) {
  stop("La validación final detectó al menos una restricción incumplida.")
}

stopifnot(
  nrow(resultado_final) == nrow(productos),
  n_distinct(resultado_final$codigo_producto) == nrow(productos)
)

write_csv(resultado_final, "resultado_optimo_pallet.csv")
