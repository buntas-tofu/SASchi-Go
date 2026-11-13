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
  if(!(name %in% c('cat','cats','catt')) || length(args)<1L || length(args)>32L) stop('arity or name')
  pieces<-lapply(args,ascii)
  if(name!='cat') pieces<-lapply(pieces,function(b) {
    nonblank<-which(b!=32L)
    if(!length(nonblank)) return(integer())
    if(name=='cats') b[seq.int(nonblank[1],tail(nonblank,1L))] else b[seq_len(tail(nonblank,1L))]
  })
  if(sum(lengths(pieces))>200L) stop('result bound')
  rawToChar(as.raw(unlist(pieces)))
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
  required<-c('data joined','set raw','rawcat=cat(a,b)','tight=cats(a,b)','tails=catt(a,b)','output',"if tight ne '                                                                                                                                                                                                        ' then put tight","if tails ne '                                                                                                                                                                                                        ' then put tails",'run')
  if(!identical(statements,required)) stop('original sequence')
  input<-read.csv(args[3],colClasses='character',na.strings=NULL,check.names=FALSE)
  if(!identical(names(input),c('a','b'))) stop('input schema')
  cat('STATEMENTS|',length(statements),'\n',sep='')
  for(i in seq_len(nrow(input))) emit('raw',list(store(input$a[i],8L),store(input$b[i],5L)))
  records<-character()
  for(i in seq_len(nrow(input))) {
    a<-store(input$a[i],8L);b<-store(input$b[i],5L)
    values<-lapply(c('cat','cats','catt'),function(name) call_value(name,list(a,b)))
    emit('joined',c(list(a,b),lapply(values,store,w=200L)))
    if(any(ascii(values[[2]])!=32L)) records<-c(records,paste0(trimws(values[[2]],whitespace=' '),' '))
    if(any(ascii(values[[3]])!=32L)) records<-c(records,paste0(trimws(values[[3]],whitespace=' '),' '))
  }
  for(record in records) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
