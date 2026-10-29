# A0 whole-source witness for comments and DATA _NULL_ literal PUT programs.
# Independent base R parsing; no translator plan or Python implementation used.

hex <- function(text) paste(sprintf('%02x', as.integer(charToRaw(text))), collapse='')
scan_source <- function(bytes) {
  values <- as.integer(bytes); n <- length(values); i <- 1L
  statements <- character(); pending <- integer(); blocks <- 0L; stars <- 0L; nulls <- 0L
  white <- function(value) value %in% c(9L, 10L, 13L, 32L)
  if (any(!(values %in% c(9L, 10L, 13L, 32L:126L)))) stop('non-ASCII source outside witness')
  while (i <= n) {
    value <- values[i]
    if (value == 47L && i < n && values[i+1L] == 42L) {
      blocks <- blocks+1L; i <- i+2L
      while (i < n && !(values[i] == 42L && values[i+1L] == 47L)) i <- i+1L
      if (i >= n) stop('unclosed block comment')
      i <- i+2L; pending <- c(pending, 32L); next
    }
    at_start <- !length(pending) || all(vapply(pending, white, logical(1)))
    macro <- value == 37L && i < n && values[i+1L] == 42L
    if (at_start && (value == 42L || macro)) {
      stars <- stars+1L
      while (i <= n && values[i] != 59L) i <- i+1L
      if (i > n) stop('unclosed statement comment')
      i <- i+1L; next
    }
    if (value %in% c(34L, 39L)) {
      quote <- value; pending <- c(pending, value); i <- i+1L; closed <- FALSE
      while (i <= n) {
        value <- values[i]; pending <- c(pending, value); i <- i+1L
        if (value == quote) {
          if (i <= n && values[i] == quote) {
            pending <- c(pending, quote); i <- i+1L
          } else {closed <- TRUE; break}
        }
      }
      if (!closed) stop('unclosed quoted literal')
      next
    }
    if (value == 59L) {
      statement <- trimws(rawToChar(as.raw(pending)))
      if (nzchar(statement)) statements <- c(statements, statement) else nulls <- nulls+1L
      pending <- integer(); i <- i+1L; next
    }
    pending <- c(pending, value); i <- i+1L
  }
  if (nzchar(trimws(rawToChar(as.raw(pending))))) stop('unterminated source tail')
  list(statements=statements, bytes=n, consumed=i-1L, block_comments=blocks,
       statement_comments=stars, null_statements=nulls)
}

literal_put <- function(text) {
  values <- as.integer(charToRaw(sub('^[Pp][Uu][Tt][[:space:]]+', '', text)))
  n <- length(values); i <- 1L; answer <- integer(); count <- 0L
  while (i <= n) {
    while (i <= n && values[i] %in% c(9L, 10L, 13L, 32L)) i <- i+1L
    if (i > n) break
    quote <- values[i]
    if (!(quote %in% c(34L, 39L))) stop('PUT requires literal operands in A0 witness')
    i <- i+1L; value <- integer(); closed <- FALSE
    while (i <= n) {
      byte <- values[i]; i <- i+1L
      if (byte == quote) {
        if (i <= n && values[i] == quote) {value <- c(value, quote); i <- i+1L}
        else {closed <- TRUE; break}
      } else value <- c(value, byte)
    }
    if (!closed || any(!(value %in% 32L:126L))) stop('unsupported literal')
    if (quote == 34L && any(value %in% c(37L, 38L))) stop('unresolved macro literal')
    answer <- c(answer, if (length(value)) value else quote); count <- count+1L
  }
  if (!count || length(answer) > 64L) stop('PUT outside existing literal profile')
  rawToChar(as.raw(answer))
}

program <- function(path) {
  size <- file.info(path)$size
  stream <- file(path, 'rb'); on.exit(close(stream)); bytes <- readBin(stream, 'raw', n=size)
  scanned <- scan_source(bytes); active <- FALSE; steps <- 0L; puts <- 0L; logs <- character()
  for (statement in scanned$statements) {
    lowered <- tolower(gsub('[[:space:]]+', ' ', statement))
    if (lowered == 'data _null_') {
      if (active) stop('unterminated DATA step')
      active <- TRUE; steps <- steps+1L
    } else if (lowered == 'run') {
      if (!active) stop('RUN outside DATA step')
      active <- FALSE
    } else if (grepl('^put[[:space:]]+', statement, ignore.case=TRUE)) {
      if (!active) stop('PUT outside DATA step')
      logs <- c(logs, literal_put(statement)); puts <- puts+1L
    } else stop('unhandled statement in complete source')
  }
  if (active) stop('missing RUN terminator')
  cat('BYTES:', scanned$bytes, '\n', 'CONSUMED:', scanned$consumed,
      '\nSTATEMENTS:', length(scanned$statements), '\nSTEPS:', steps, '\nPUTS:', puts,
      '\nBLOCK_COMMENTS:', scanned$block_comments, '\nSTATEMENT_COMMENTS:', scanned$statement_comments,
      '\nNULL_STATEMENTS:', scanned$null_statements, '\n', sep='')
  for (record in logs) cat('LOG:', hex(record), '\n', sep='')
}

args <- commandArgs(trailingOnly=TRUE)
if (length(args) != 1L) stop('one complete source path required')
program(args[1])
