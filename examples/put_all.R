# Original base-R DS-025 witness. Logical records, no live SAS transcript.
render_all <- function(fields) {
  labels <- character()
  pieces <- character()
  for (f in fields) {
    name <- f$name
    if (!grepl('^[A-Za-z_][A-Za-z0-9_]{0,31}$', name) || tolower(name) %in% labels ||
        tolower(name) %in% c('_n_', '_error_', '_all_', '_numeric_', '_character_',
                            '_infile_', '_file_', '_ods_', '_page_', '_blankpage_'))
      stop('unique ordinary V7 names required')
    labels <- c(labels, tolower(name))
    if (f$kind == 'character') {
      if (f$type != 'text' || any(utf8ToInt(f$value) < 32L | utf8ToInt(f$value) > 126L))
        stop('printable ASCII character values required')
      chars <- strsplit(f$value, '', fixed=TRUE)[[1]]
      occupied <- which(chars != ' ')
      if (!length(occupied)) stop('blank character fields require review')
      text <- paste0(chars[min(occupied):max(occupied)], collapse='')
    } else if (f$kind == 'number') {
      if (f$type == 'missing') text <- '.'
      else {
        if (f$type != 'number') stop('ordinary numeric values required')
        value <- suppressWarnings(as.numeric(f$value))
        if (!is.finite(value) || abs(value) > 99999999999 || value != trunc(value))
          stop('whole numbers within the signed BEST12 slice required')
        text <- if (value == 0) '0' else sprintf('%.0f', value)
      }
    } else stop('unsupported field kind')
    pieces <- c(pieces, paste0(name, '=', text, ' '))
  }
  text <- paste0(paste0(pieces, collapse=''), '_ERROR_=0 _N_=1 ')
  if (nchar(text, type='bytes') > 64L) stop('output beyond 64 columns requires LINESIZE review')
  text
}

hex <- function(text) paste(sprintf('%02x', as.integer(charToRaw(text))), collapse='')

# Independent, deliberately small evaluator for the two hash-pinned external
# corpus programs. It reads them in place. No corpus source is embedded here.
program_records <- function(path) {
  source <- paste(readLines(path, warn=FALSE), collapse='\n')
  source <- gsub('(?s)/\\*.*?\\*/', '', source, perl=TRUE)
  statements <- trimws(strsplit(source, ';', fixed=TRUE)[[1]])
  statements <- statements[nzchar(statements)]
  if (tolower(statements[1]) != 'data _null_' || tolower(tail(statements, 1)) != 'run')
    stop('witness requires one DATA _NULL_ block')
  body <- statements[2:(length(statements)-1L)]
  order <- character(); spelling <- list(); types <- list(); widths <- list()
  register <- function(name, kind, width=0L) {
    key <- tolower(name)
    if (!(key %in% order)) {
      order <<- c(order, key); spelling[[key]] <<- name
      types[[key]] <<- kind; widths[[key]] <<- width
    }
  }
  parse <- function(text) {
    text <- trimws(text)
    q <- substr(text, 1L, 1L)
    if (q %in% c("'", '"') && substr(text, nchar(text), nchar(text)) == q) {
      body <- substr(text, 2L, nchar(text)-1L)
      if (grepl(q, gsub(paste0(q,q), '', body, fixed=TRUE), fixed=TRUE)) stop('bad quote')
      return(list(kind='character', value=gsub(paste0(q,q), q, body, fixed=TRUE)))
    }
    if (grepl('^[A-Za-z_][A-Za-z0-9_]*$', text)) return(list(kind='variable', value=text))
    m <- regmatches(text, regexec('^([A-Za-z]+)\\((.*)\\)$', text))[[1]]
    if (length(m)) {
      name <- tolower(m[2]); args <- trimws(strsplit(m[3], ',', fixed=TRUE)[[1]])
      if (name %in% c('length', 'lengthn', 'lengthc') && length(args) == 1L)
        return(list(kind='call', name=name, arg=parse(args[1])))
      if (name == 'substr' && length(args) == 3L)
        return(list(kind='call', name=name, arg=parse(args[1]), pos=as.integer(args[2]), width=as.integer(args[3])))
    }
    stop('expression outside independent corpus witness')
  }
  compiled <- lapply(body, function(statement) {
    if (tolower(statement) == 'put _all_') return(list(kind='put'))
    m <- regmatches(statement, regexec('^([A-Za-z_][A-Za-z0-9_]*)\\s*=\\s*(.*)$', statement))[[1]]
    if (!length(m)) stop('statement outside independent corpus witness')
    expr <- parse(m[3])
    kind <- if (expr$kind == 'character' || (expr$kind == 'call' && expr$name == 'substr')) 'character' else 'number'
    width <- if (expr$kind == 'character') max(1L, nchar(expr$value)) else if (kind == 'character') expr$width else 0L
    register(m[2], kind, width)
    ref <- if (expr$kind == 'call') expr$arg else expr
    if (ref$kind == 'variable') register(ref$value, 'number')
    list(kind='assign', target=tolower(m[2]), expr=expr)
  })
  row <- lapply(order, function(key) if (types[[key]] == 'character') strrep(' ', widths[[key]]) else NA_real_)
  names(row) <- order
  value <- function(expr) {
    if (expr$kind == 'character') return(expr$value)
    if (expr$kind == 'variable') return(row[[tolower(expr$value)]])
    arg <- value(expr$arg)
    if (expr$name == 'substr') {
      if (!is.character(arg) || expr$pos < 1L || expr$width < 1L || expr$pos + expr$width - 1L > nchar(arg)) stop('SUBSTR bounds')
      return(substr(arg, expr$pos, expr$pos + expr$width - 1L))
    }
    # Numeric BEST12 conversion occupies twelve columns even when missing.
    if (!is.character(arg)) return(nchar(sprintf('%12s', if (is.na(arg)) '.' else '0')))
    if (expr$name == 'lengthc') return(nchar(arg))
    size <- nchar(sub(' +$', '', arg))
    if (expr$name == 'length') max(1L, size) else size
  }
  records <- character()
  for (op in compiled) {
    if (op$kind == 'assign') {
      x <- value(op$expr)
      if (types[[op$target]] == 'character') x <- substr(paste0(x, strrep(' ', widths[[op$target]])), 1L, widths[[op$target]])
      row[[op$target]] <- x
    } else {
      fields <- lapply(order, function(key) list(name=spelling[[key]], kind=types[[key]],
                  value=if (is.na(row[[key]])) '' else as.character(row[[key]]),
                  type=if (is.na(row[[key]])) 'missing' else if (types[[key]] == 'character') 'text' else 'number'))
      records <- c(records, hex(render_all(fields)))
    }
  }
  records
}

args <- commandArgs(trailingOnly=TRUE)
if (length(args) != 2L) stop('usage: Rscript put_all.R fields|program input')
if (args[1] == 'program') {
  cat(paste(program_records(args[2]), collapse='\n'), '\n', sep='')
} else {
  cases <- read.csv(args[2], colClasses='character', na.strings=NULL, check.names=FALSE)
  for (id in unique(cases$id)) {
    selected <- cases[cases$id == id & cases$kind != 'empty', , drop=FALSE]
    fields <- lapply(seq_len(nrow(selected)), function(i) as.list(selected[i, ]))
    result <- tryCatch(paste0('OK:', hex(render_all(fields))), error=function(e) paste0('ERROR:', conditionMessage(e)))
    cat(result, '\n', sep='')
  }
}
