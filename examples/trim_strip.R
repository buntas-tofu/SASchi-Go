# DS-043 independent byte-position and whole-program witness, no live SAS.
hex <- function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
unhex <- function(x) {
  if(!nzchar(x)) return('')
  if(nchar(x)%%2L) stop('hex')
  rawToChar(as.raw(strtoi(substring(x,seq(1,nchar(x),2),seq(2,nchar(x),2)),16L)))
}
shorten <- function(x,mode) {
  b<-as.integer(charToRaw(x)); n<-length(b)
  if(n<1L || n>32767L || any(b<32L | b>126L) || !(mode %in% c('trim','strip'))) stop('argument')
  occupied<-which(b!=32L)
  if(!length(occupied)) return(if(mode=='trim') ' ' else '')
  first<-if(mode=='trim') 1L else min(occupied)
  rawToChar(as.raw(b[first:max(occupied)]))
}
store_value <- function(x,width) {
  if(width<1L || width>32767L) stop('width')
  x<-substr(x,1L,width)
  paste0(x,strrep(' ',width-nchar(x,type='bytes')))
}
capture <- function(pattern,text) {
  m<-regmatches(text,regexec(paste0('(?i)^',pattern,'$'),text,perl=TRUE))[[1]]
  if(!length(m)) return(NULL)
  m[-1]
}
args<-commandArgs(trailingOnly=TRUE)
if(args[1]=='cases') {
  cases<-read.csv(args[2],colClasses='character',na.strings=NULL,check.names=FALSE)
  for(i in seq_len(nrow(cases))) {
    row<-cases[i,]
    result<-tryCatch({
      if(row$type!='character') stop('type')
      value<-unhex(row$value); raw<-shorten(value,row$mode)
      joined<-paste0('[',raw,']')
      paste('OK',hex(raw),hex(store_value(raw,as.integer(row$width))),
            hex(store_value(joined,nchar(value,type='bytes')+2L)),sep=':')
    },error=function(e) 'REFUSE')
    cat(result,'\n',sep='')
  }
} else if(args[1]=='program') {
  source<-paste(readLines(args[2],warn=FALSE),collapse='\n')
  source<-gsub('(?s)/\\*.*?\\*/','',source,perl=TRUE)
  statements<-trimws(strsplit(source,';',fixed=TRUE)[[1]])
  statements<-statements[nzchar(statements)]; at<-1L;steps<-list()
  parse_body<-function(terminator) {
    body<-list()
    while(at<=length(statements)) {
      text<-statements[at];at<<-at+1L
      if(tolower(text)==terminator) return(body)
      loop<-capture('do\\s+([a-z_]\\w*)\\s*=\\s*([0-9]+)\\s+to\\s+([0-9]+|[a-z_]\\w*)',text)
      if(!is.null(loop)) body[[length(body)+1L]]<-list(kind='loop',index=tolower(loop[1]),start=as.integer(loop[2]),stop=tolower(loop[3]),body=parse_body('end'))
      else {
        decl<-capture('length\\s+([a-z_]\\w*)\\s+\\$([0-9]+)',text)
        put<-capture('put\\s+([a-z_]\\w*)',text)
        assign<-capture('([a-z_]\\w*)\\s*=\\s*(.+)',text)
        node<-if(!is.null(decl)) list(kind='declare',name=tolower(decl[1]),width=as.integer(decl[2])) else
              if(!is.null(put)) list(kind='put',name=tolower(put[1])) else
              if(tolower(text)=='output') list(kind='output') else
              if(!is.null(assign)) list(kind='assign',name=tolower(assign[1]),rhs=assign[2]) else stop('unhandled statement')
        body[[length(body)+1L]]<-node
      }
    }
    stop('missing terminator')
  }
  while(at<=length(statements)) {
    header<-capture('data\\s+([a-z_]\\w*)',statements[at]);at<-at+1L
    if(is.null(header)) stop('DATA required')
    steps[[length(steps)+1L]]<-list(name=tolower(header[1]),body=parse_body('run'))
  }
  cat('STATEMENTS:',length(statements),'\n',sep='')
  for(si in seq_along(steps)) {
    step<-steps[[si]];schema<-list();row<-list();records<-character();rows<-list();explicit<-FALSE;trips<-0L
    text_atom<-function(text,descriptors=FALSE) {
      text<-trimws(text)
      literal<-capture("'([^']*)'|\"([^\"]*)\"",text)
      if(!is.null(literal)) {
        x<-paste0(literal,collapse='');if(!nzchar(x)) stop('empty literal outside witness')
        return(if(descriptors) nchar(x,type='bytes') else x)
      }
      if(!grepl('^[a-z_]\\w*$',text,perl=TRUE)) stop('atom')
      name<-tolower(text)
      if(is.null(schema[[name]]) || schema[[name]]==0L) stop('character descriptor')
      if(descriptors) schema[[name]] else row[[name]]
    }
    expression<-function(text,descriptors=FALSE) {
      pieces<-strsplit(text,'\\s*(?:\\|\\||!!)\\s*',perl=TRUE)[[1]]
      values<-lapply(pieces,function(piece) {
        call<-capture('(trim|strip)\\(([^()]*)\\)',trimws(piece))
        if(is.null(call)) text_atom(piece,descriptors) else {
          x<-text_atom(call[2],descriptors)
          if(descriptors) x else shorten(x,tolower(call[1]))
        }
      })
      if(descriptors) sum(unlist(values)) else paste0(unlist(values),collapse='')
    }
    discover<-function(body) {
      for(op in body) {
        if(op$kind=='declare') {schema[[op$name]]<<-op$width}
        else if(op$kind=='assign') {width<-expression(op$rhs,TRUE);if(is.null(schema[[op$name]])) schema[[op$name]]<<-width}
        else if(op$kind=='loop') {schema[[op$index]]<<-0L;discover(op$body)}
        else if(op$kind=='output') explicit<<-TRUE
        else if(op$kind!='put') stop('unhandled node')
      }
    }
    discover(step$body)
    for(name in names(schema)) row[[name]]<-if(schema[[name]]) strrep(' ',schema[[name]]) else NA_real_
    execute<-function(body) {
      for(op in body) {
        if(op$kind=='declare') next
        if(op$kind=='assign') row[[op$name]]<<-store_value(expression(op$rhs),schema[[op$name]])
        else if(op$kind=='loop') {
          stop<-if(grepl('^[0-9]+$',op$stop)) as.integer(op$stop) else row[[op$stop]]
          row[[op$index]]<<-op$start
          while(row[[op$index]]<=stop) {
            trips<<-trips+1L;if(trips>10000L) stop('budget')
            execute(op$body);row[[op$index]]<<-row[[op$index]]+1L
          }
        } else if(op$kind=='output') rows[[length(rows)+1L]]<<-row
        else if(op$kind=='put') {
          x<-shorten(row[[op$name]],'strip');if(!nzchar(x)) stop('blank PUT')
          records<<-c(records,paste0(x,' '))
        } else stop('unhandled execution')
      }
    }
    execute(step$body)
    if(!explicit) rows<-list(row)
    encode_row<-function(values) paste(vapply(names(schema),function(name) paste0(name,'=',if(schema[[name]]) paste0('C',hex(values[[name]])) else paste0('N',values[[name]])),''),collapse='|')
    cat('STEP:',si,':',step$name,'\n',sep='')
    cat('STATE:',encode_row(row),'\n',sep='');cat('TRIPS:',trips,'\n',sep='')
    if(step$name!='_null_') {
      for(name in names(schema)) cat('SCHEMA:',name,':',schema[[name]],'\n',sep='')
      for(values in rows) cat('ROW:',encode_row(values),'\n',sep='')
    }
    for(record in records) cat('RECORD:',hex(record),'\n',sep='')
  }
} else stop('unknown mode')
