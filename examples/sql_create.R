# Independent base-R descriptor-only SQL witness for maintainer review.
# No SQL engine, Python evaluation, live SAS or physical log claim.
reserved <- strsplit(paste('proc sql create table char character varchar numeric num integer int',
 'decimal float real double quit run select from where as like case when then else end',
 'join inner left right full outer on group by order having union intersect except',
 'insert into values update delete drop alter view constraint primary foreign key',
 'references not null check unique default distinct all _null_ _n_ _error_ _all_',
 '_numeric_ _character_ _temporary_ _infile_ _file_ _ods_ _page_ _blankpage_'),' ',fixed=TRUE)[[1]]
ordinary <- function(name) grepl('^[a-z_][a-z0-9_]{0,31}$',name,perl=TRUE) && !(name %in% reserved)
parse_create <- function(text) {
  if(nchar(text,type='bytes')>16384 || any(as.integer(charToRaw(text))>127)) stop('source bound')
  text <- tolower(trimws(text));tokens <- strsplit(gsub('([(),])',' \\1 ',text),'[[:space:]]+',perl=TRUE)[[1]]
  tokens <- tokens[nzchar(tokens)];at <- 1L
  take <- function(expected=NULL) {
    if(at>length(tokens)) stop('missing SQL token')
    token <- tokens[at];at <<- at+1L
    if(!is.null(expected) && token!=expected) stop('SQL token mismatch')
    token
  }
  take('create');take('table');name <- take();if(!ordinary(name)) stop('destination')
  take('(');columns <- list()
  repeat {
    column <- take();if(!ordinary(column) || !is.null(columns[[column]])) stop('column')
    take('char');take('(');width <- take();take(')')
    if(!grepl('^[1-9][0-9]{0,4}$',width) || as.numeric(width)>32767) stop('width')
    columns[[column]] <- as.integer(width)
    if(length(columns)>64L) stop('column count')
    next_token <- take()
    if(next_token==')') break
    if(next_token!=',') stop('column separator')
  }
  if(at<=length(tokens)) stop('unconsumed SQL tokens')
  list(name=name,columns=columns)
}
scan <- function(path) {
  text <- paste(readLines(path,warn=FALSE),collapse='\n');chars <- strsplit(text,'',fixed=TRUE)[[1]]
  at <- 1L;buffer <- '';statements <- character();block <- FALSE;quote <- '';star <- FALSE
  while(at<=length(chars)) {
    ch <- chars[at];after <- if(at<length(chars)) chars[at+1L] else ''
    if(block) {
      if(ch=='*' && after=='/') {block <- FALSE;buffer <- paste0(buffer,' ');at <- at+2L} else at <- at+1L
    } else if(star) {if(ch==';') star <- FALSE;at <- at+1L}
    else if(nzchar(quote)) {
      buffer <- paste0(buffer,ch);at <- at+1L
      if(ch==quote) {if(after==quote) {buffer <- paste0(buffer,after);at <- at+1L} else quote <- ''}
    } else if(ch=='/' && after=='*') {block <- TRUE;at <- at+2L}
    else if(ch=='*' && !nzchar(trimws(buffer))) {star <- TRUE;at <- at+1L}
    else if(ch %in% c("'",'"')) {quote <- ch;buffer <- paste0(buffer,ch);at <- at+1L}
    else if(ch==';') {
      statement <- trimws(buffer)
      if(nzchar(statement)) statements <- c(statements,statement)
      buffer <- '';at <- at+1L
    } else {buffer <- paste0(buffer,ch);at <- at+1L}
  }
  if(block || star || nzchar(quote) || nzchar(trimws(buffer))) stop('unconsumed source')
  statements
}
program <- function(path,existing=character()) {
  statements <- scan(path);at <- 1L;tables <- list();created <- character()
  while(at<=length(statements)) {
    if(tolower(gsub('[[:space:]]+',' ',statements[at]))!='proc sql') stop('bare PROC SQL required')
    at <- at+1L;if(at>length(statements)) stop('CREATE required')
    table <- parse_create(gsub('[[:space:]]+',' ',statements[at]));at <- at+1L
    if(table$name %in% c(tolower(existing),created)) stop('existing destination')
    if(at>length(statements) || tolower(statements[at])!='quit') stop('QUIT required')
    at <- at+1L;tables[[table$name]] <- table$columns;created <- c(created,table$name)
  }
  if(!length(tables)) stop('SQL program required')
  cat('STATEMENTS:',length(statements),'\n',sep='')
  for(name in names(tables)) {
    cat('TABLE:',name,'\n',sep='')
    for(column in names(tables[[name]])) cat('COLUMN:',column,',',tables[[name]][[column]],'\n',sep='')
    cat('ROWS:0\n')
  }
}
args <- commandArgs(trailingOnly=TRUE)
if(args[1]=='declaration') {
  text <- paste(readLines(args[2],warn=FALSE),collapse='\n')
  ok <- tryCatch({parse_create(text);TRUE},error=function(e) FALSE)
  cat(if(ok) 'OK' else 'REFUSE','\n',sep='')
} else if(args[1]=='program') {program(args[2],if(length(args)>2) strsplit(args[3],',',fixed=TRUE)[[1]] else character())} else if(args[1]=='batch') {
  cases <- read.csv(args[2],colClasses='character',na.strings=NULL)
  for(i in seq_len(nrow(cases))) {
    cat('CASE:',i-1L,'\n',sep='')
    ok <- tryCatch({program(cases$path[i],if(nzchar(cases$existing[i])) strsplit(cases$existing[i],',',fixed=TRUE)[[1]] else character());TRUE},error=function(e) FALSE)
    cat('ANSWER:',if(ok) 'OK' else 'REFUSE','\n',sep='')
  }
} else stop('witness mode')
