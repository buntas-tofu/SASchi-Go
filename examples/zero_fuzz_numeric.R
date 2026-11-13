# Independent byte-array oracle and fixed original-program witness.
unhex<-function(x) {if(!nzchar(x)) return('');rawToChar(as.raw(strtoi(substring(x,seq(1,nchar(x),2),seq(2,nchar(x),2)),16L)))}
hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
ascii<-function(x) {
  if(!identical(class(x),'character') || length(x)!=1L || is.na(x)) stop('character')
  b<-as.integer(charToRaw(x))
  if(length(b)>32767L || any(b<32L | b>126L)) stop('ASCII bounds')
  b
}
bounded<-function(x) {
 if(!identical(class(x),'numeric') || length(x)!=1L || is.nan(x)) stop('numeric type')
 if(!is.na(x) && (!is.finite(x) || abs(x)>1000000 || (x!=0 && abs(x)<2^-40))) stop('bounded normal operand');x
}
unit_value<-function(x,signed=FALSE) {
 x<-bounded(x);if(is.na(x)) return(x)
 if(x==0 || (!signed && x<0)) stop('nonzero unit')
 if(!(abs(x) %in% (2^seq.int(-10L,10L)))) stop('power of two unit');x
}
call_value<-function(name,args) {
 if(!(name %in% c('ceilz','floorz','intz','roundz','modz'))) stop('name')
 lower<-if(name=='modz') 2L else 1L;upper<-if(name %in% c('roundz','modz')) 2L else 1L
 if(length(args)<lower || length(args)>upper) stop('arity')
 x<-bounded(args[[1]])
 unit<-if(name %in% c('roundz','modz')) unit_value(if(length(args)==2L) args[[2]] else 1,name=='modz') else 1
 if(is.na(x) || is.na(unit)) return(NA_real_)
 answer<-switch(name,ceilz=ceiling(x),floorz=floor(x),intz=trunc(x),roundz=round(x/unit)*unit,modz=sign(x)*(abs(x)%%abs(unit)))
 if(answer==0) 0 else answer
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
 source<-paste(readLines(args[2],warn=FALSE),collapse='\n');statements<-trimws(strsplit(source,';',fixed=TRUE)[[1]]);statements<-statements[nzchar(statements)]
 required<-c('data quantities','set raw','raised=ceilz(x)','lowered=floorz(x)','integral=intz(x)','nearest=roundz(x,unit)','remainder=modz(x,divisor)','output','put raised','put integral','run')
 if(!identical(statements,required)) stop('original sequence')
 input<-read.csv(args[3],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
 if(!identical(names(input),c('tag','x','unit','divisor'))) stop('schema')
 rows<-lapply(seq_len(nrow(input)),function(i) c(list(store(input$tag[i],4L)),lapply(input[i,2:4],function(x) if(nzchar(x)) as.numeric(x) else NA_real_)))
 cat('STATEMENTS|',length(statements),'\n',sep='');records<-character()
 for(row in rows) emit('raw',row)
 for(row in rows) {
  x<-row[[2]];u<-row[[3]];d<-row[[4]]
  out<-c(lapply(c('ceilz','floorz','intz'),function(name) call_value(name,list(x))),list(call_value('roundz',list(x,u)),call_value('modz',list(x,d))))
  emit('quantities',c(row,out));records<-c(records,vapply(out[c(1L,3L)],function(x) paste0(if(is.na(x)) '.' else sprintf('%.17g',x),' '),''))
 }
 for(record in records) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
