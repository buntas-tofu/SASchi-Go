# Independent finite complete-source oracle for the pinned vendor INVALUE target.
# Reads an external source file. No Python plans, helpers or vendor rows here.
args <- commandArgs(trailingOnly=TRUE)
if (length(args) != 2L) stop('source and fresh temporary output directory required')
input_path <- normalizePath(args[1], mustWork=TRUE)
output_path <- args[2]
temp_root <- file.path(normalizePath(tempdir(), mustWork=TRUE), '..')
temp_root <- paste0(normalizePath(temp_root, mustWork=TRUE), '/saschi-vendor-invalue-')
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
  if (tolower(statement) == 'datalines') {
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

# The scanner above consumes the original file independently of Python.
statements <- Filter(function(x) x$kind == 'statement', events)
stopifnot(length(statements) == 13L, length(events) == 14L,
          identical(vapply(statements, function(x) x$line, 1L), c(13L,14L,20L,22L,23L,24L,34L,35L,36L,37L,39L,40L,41L)))
texts <- vapply(statements, function(x) x$text, '')
normalized <- tolower(gsub('[ \t\r\n]+', ' ', texts))
stopifnot(normalized[1] == 'proc format', all(normalized[c(3,7,11,13)] == 'run'),
          normalized[4] == 'data evals', normalized[5] == 'input id $ @6 string $9. @6 evaluation eval.',
          normalized[6] == 'datalines', normalized[9] == 'proc print data=evals label noobs',
          normalized[12] == 'proc means data=evals')
rest <- sub('^invalue[ \t\r\n]+eval[ \t\r\n]+', '', texts[2], ignore.case=TRUE)
entries <- regmatches(rest, gregexpr("'[^']+'[ \t\r\n]*=[ \t\r\n]*[0-9]+", rest, perl=TRUE))[[1]]
stopifnot(length(entries) == 4L)
keys <- sub("^'([^']+)'.*$", '\\1', entries)
mapping <- as.integer(sub('^.*=[ \t\r\n]*', '', entries)); names(mapping) <- keys
stopifnot(max(nchar(keys, type='bytes')) == 9L, identical(unname(mapping), c(4L,3L,2L,1L)))
payload <- Filter(function(x) x$kind == 'opaque_data', events)[[1]]
stopifnot(payload$line == 25L, payload$terminator_line == 33L, length(payload$records) == 8L,
          all(nchar(payload$records, type='bytes') == 14L))
schema <- list(id=list(type='character',length=8L), string=list(type='character',length=9L), evaluation=list(type='number',length=8L))
rows <- lapply(payload$records, function(card) {
 id <- substr(card,1L,4L); raw <- substr(card,6L,14L); token <- sub(' +$', '', raw)
 stopifnot(grepl('^[0-9]{4}$', id), substr(card,5L,5L) == ' ')
 value <- if (token %in% names(mapping)) unname(mapping[token]) else as.numeric(token)
 stopifnot(is.finite(value), value == trunc(value), abs(value) <= 1000)
 list(id=paste0(id,'    '), string=paste0(sub('^ +','',raw),strrep(' ',9L-nchar(sub('^ +','',raw)))), evaluation=as.numeric(value))
})
values <- vapply(rows,function(row) row$evaluation,0)
stopifnot(identical(values,c(3,2,4,1,2,4,3,3)),sum(values)==22,sum(values^2)==68)
title <- sub("^title[ \t]+'([^']+)'$",'\\1',texts[8],ignore.case=TRUE)
label_entries <- regmatches(texts[10],gregexpr('[A-Za-z_]+[ \t]*=[ \t]*"[^"]+"',texts[10],perl=TRUE))[[1]]
labels <- sub('^[^=]+=[ \t]*"([^"]+)"$','\\1',label_entries)
names(labels) <- tolower(sub('[ \t]*=.*$','',label_entries))
json_string <- function(x) encodeString(x,quote='"',justify='none')
integer_text <- function(x) format(x,scientific=FALSE,trim=TRUE,digits=15)
header <- paste(vapply(names(schema),function(name) json_string(if(name %in% names(labels)) labels[name] else name),''),collapse=' ')
print_records <- c(paste0('TITLE: ',title),header,vapply(rows,function(row) paste(json_string(sub(' +$','',row$id)),json_string(sub(' +$','',row$string)),integer_text(row$evaluation)),''))
# Base R mean/sd are independent of the engine's integer-square renderer. The
# original target lies well away from a decimal rounding boundary.
mean_token <- sprintf('%.8f',mean(values)); std_token <- sprintf('%.8f',sd(values))
stopifnot(mean_token=='2.75000000',std_token=='1.03509834')
means_records <- c(paste0('TITLE: ',title),'variable n mean std min max',paste('"evaluation"',length(values),mean_token,std_token,min(values),max(values)))
reports <- list(print_01.txt=paste0(paste(print_records,collapse='\n'),'\n'),means_01.txt=paste0(paste(means_records,collapse='\n'),'\n'))
result <- list(datasets=list(evals=list(schema=schema,rows=rows)),log=list(),reports=reports)
accounting <- list(language_statements=13L,opaque_payloads=1L,steps=5L,input_records=8L,data_iterations=8L,input_attempts=9L,implicit_outputs=8L,title_sets=1L,prints=1L,means=1L,report_records=list(10L,3L),final_title=title)
hex <- function(text) paste0(sprintf('%02x',as.integer(charToRaw(text))),collapse='')
trace <- list(); add <- function(x) trace[[length(trace)+1L]] <<- x
for(i in 1:9) {
 add(list(kind='formatted_input',line=23L,attempt=as.integer(i),complete=i<9))
 if(i<9) add(list(kind='formatted_output',line=23L,observation=as.integer(i)))
}
add(paste0('informat-title|set|',hex(title)))
add('labelled-print|input|evals|8'); add(paste0('labelled-print|title|',hex(print_records[1]))); add(paste0('labelled-print|header|',hex(header)))
for(record in print_records[-c(1,2)]) add(paste0('labelled-print|row|',hex(record)))
add(paste0('labelled-print|output|print_01.txt|',nchar(reports$print_01.txt,type='bytes')))
add('default-means|input|evals|8'); add(paste0('default-means|title|',hex(means_records[1]))); add(paste0('default-means|header|',hex(means_records[2])))
add('default-means|stats|evaluation|8|22|68|11/4|15/14'); add(paste0('default-means|row|',hex(means_records[3])))
add(paste0('default-means|output|means_01.txt|',nchar(reports$means_01.txt,type='bytes')))
stopifnot(length(trace)==36L)
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
