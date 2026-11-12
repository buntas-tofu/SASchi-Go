# Independently authored byte-delimiter and sequential original witness.
unhex<-function(x) {if(!nzchar(x)) return('');rawToChar(as.raw(strtoi(substring(x,seq(1,nchar(x),2),seq(2,nchar(x),2)),16L)))}
hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
ascii<-function(x) {
  if(!identical(class(x),'character') || length(x)!=1L || is.na(x)) stop('character')
  b<-as.integer(charToRaw(x));if(length(b)<1L || length(b)>32767L || any(b<32L | b>126L)) stop('ASCII bounds')
  x
}
words<-function(source,delimiters,modifier='') {
  source<-ascii(source);delimiters<-ascii(delimiters)
  if(nchar(delimiters)>64L || !identical(class(modifier),'character') || !(modifier %in% c('','m','M'))) stop('word options')
  b<-as.integer(charToRaw(source));separators<-as.integer(charToRaw(delimiters));keep<-nzchar(modifier)
  starts<-c(0L,which(b %in% separators),length(b)+1L);result<-list()
  for(i in seq_len(length(starts)-1L)) {
    left<-starts[i]+1L;right<-starts[i+1L]-1L
    if(left<=right) result[[length(result)+1L]]<-rawToChar(as.raw(b[left:right])) else if(keep) result[[length(result)+1L]]<-''
  }
  result
}
call_value<-function(name,args) {
  if(name=='countw') {
    if(length(args)<2L || length(args)>3L) stop('arity')
    return(length(words(args[[1]],args[[2]],if(length(args)==3L) args[[3]] else '')))
  }
  if(name!='scan' || length(args)<3L || length(args)>4L) stop('arity')
  n<-args[[2]]
  if(!is.numeric(n) || length(n)!=1L || !is.finite(n) || n!=trunc(n) || n==0 || abs(n)>2147483647) stop('count')
  modifier<-if(length(args)==4L) args[[4]] else '';parts<-words(args[[1]],args[[3]],modifier)
  index<-if(n>0) n else length(parts)+n+1L
  if(index<1 || index>length(parts)) return(if(nzchar(modifier)) '' else ' ')
  parts[[index]]
}
decode<-function(x) {kind<-substr(x,1,1);v<-substring(x,3);switch(kind,c=unhex(v),n=as.numeric(v),m=NA_real_,t=structure(v,class='tagged'),b=TRUE,stop('encoding'))}
encode<-function(x) if(is.character(x)) paste0('c:',hex(x)) else if(is.na(x)) 'm:' else paste0('n:',sprintf('%.17g',x))
store<-function(x,w) paste0(substr(x,1,w),strrep(' ',max(0,w-nchar(x,type='bytes'))))
emit<-function(name,row) cat(paste(c('ROW',name,vapply(row,encode,'')),collapse='|'),'\n',sep='')
args<-commandArgs(trailingOnly=TRUE)
if(args[1]=='cases') {
  cases<-read.csv(args[2],colClasses='character',na.strings=NULL,check.names=FALSE)
  for(i in seq_len(nrow(cases))) {
    values<-lapply(strsplit(cases$args[i],'|',fixed=TRUE)[[1]],decode)
    cat(tryCatch(encode(call_value(cases$name[i],values)),error=function(e) 'REFUSE'),'\n',sep='')
  }
} else if(args[1]=='program') {
  source<-gsub('(?s)/\\*.*?\\*/','',paste(readLines(args[2],warn=FALSE),collapse='\n'),perl=TRUE)
  statements<-trimws(strsplit(source,';',fixed=TRUE)[[1]]);statements<-statements[nzchar(statements)]
  required<-c('data words','set raw',"head=scan(text,1,'|')","tail=scan(text,-1,'|')","n=countw(text,'|')","m=countw(text,'|','M')",'output','put head','put tail','run')
  if(!identical(statements,required)) stop('original sequence')
  input<-read.csv(args[3],colClasses='character',na.strings=NULL,check.names=FALSE)
  cat('STATEMENTS|',length(statements),'\n',sep='')
  for(i in seq_len(nrow(input))) emit('raw',list(store(input$text[i],8L)))
  records<-character()
  for(i in seq_len(nrow(input))) {
    text<-store(input$text[i],8L);head<-call_value('scan',list(text,1,'|'));tail<-call_value('scan',list(text,-1,'|'))
    emit('words',list(text,store(head,8L),store(tail,8L),call_value('countw',list(text,'|')),call_value('countw',list(text,'|','M'))))
    records<-c(records,paste0(trimws(head,whitespace=' '),' '),paste0(trimws(tail,whitespace=' '),' '))
  }
  for(record in records) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
