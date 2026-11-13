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
  if(!(name %in% c('median','range','var','std')) || length(args)<1L || length(args)>32L) stop('arity')
  values<-vapply(args,function(x) {
    if(!identical(class(x),'numeric') || length(x)!=1L || is.nan(x)) stop('type')
    if(!is.na(x) && (!is.finite(x) || abs(x)>1000000 || x!=floor(x))) stop('domain')
    x
  },0)
  values<-values[!is.na(values)];n<-length(values)
  if(!n) return(NA_real_)
  if(name=='median') {
    v<-sort(values);return(if(n%%2L) v[(n+1L)/2L] else (v[n/2L]+v[n/2L+1L])/2)
  }
  if(name=='range') return(max(values)-min(values))
  if(n<2L) return(NA_real_)
  differences<-outer(values,values,'-')
  variance<-sum(differences*differences)/(2*n*(n-1))
  if(name=='std') sqrt(variance) else variance
}
decode<-function(x) {kind<-substr(x,1,1);v<-substring(x,3);switch(kind,c=unhex(v),n=as.numeric(v),m=NA_real_,t=structure(v,class='tagged'),b=TRUE,stop('encoding'))}
encode<-function(x) if(is.character(x)) paste0('c:',hex(x)) else if(is.na(x)) 'm:' else paste0('n:',sprintf('%.17g',x))
store<-function(x,w) paste0(substr(x,1,w),strrep(' ',max(0,w-nchar(x,type='bytes'))))
emit<-function(name,row) cat(paste(c('ROW',name,vapply(row,encode,'')),collapse='|'),'\n',sep='')
args<-commandArgs(trailingOnly=TRUE)
if(args[1]=='cases') {
  cases<-read.csv(args[2],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
  for(i in seq_len(nrow(cases))) cat(tryCatch(encode(call_value(cases$name[i],lapply(strsplit(cases$args[i],'|',fixed=TRUE)[[1]],decode))),error=function(e) 'REFUSE'),'\n',sep='')
} else if(args[1]=='program') {
  source<-gsub('(?s)/\\*.*?\\*/','',paste(readLines(args[2],warn=FALSE),collapse='\n'),perl=TRUE)
  statements<-trimws(strsplit(source,';',fixed=TRUE)[[1]]);statements<-statements[nzchar(statements)]
  required<-c('data stats','set raw','mid=median(a,b,c)','spread=range(a,b,c)','variance=var(a,b,c)','deviation=std(a,b,c)','output',"put 'measured'",'run')
  if(!identical(statements,required)) stop('original sequence')
  input<-read.csv(args[3],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
  if(!identical(names(input),c('a','b','c'))) stop('input schema')
  number<-function(x) if(!nzchar(x)) NA_real_ else as.numeric(x)
  rows<-lapply(seq_len(nrow(input)),function(i) lapply(input[i,],number))
  cat('STATEMENTS|',length(statements),'\n',sep='')
  for(row in rows) emit('raw',row)
  for(row in rows) emit('stats',c(row,lapply(c('median','range','var','std'),function(name) call_value(name,row))))
  for(row in rows) cat('LOG|',hex('measured'),'\n',sep='')
} else stop('mode')
