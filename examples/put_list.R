# Independent base-R witness for DS-024. Repository evidence, no live SAS.
decode_literal <- function(token) {
  chars <- strsplit(token, '', fixed=TRUE)[[1]]
  n <- length(chars)
  if (n < 2L || !(chars[1] %in% c("'", '"')) || chars[n] != chars[1])
    stop('complete quoted literals required')
  quote <- chars[1]
  body <- if (n == 2L) character() else chars[2:(n-1L)]
  if (quote == '"' && any(body %in% c('&', '%')))
    stop('double-quoted & or % requires macro review')
  result <- character()
  at <- 1L
  while (at <= length(body)) {
    ch <- body[at]
    if (ch == quote) {
      if (at == length(body) || body[at+1L] != quote)
        stop('complete quoted literals required')
      at <- at + 1L
    }
    result <- c(result, ch)
    at <- at + 1L
  }
  if (length(body) == 0L) quote else paste0(result, collapse='')
}

sas_put_character_list <- function(items) {
  if (!is.list(items) || length(items) == 0L) stop('list items required')
  record <- ''
  variables <- 0L
  for (item in items) {
    value <- item$value
    if (!is.character(value) || length(value) != 1L || is.na(value))
      stop('character values required; no implicit conversion')
    if (item$kind == 'literal') {
      text <- decode_literal(value)
    } else if (item$kind == 'character') {
      variables <- variables + 1L
      chars <- strsplit(value, '', fixed=TRUE)[[1]]
      occupied <- which(chars != ' ')
      if (!length(occupied)) stop('blank character values require missing-field review')
      # Keep only the interval from first to last nonblank character.
      text <- paste0(chars[min(occupied):max(occupied)], collapse='')
      text <- paste0(text, ' ')
    } else stop('unsupported item kind')
    codes <- utf8ToInt(value)
    if (any(codes < 32L | codes > 126L)) stop('only printable ASCII is gated')
    record <- paste0(record, text)
  }
  if (variables == 0L) stop('at least one character variable required')
  if (nchar(record, type='bytes') > 64L) stop('output beyond 64 columns requires LINESIZE review')
  record
}

args <- commandArgs(trailingOnly=TRUE)
if (length(args) != 1L) stop('usage: Rscript put_list.R cases.csv')
cases <- read.csv(args[1], colClasses='character', na.strings=NULL,
                  check.names=FALSE, fileEncoding='UTF-8')
for (id in unique(cases$id)) {
  selected <- cases[cases$id == id, , drop=FALSE]
  items <- lapply(seq_len(nrow(selected)), function(i) {
    value <- switch(selected$type[i], text=selected$value[i],
                    number=as.numeric(selected$value[i]), null=NULL,
                    tagged=list(missing=selected$value[i]))
    list(kind=selected$kind[i], value=value)
  })
  result <- tryCatch({
    record <- sas_put_character_list(items)
    paste0('OK:', paste(sprintf('%02x', as.integer(charToRaw(record))), collapse=''))
  }, error=function(e) paste0('ERROR: ', conditionMessage(e)))
  cat(result, '\n', sep='')
}
