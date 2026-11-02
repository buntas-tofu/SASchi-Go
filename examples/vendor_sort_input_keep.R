# Independent finite complete-source oracle for the pinned vendor input KEEP target.
# Reads an external source file. No Python plans, helpers or vendor rows here.
# Numeric spelling frontier is integer list fields and ordinary missing, which
# covers the original report target. This is not the full numeric INPUT grammar.
# Source parsing and input projection are independent of Python plans/helpers.
args <- commandArgs(trailingOnly=TRUE)
if (length(args) != 2L) stop('source and fresh temporary output directory required')
input_path <- normalizePath(args[1], mustWork=TRUE)
output_path <- args[2]
temp_root <- file.path(normalizePath(tempdir(), mustWork=TRUE), '..')
temp_root <- paste0(normalizePath(temp_root, mustWork=TRUE), '/saschi-sort-input-keep-')
if (!startsWith(output_path, temp_root) || dir.exists(output_path) || file.exists(output_path)) stop('fresh task temporary output required')
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
  if (tolower(statement) == 'datalines4') {
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
      if (value == ';;;;') {
        add_event(list(kind='opaque_data', line=payload_line,
                       terminator_line=as.integer(line_at(begin)), records=records))
        found <- TRUE; pos <- pos + 1L; break
      }
      records <- c(records, value); pos <- pos + 1L
    }
    if (!found) stop('missing DATALINES4 terminator')
  }
}
if (quote != '' || trimws(buffer) != '') stop('unterminated source')

ascii_name <- function(x) grepl('^[A-Za-z_][A-Za-z0-9_]{0,31}$', x)
lower_name <- function(x) {
  if (!ascii_name(x)) stop('ordinary ASCII name required')
  value <- tolower(x)
  if (value %in% c('_n_', '_error_', '_all_', '_null_')) stop('automatic name outside frontier')
  value
}
capture <- function(pattern, text) {
  match <- regexec(pattern, text, ignore.case=TRUE, perl=TRUE)
  result <- regmatches(text, match)[[1]]
  if (length(result) == 0L) stop('outside finite source grammar')
  result[-1L]
}
exact <- function(index, text) {
  if (index > length(events) || events[[index]]$kind != 'statement' ||
      tolower(gsub('[ \t\r\n]+', ' ', events[[index]]$text)) != text) stop('required complete statement differs')
}
columns_from <- function(text) {
  rest <- sub('^[Ii][Nn][Pp][Uu][Tt][ \t\r\n]+', '', text)
  columns <- list()
  while (nchar(trimws(rest), type='bytes') > 0L) {
    hit <- regexec('^[ \t\r\n]*([A-Za-z_][A-Za-z0-9_]*)(?:[ \t\r\n]*:[ \t\r\n]*\\$([0-9]+)\\.)?(?=[ \t\r\n]|$)', rest, perl=TRUE)
    value <- regmatches(rest, hit)[[1]]
    if (length(value) == 0L) stop('INPUT outside finite column grammar')
    name <- lower_name(value[2])
    if (name %in% names(columns)) stop('duplicate INPUT name')
    width <- value[3]
    if (is.na(width) || width == '') columns[name] <- list(list(type='number', length=8L))
    else {
      n <- as.integer(width)
      if (is.na(n) || n < 1L || n > 64L || as.character(n) != width) stop('character width bound')
      columns[name] <- list(list(type='character', length=n))
    }
    rest <- substring(rest, nchar(value[1]) + 1L)
  }
  if (length(columns) < 1L || length(columns) > 32L ||
      !any(vapply(columns, function(x) x$type == 'character', TRUE))) stop('mixed columns required')
  columns
}
split_fields <- function(text) {
  commas <- gregexpr(',', text, fixed=TRUE)[[1]]
  if (commas[1] < 0L) return(text)
  starts <- c(1L, commas + 1L)
  ends <- c(commas - 1L, nchar(text, type='bytes'))
  vapply(seq_along(starts), function(i) if (ends[i] < starts[i]) '' else substr(text, starts[i], ends[i]), '')
}
trim_ascii <- function(text) sub(' +$', '', sub('^ +', '', text))
printable <- function(text) all(as.integer(charToRaw(text)) >= 32L & as.integer(charToRaw(text)) <= 126L)
read_row <- function(text, schema) {
  if (!printable(text) || nchar(text, type='bytes') > 80L ||
      grepl('"', text, fixed=TRUE) || grepl("'", text, fixed=TRUE)) stop('record character bound')
  fields <- split_fields(text)
  if (length(fields) != length(schema)) stop('record field count')
  row <- list()
  for (i in seq_along(schema)) {
    name <- names(schema)[i]; descriptor <- schema[[i]]
    value <- trim_ascii(fields[i])
    if (descriptor$type == 'character') {
      width <- nchar(value, type='bytes')
      if (value == '.' || width > descriptor$length) stop('character field refusal')
      cell <- paste0(value, strrep(' ', descriptor$length - width))
    } else if (value %in% c('', '.')) cell <- NULL
    else {
      if (!grepl('^[+-]?[0-9]+$', value) || nchar(gsub('[+-]', '', value)) > 15L ||
          nchar(value) > 32L) stop('numeric spelling outside finite integer oracle')
      cell <- as.numeric(value)
      if (!is.finite(cell) || cell != trunc(cell) || abs(cell) > 2147483647) stop('numeric value bound')
      if (cell == 0) cell <- 0
    }
    row[name] <- list(cell)
  }
  row
}
json_string <- function(x) encodeString(x, quote='"', justify='none')
integer_text <- function(x) {
  if (is.null(x)) return('.')
  if (!is.numeric(x) || !is.finite(x) || x != trunc(x) || abs(x) > 2147483647) stop('report number bound')
  if (x == 0) return('0')
  format(x, scientific=FALSE, trim=TRUE, digits=15)
}
title_literal <- function(text) {
  rest <- sub('^[Tt][Ii][Tt][Ll][Ee][ \t\r\n]*', '', text)
  if (rest == '') return(NULL)
  delimiter <- substr(rest, 1L, 1L)
  if (!delimiter %in% c('"', "'") || substr(rest, nchar(rest), nchar(rest)) != delimiter) stop('one title literal required')
  inside <- substr(rest, 2L, nchar(rest) - 1L)
  chars <- strsplit(inside, '', fixed=TRUE)[[1]]
  result <- ''; k <- 1L
  while (k <= length(chars)) {
    ch <- chars[k]
    if (ch == delimiter) {
      if (k == length(chars) || chars[k + 1L] != delimiter) stop('undoubled title quote')
      k <- k + 1L
    }
    result <- paste0(result, ch); k <- k + 1L
  }
  if (!printable(result) || nchar(result, type='bytes') < 1L ||
      nchar(result, type='bytes') > 128L || trim_ascii(result) == '') stop('title policy bound')
  if (grepl('&', result, fixed=TRUE) || grepl('%', result, fixed=TRUE)) stop('macro-sensitive title text outside DECISION-02')
  result
}
render <- function(table, title) {
  schema <- table$schema
  if ('obs' %in% names(schema) || length(schema) > 32L || length(table$rows) > 1000L) stop('report schema bound')
  header <- paste(c('obs', names(schema)), collapse=' ')
  if (nchar(header, type='bytes') > 1055L) stop('report header bound')
  lines <- character()
  if (!is.null(title)) lines <- c(lines, paste0('TITLE: ', title))
  lines <- c(lines, header)
  for (i in seq_along(table$rows)) {
    row <- table$rows[[i]]
    values <- vapply(names(schema), function(name) {
      value <- row[[name]]
      if (schema[[name]]$type == 'character') json_string(sub(' +$', '', value))
      else integer_text(value)
    }, '')
    line <- paste(c(as.character(i), values), collapse=' ')
    if (nchar(line, type='bytes') > 415L) stop('report data-row bound')
    lines <- c(lines, line)
  }
  result <- paste0(paste(lines, collapse='\n'), '\n')
  if (nchar(result, type='bytes') > 417056L) stop('total report bound')
  result
}

tables <- list(); reports <- list(); trace <- list()
title <- NULL; ordinal <- 0L; title_sets <- 0L; title_resets <- 0L
iterations <- 0L; attempts <- 0L; outputs <- 0L; sort_rows <- 0L
source_ordinals <- integer(); kept_ordinals <- integer(); report_records <- integer(); steps <- 0L
add_trace <- function(x) trace[[length(trace) + 1L]] <<- x
cursor <- 1L
while (cursor <= length(events)) {
  item <- events[[cursor]]
  if (item$kind != 'statement') stop('unowned payload')
  text <- item$text
  if (grepl('^data[ \t\r\n]+', text, ignore.case=TRUE)) {
    table_name <- lower_name(capture('^data\\s+([A-Za-z_][A-Za-z0-9_]*)$', text)[1])
    if (table_name %in% names(tables)) stop('input destination exists')
    exact(cursor + 1L, 'infile datalines dsd')
    declaration <- events[[cursor + 2L]]
    if (declaration$kind != 'statement' || !grepl('^input\\s+', declaration$text, ignore.case=TRUE)) stop('INPUT required')
    schema <- columns_from(declaration$text)
    exact(cursor + 3L, 'datalines4')
    payload <- events[[cursor + 4L]]
    if (payload$kind != 'opaque_data' || length(payload$records) > 1000L) stop('opaque payload bound')
    exact(cursor + 5L, 'run')
    rows <- lapply(payload$records, read_row, schema=schema)
    add_trace(list(event='data_begin', line=item$line, table=table_name))
    for (i in seq_along(rows)) {
      add_trace(list(event='input_attempt', line=declaration$line, record=as.integer(i),
                     record_line=as.integer(payload$line + i - 1L), eof=FALSE))
      add_trace(list(event='implicit_output', table=table_name, observation=as.integer(i)))
    }
    add_trace(list(event='input_attempt', line=declaration$line,
                   record=as.integer(length(rows) + 1L), eof=TRUE))
    add_trace(list(event='data_end', line=events[[cursor + 5L]]$line,
                   table=table_name, rows=as.integer(length(rows))))
    tables[table_name] <- list(list(schema=schema, rows=unname(rows)))
    iterations <- iterations + length(rows); attempts <- attempts + length(rows) + 1L
    outputs <- outputs + length(rows); cursor <- cursor + 6L
  } else if (grepl('^title(?:[ \t\r\n]|$)', text, ignore.case=TRUE, perl=TRUE)) {
    title <- title_literal(text)
    if (is.null(title)) {
      title_resets <- title_resets + 1L
      add_trace(list(event='title_reset', line=item$line))
    } else {
      title_sets <- title_sets + 1L
      add_trace(list(event='title_set', line=item$line, text=title))
    }
    if (title_sets + title_resets > 32L) stop('TITLE count bound')
    cursor <- cursor + 1L
  } else if (grepl('^proc\\s+print\\s+', text, ignore.case=TRUE, perl=TRUE)) {
    name <- lower_name(capture('^proc\\s+print\\s+data\\s*=\\s*([A-Za-z_][A-Za-z0-9_]*)$', text)[1])
    exact(cursor + 1L, 'run')
    if (!name %in% names(tables)) stop('PRINT input absent')
    ordinal <- ordinal + 1L
    if (ordinal > 2L) stop('PRINT count bound')
    file <- sprintf('print_%02d.txt', ordinal)
    value <- render(tables[[name]], title)
    reports[file] <- list(value)
    report_records <- c(report_records, as.integer(length(strsplit(value, '\n', fixed=TRUE)[[1]])))
    add_trace(list(event='print', line=item$line, table=name, report=file,
                   rows=as.integer(length(tables[[name]]$rows)), title=title))
    cursor <- cursor + 2L
  } else if (grepl('^proc\\s+sort\\s+', text, ignore.case=TRUE, perl=TRUE)) {
    names_ <- capture('^proc\\s+sort\\s+data\\s*=\\s*([A-Za-z_][A-Za-z0-9_]*)\\s*\\(\\s*keep\\s*=\\s*([A-Za-z_][A-Za-z0-9_]*(?:\\s+[A-Za-z_][A-Za-z0-9_]*)*)\\s*\\)\\s+out\\s*=\\s*([A-Za-z_][A-Za-z0-9_]*)(\\s+nodupkey)?$', text)
    from <- lower_name(names_[1]); keep <- strsplit(trimws(names_[2]), '[ \t\r\n]+', perl=TRUE)[[1]]
    keep <- vapply(keep, lower_name, ''); to <- lower_name(names_[3])
    nodupkey <- !is.na(names_[4]) && trimws(names_[4]) != ''
    if (!from %in% names(tables) || to %in% names(tables)) stop('SORT lineage outside frontier')
    table <- tables[[from]]
    if (anyDuplicated(keep) || !all(keep %in% names(table$schema))) stop('KEEP unknown or duplicate name')
    selected <- names(table$schema)[names(table$schema) %in% keep]
    table$schema <- table$schema[selected]
    table$rows <- lapply(table$rows, function(row) row[selected])
    by <- events[[cursor + 1L]]
    if (by$kind != 'statement') stop('BY required')
    keys <- capture('^by\\s+(.+)$', by$text)[1]
    keys <- strsplit(trimws(keys), '[ \t\r\n]+', perl=TRUE)[[1]]
    keys <- vapply(keys, lower_name, '')
    if (anyDuplicated(keys) || !all(keys %in% names(table$schema))) stop('BY keys removed or invalid')
    exact(cursor + 2L, 'run')
    values <- lapply(keys, function(key) {
      if (table$schema[[key]]$type == 'character')
        vapply(table$rows, function(row) sub(' +$', '', row[[key]]), '')
      else vapply(table$rows, function(row) if (is.null(row[[key]])) -Inf else row[[key]], 0)
    })
    if (length(table$rows)) {
      source_ordinals <- as.integer(do.call(order, c(values, list(method='radix'))))
      kept_ordinals <- source_ordinals
      if (nodupkey && length(source_ordinals) > 1L) {
        keep_row <- rep(TRUE, length(source_ordinals))
        for (i in 2:length(source_ordinals)) {
          keep_row[i] <- !all(vapply(values, function(v) identical(v[source_ordinals[i]], v[source_ordinals[i - 1L]]), TRUE))
        }
        kept_ordinals <- source_ordinals[keep_row]
      }
      table$rows <- table$rows[kept_ordinals]
    } else { source_ordinals <- integer(); kept_ordinals <- integer() }
    tables[to] <- list(table); sort_rows <- sort_rows + length(source_ordinals)
    add_trace(list(event='sort', line=item$line, source=from, destination=to,
                   source_ordinals=as.list(source_ordinals), kept_ordinals=as.list(kept_ordinals)))
    cursor <- cursor + 3L
  } else stop('unconsumed or unsupported source statement')
  steps <- steps + 1L
  if (steps > 64L) stop('top-level step bound')
}
if (!length(tables) || !length(reports)) stop('complete character/report source required')
result <- list(datasets=tables, log=list(), reports=reports)
accounting <- list(language_statements=as.integer(sum(vapply(events, function(x) x$kind == 'statement', TRUE))),
                   opaque_payloads=as.integer(sum(vapply(events, function(x) x$kind == 'opaque_data', TRUE))),
                   steps=as.integer(steps), input_records=as.integer(iterations),
                   data_iterations=as.integer(iterations), input_attempts=as.integer(attempts),
                   implicit_outputs=as.integer(outputs), sort_rows=as.integer(sort_rows),
                   sort_source_ordinals=as.list(source_ordinals), sort_kept_ordinals=as.list(kept_ordinals), title_sets=title_sets,
                   title_resets=title_resets, prints=ordinal,
                   report_records=as.list(report_records), final_title=title)
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
dir.create(output_path, recursive=TRUE, showWarnings=FALSE)
write_body <- function(name, value) {
  con <- file(file.path(output_path, name), open='wb')
  writeBin(charToRaw(paste0(to_json(value), '\n')), con); close(con)
}
write_body('result.json', result)
write_body('accounting.json', accounting)
write_body('trace.json', trace)
for (name in names(reports)) {
  con <- file(file.path(output_path, name), open='wb')
  writeBin(charToRaw(reports[[name]]), con); close(con)
}
cat('PASS complete finite source oracle\n')
cat('language_statements ', accounting$language_statements, '\n', sep='')
cat('records ', accounting$input_records, '\n', sep='')
cat('reports ', ordinal, '\n', sep='')
cat('semantic_trace_events ', length(trace), '\n', sep='')
