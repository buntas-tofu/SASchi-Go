# Independent byte-array oracle and fixed original-program witness.
unhex<-function(x) {if(!nzchar(x)) return('');rawToChar(as.raw(strtoi(substring(x,seq(1,nchar(x),2),seq(2,nchar(x),2)),16L)))}
hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
ascii<-function(x) {
  if(!identical(class(x),'character') || length(x)!=1L || is.na(x)) stop('character')
  b<-as.integer(charToRaw(x))
  if(length(b)>32767L || any(b<32L | b>126L)) stop('ASCII bounds')
  b
}
call_value<-function(name,args) {
  if(length(args)!=1L) stop('arity')
  b<-ascii(args[[1]]);n<-length(b)
  if(name=='left') {
    first<-which(b!=32L)
    if(!length(first)) return(rawToChar(as.raw(b)))
    i<-first[1];return(rawToChar(as.raw(c(b[seq.int(i,n)],rep(32L,i-1L)))))
  }
  if(name=='right') {
    last<-which(b!=32L)
    if(!length(last)) return(rawToChar(as.raw(b)))
    i<-tail(last,1L);return(rawToChar(as.raw(c(rep(32L,n-i),b[seq_len(i)]))))
  }
  if(name=='compbl') {
    selected<-if(n) c(TRUE,!(head(b,-1L)==32L & tail(b,-1L)==32L)) else logical()
    return(rawToChar(as.raw(b[selected])))
  }
  if(name!='trimn') stop('name')
  last<-which(b!=32L)
  rawToChar(as.raw(if(length(last)) b[seq_len(tail(last,1L))] else integer()))
}
decode<-function(x) {kind<-substr(x,1,1);v<-substring(x,3);switch(kind,c=unhex(v),n=as.numeric(v),m=NA_real_,t=structure(v,class='tagged'),b=TRUE,stop('encoding'))}
encode<-function(x) if(is.character(x)) paste0('c:',hex(x)) else if(is.na(x)) 'm:' else paste0('n:',sprintf('%.17g',x))
store<-function(x,w) paste0(substr(x,1,w),strrep(' ',max(0,w-nchar(x,type='bytes'))))
emit<-function(name,row) cat(paste(c('ROW',name,vapply(row,encode,'')),collapse='|'),'\n',sep='')
args<-commandArgs(trailingOnly=TRUE)
if(args[1]=='cases') {
  cases<-read.csv(args[2],colClasses='character',na.strings=NULL,check.names=FALSE)
  for(i in seq_len(nrow(cases))) cat(tryCatch(encode(call_value(cases$name[i],lapply(strsplit(cases$args[i],'|',fixed=TRUE)[[1]],decode))),error=function(e) 'REFUSE'),'\n',sep='')
} else if(args[1]=='program') {
  source<-gsub('(?s)/\\*.*?\\*/','',paste(readLines(args[2],warn=FALSE),collapse='\n'),perl=TRUE)
  statements<-trimws(strsplit(source,';',fixed=TRUE)[[1]]);statements<-statements[nzchar(statements)]
  required<-c('data cleaned','set raw','lefted=left(text)','righted=right(text)','spaced=compbl(text)','trimmed=trimn(text)','output',"if text ne '          ' then put spaced","if text ne '          ' then put trimmed",'run')
  if(!identical(statements,required)) stop('original sequence')
  input<-read.csv(args[3],colClasses='character',na.strings=NULL,check.names=FALSE)
  if(!identical(names(input),'text')) stop('input schema')
  cat('STATEMENTS|',length(statements),'\n',sep='')
  for(i in seq_len(nrow(input))) emit('raw',list(store(input$text[i],10L)))
  records<-character()
  for(i in seq_len(nrow(input))) {
    text<-store(input$text[i],10L)
    values<-lapply(c('left','right','compbl','trimn'),function(name) call_value(name,list(text)))
    emit('cleaned',c(list(text),lapply(values,store,w=10L)))
    if(any(ascii(text)!=32L)) records<-c(records,paste0(trimws(values[[3]],whitespace=' '),' '),paste0(trimws(values[[4]],whitespace=' '),' '))
  }
  for(record in records) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
