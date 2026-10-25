# Original, deliberately small independent program witness for the pinned
# external counted-DO/numeric-PUT program. It reads source in place and does
# not execute SAS or claim full language interpretation.
args <- commandArgs(trailingOnly=TRUE)
if (length(args) != 1L) stop('usage: Rscript do_put_program.R source.sas')
source <- paste(readLines(args[1], warn=FALSE), collapse='\n')
source <- gsub('(?s)/\\*.*?\\*/', '', source, perl=TRUE)
statements <- trimws(strsplit(source, ';', fixed=TRUE)[[1]])
statements <- statements[nzchar(statements)]
if (length(statements) != 5L || tolower(statements[1]) != 'data _null_' ||
    tolower(statements[4]) != 'end' || tolower(statements[5]) != 'run')
  stop('program outside independent witness structure')
header <- regmatches(statements[2], regexec(
  '^do[[:space:]]+([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*=[[:space:]]*([+-]?[0-9]+)[[:space:]]+to[[:space:]]+([+-]?[0-9]+)(?:[[:space:]]+by[[:space:]]+([+-]?[0-9]+))?$',
  statements[2], ignore.case=TRUE, perl=TRUE))[[1]]
if (!length(header)) stop('counted loop header required')
put <- regmatches(statements[3], regexec('^put[[:space:]]+([A-Za-z_][A-Za-z0-9_]*)$',
                                       statements[3], ignore.case=TRUE))[[1]]
if (!length(put) || tolower(put[2]) != tolower(header[2])) stop('PUT must name the loop index')
start <- as.numeric(header[3]); stop_value <- as.numeric(header[4])
step <- if (length(header) < 5L || !nzchar(header[5])) 1 else as.numeric(header[5])
controls <- c(start, stop_value, step)
if (any(!is.finite(controls)) || any(abs(controls) > 2^31-1) || step == 0) stop('controls outside witness policy')
index <- start
records <- character()
# Explicit post-body increment preserves the completed SAS control state;
# R's ordinary for-loop would leave its variable at the last body value.
while ((step > 0 && index <= stop_value) || (step < 0 && index >= stop_value)) {
  if (length(records) >= 10000L) stop('iteration limit')
  if (abs(index) > 99999999999 || index != trunc(index)) stop('numeric output outside BEST12 subset')
  text <- paste0(if (index == 0) '0' else sprintf('%.0f', index), ' ')
  if (nchar(text, type='bytes') > 64L) stop('record too wide')
  records <- c(records, paste(sprintf('%02x', as.integer(charToRaw(text))), collapse=''))
  index <- index + step
}
cat('STATE:', sprintf('%.0f', index), ':', length(records), '\n', sep='')
for (record in records) cat('RECORD:', record, '\n', sep='')
