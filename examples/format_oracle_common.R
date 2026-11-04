# Independent source scanner and JSON writer shared only by base-R witnesses.
size <- file.info(input_path)$size
connection <- file(input_path, open='rb')
raw_source <- readBin(connection, what='raw', n=size)
close(connection)
if (any(as.integer(raw_source) > 127L) || any(raw_source == as.raw(0))) stop('ASCII source frontier')
source <- rawToChar(raw_source)
characters <- strsplit(source, '', fixed=TRUE)[[1]]
N <- length(characters)
line_at <- function(pos) 1L + sum(characters[seq_len(max(0L, pos - 1L))] == '\n')
at <- function(pos) if (pos > N) '' else characters[pos]
space <- function(ch) ch %in% c(' ', '\t', '\r', '\n')
events <- list()
add_event <- function(value) events[[length(events) + 1L]] <<- value
pos <- 1L
buffer <- ''
first <- NA_integer_
quote <- ''
while (pos <= N) {
  ch <- at(pos)
  if (quote != '') {
    buffer <- paste0(buffer, ch)
    if (ch == quote) {
      if (at(pos + 1L) == quote) {
        buffer <- paste0(buffer, quote); pos <- pos + 2L; next
      }
      quote <- ''
    }
    pos <- pos + 1L; next
  }
  if (ch == '/' && at(pos + 1L) == '*') {
    end <- pos + 2L
    while (end <= N && !(at(end) == '*' && at(end + 1L) == '/')) end <- end + 1L
    if (end > N) stop('unterminated comment')
    buffer <- paste0(buffer, ' '); pos <- end + 2L; next
  }
  if (ch == '*' && trimws(buffer) == '') {
    while (pos <= N && at(pos) != ';') pos <- pos + 1L
    if (pos > N) stop('unterminated statement comment')
    buffer <- ''; first <- NA_integer_; pos <- pos + 1L; next
  }
  if (!space(ch) && is.na(first)) first <- pos
  if (ch %in% c('"', "'")) {
    quote <- ch; buffer <- paste0(buffer, ch); pos <- pos + 1L; next
  }
  if (ch != ';') {
    buffer <- paste0(buffer, ch); pos <- pos + 1L; next
  }
  statement <- trimws(buffer)
  if (statement == '') stop('unowned empty statement')
  add_event(list(kind='statement', line=as.integer(line_at(first)), text=statement))
  buffer <- ''; first <- NA_integer_; pos <- pos + 1L
  if (tolower(statement) %in% c('cards','datalines')) {
    while (pos <= N && at(pos) %in% c(' ', '\t', '\r')) pos <- pos + 1L
    if (at(pos) != '\n') stop('payload must start on next physical line')
    pos <- pos + 1L
    payload_line <- as.integer(line_at(pos))
    records <- character()
    found <- FALSE
    while (pos <= N) {
      begin <- pos
      while (pos <= N && at(pos) != '\n') pos <- pos + 1L
      value <- if (pos == begin) '' else paste0(characters[seq.int(begin, pos - 1L)], collapse='')
      value <- sub('\r$', '', value)
      if (value == ';') {
        add_event(list(kind='opaque_data', line=payload_line,
                       terminator_line=as.integer(line_at(begin)), records=records))
        found <- TRUE; pos <- pos + 1L; break
      }
      records <- c(records, value); pos <- pos + 1L
    }
    if (!found) stop('missing DATALINES terminator')
  }
}
if (quote != '' || trimws(buffer) != '') stop('unterminated source')


statements <- Filter(function(x) x$kind=='statement',events)
json_string <- function(x) encodeString(x,quote='"',justify='none')
integer_text <- function(x) format(x,scientific=FALSE,trim=TRUE,digits=15)
hex <- function(text) paste0(sprintf('%02x',as.integer(charToRaw(text))),collapse='')
to_json <- function(x) {
  if (is.null(x)) return('null')
  if (is.list(x)) {
    if (!is.null(names(x))) {
      pieces <- vapply(seq_along(x), function(i) paste0(json_string(names(x)[i]), ':', to_json(x[[i]])), '')
      return(paste0('{', paste(pieces, collapse=','), '}'))
    }
    return(paste0('[', paste(vapply(x, to_json, ''), collapse=','), ']'))
  }
  if (length(x) != 1L) return(to_json(as.list(x)))
  if (is.character(x)) return(json_string(x))
  if (is.logical(x)) return(if (x) 'true' else 'false')
  if (is.integer(x)) return(as.character(x))
  if (is.numeric(x) && is.finite(x) && x == trunc(x)) return(paste0(integer_text(x), '.0'))
  stop('JSON value outside finite oracle')
}

write_json <- function(name,value) {
 con <- file(file.path(output_path,name),open='wb')
 writeBin(charToRaw(paste0(to_json(value),'\n')),con);close(con)
}
