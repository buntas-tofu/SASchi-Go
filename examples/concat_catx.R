# Original DS-029 witness: independent base-R character operations and parser.
hex <- function(value) paste(sprintf('%02x', as.integer(charToRaw(value))), collapse='')
unhex <- function(value) {
  if (!nzchar(value)) return('')
  rawToChar(as.raw(strtoi(substring(value, seq(1,nchar(value),2), seq(2,nchar(value),2)),16L)))
}
text <- function(value) {
  if (!is.character(value) || length(value)!=1L || nchar(value,type='bytes')<1L || nchar(value,type='bytes')>32767L) stop('character domain')
  if (any(as.integer(charToRaw(value))<32L | as.integer(charToRaw(value))>126L)) stop('ASCII domain')
  value
}
render <- function(mode, delimiter, fields) {
  if (mode=='concat') {
    if (length(fields)<2L || length(fields)>32L) stop('operand count')
    result <- paste(vapply(fields,text,''), collapse='')
    if (nchar(result,type='bytes')>32767L) stop('width')
  } else if (mode=='catx') {
    delimiter <- text(delimiter)
    if (length(fields)<1L || length(fields)>32L) stop('item count')
    stripped <- vapply(fields,function(x) sub(' +$','',sub('^ +','',text(x))), '')
    result <- paste(stripped[nzchar(stripped)],collapse=delimiter)
    if (nchar(result,type='bytes')>200L) stop('buffer')
  } else stop('mode')
  result
}
args <- commandArgs(trailingOnly=TRUE)
if (args[1]=='fixtures') {
  for (line in readLines(args[2],warn=FALSE)) {
    cells <- strsplit(line,'\t',fixed=TRUE)[[1]]
    decode <- function(x) if (startsWith(x,'C:')) unhex(substring(x,3)) else NA_real_
    result <- tryCatch(render(cells[1],decode(cells[2]),lapply(cells[-c(1,2)],decode)),error=function(e) NULL)
    cat(if(is.null(result)) 'ERROR' else paste0('OK:',hex(result)),'\n',sep='')
  }
} else if (args[1]=='program') {
  source <- paste(readLines(args[2],warn=FALSE),collapse='\n')
  source <- gsub('(?s)/\\*.*?\\*/',' ',source,perl=TRUE)
  statements <- strsplit(source,';',fixed=TRUE)[[1]]
  env <- new.env(parent=emptyenv()); widths <- new.env(parent=emptyenv()); records <- character(); started<-FALSE; ended<-FALSE
  token_pattern <- "'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"|[A-Za-z_][A-Za-z0-9_]*|!!|\\|\\||[(),]"
  literal <- function(x) substr(x,1,1) %in% c("'",'"')
  evaluate <- function(tokens) {
    if (length(tokens)==1L) {
      token<-tokens[1]
      if(literal(token)) {
        q<-substr(token,1,1); value<-substr(token,2,nchar(token)-1);value<-gsub(paste0(q,q),q,value,fixed=TRUE)
        return(list(value=text(value),width=nchar(value,type='bytes'),catx=FALSE))
      }
      name<-tolower(token);if(!exists(name,env,inherits=FALSE)) stop('unknown variable')
      return(list(value=get(name,env),width=get(name,widths),catx=FALSE))
    }
    if(tolower(tokens[1])=='catx') {
      if(tokens[2]!='(' || tail(tokens,1)!=')') stop('call')
      groups<-split(tokens[3:(length(tokens)-1)],cumsum(tokens[3:(length(tokens)-1)]==','))
      groups<-lapply(groups,function(x)x[x!=',']);if(any(lengths(groups)!=1L)) stop('call arguments')
      values<-lapply(groups,evaluate)
      return(list(value=render('catx',values[[1]]$value,lapply(values[-1],function(x)x$value)),width=200L,catx=TRUE))
    }
    if(length(tokens)%%2L!=1L || any(!tokens[seq(2,length(tokens),2)] %in% c('!!','||'))) stop('operator')
    values<-lapply(tokens[seq(1,length(tokens),2)],evaluate)
    list(value=render('concat',' ',lapply(values,function(x)x$value)),width=sum(vapply(values,function(x)x$width,0L)),catx=FALSE)
  }
  for(statement in statements) {
    statement<-trimws(statement);if(!nzchar(statement)||startsWith(statement,'*')) next
    if(grepl('^data[[:space:]]+_null_$',statement,ignore.case=TRUE)) {if(started) stop('step');started<-TRUE;next}
    if(tolower(statement)=='run') {ended<-TRUE;next}
    if(!started||ended) stop('step ordering')
    if(grepl('^put[[:space:]]+[A-Za-z_][A-Za-z0-9_]*$',statement,ignore.case=TRUE)) {
      name<-tolower(sub('^put[[:space:]]+','',statement,ignore.case=TRUE));value<-trimws(get(name,env));if(!nzchar(value)||nchar(value)>63L) stop('PUT domain')
      records<-c(records,paste0(value,' '));next
    }
    match<-regexec('^([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*=[[:space:]]*(.*)$',statement);parts<-regmatches(statement,match)[[1]]
    if(length(parts)!=3L) stop('statement')
    rhs<-parts[3];loc<-gregexpr(token_pattern,rhs,perl=TRUE);tokens<-regmatches(rhs,loc)[[1]]
    if(gsub('[[:space:]]','',gsub(token_pattern,'',rhs,perl=TRUE))!='') stop('unconsumed source')
    result<-evaluate(tokens);name<-tolower(parts[2]);width<-if(exists(name,widths,inherits=FALSE))get(name,widths) else result$width
    if(result$catx && nchar(result$value)>width) stop('destination overflow')
    assign(name,width,widths);assign(name,substr(paste0(result$value,strrep(' ',width)),1,width),env)
  }
  if(!ended) stop('missing RUN')
  cat('STATE:',length(records),':',length(ls(env)),'\n',sep='')
  for(record in records) cat('RECORD:',hex(record),'\n',sep='')
} else stop('mode')
