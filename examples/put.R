# Independent base-R witness for DS-023. Repository evidence, no live SAS.
# Keep source tokens quoted so quote-pair PUT syntax remains distinguishable.
sas_put_literals <- function(tokens) {
  if (!is.character(tokens) || length(tokens) == 0L || anyNA(tokens))
    stop('quoted literals required')
  rendered <- character(length(tokens))
  for (j in seq_along(tokens)) {
    chars <- strsplit(tokens[j], '', fixed=TRUE)[[1]]
    n <- length(chars)
    if (n < 2L || !(chars[1] %in% c("'", '"')) || chars[n] != chars[1])
      stop('complete quoted literals required')
    quote <- chars[1]
    body <- if (n == 2L) character() else chars[2:(n-1L)]
    if (quote == '"' && any(body %in% c('&', '%')))
      stop('double-quoted & or % requires macro review')
    result <- character()
    i <- 1L
    while (i <= length(body)) {
      ch <- body[i]
      if (ch == quote) {
        if (i == length(body) || body[i+1L] != quote)
          stop('complete quoted literals required')
        i <- i + 1L
      }
      result <- c(result, ch)
      i <- i + 1L
    }
    # PUT's two-delimiter form writes the delimiter itself.
    rendered[j] <- if (length(body) == 0L) quote else paste0(result, collapse='')
    codepoints <- utf8ToInt(rendered[j])
    if (any(codepoints < 32L | codepoints > 126L))
      stop('only printable ASCII literals are gated')
  }
  record <- paste0(rendered, collapse='')
  if (nchar(record, type='bytes') > 64L)
    stop('output beyond 64 columns requires LINESIZE review')
  record
}

args <- commandArgs(trailingOnly=TRUE)
if (length(args) != 1L) stop('usage: Rscript put.R cases.csv')
cases <- read.csv(args[1], colClasses='character',
                  na.strings=NULL, check.names=FALSE, fileEncoding='UTF-8')
for (id in unique(cases$id)) {
  result <- tryCatch({
    record <- sas_put_literals(cases$token[cases$id == id])
    paste0('OK:', paste(sprintf('%02x', as.integer(charToRaw(record))), collapse=''))
  }, error=function(e) paste0('ERROR: ', conditionMessage(e)))
  cat(result, '\n', sep='')
}
