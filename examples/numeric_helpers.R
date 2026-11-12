# Independent directional arithmetic and sequential original numeric witness.
unhex<-function(x) {if(!nzchar(x)) return('');rawToChar(as.raw(strtoi(substring(x,seq(1,nchar(x),2),seq(2,nchar(x),2)),16L)))}
hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
call_value<-function(name,args) {
  if(length(args)!=1L || !(name %in% c('abs','sign','ceil','floor'))) stop('arity/name')
  x<-args[[1]]
  if(!is.numeric(x) || length(x)!=1L || is.nan(x)) stop('numeric')
  if(is.na(x)) return(NA_real_)
  if(!is.finite(x) || abs(x)>2147483647 || (x!=0 && abs(x)<.Machine$double.xmin)) stop('domain')
  if(name=='abs') return(if(x<0) -x else x)
  if(name=='sign') return(if(x<0) -1 else if(x>0) 1 else 0)
  nearest<-round(x)
  if(abs(x-nearest)<=1e-12) return(nearest)
  truncated<-trunc(x)
  if(name=='ceil') truncated+if(x>truncated) 1 else 0 else truncated-if(x<truncated) 1 else 0
}
decode<-function(x) {kind<-substr(x,1,1);v<-substring(x,3);switch(kind,c=unhex(v),n=as.numeric(v),m=NA_real_,t=structure(v,class='tagged'),b=TRUE,stop('encoding'))}
encode<-function(x) if(is.character(x)) paste0('c:',hex(x)) else if(is.na(x)) 'm:' else paste0('n:',sprintf('%.17g',x))
emit<-function(name,row) cat(paste(c('ROW',name,vapply(row,encode,'')),collapse='|'),'\n',sep='')
args<-commandArgs(trailingOnly=TRUE)
if(args[1]=='cases') {
  cases<-read.csv(args[2],colClasses='character',na.strings=NULL,check.names=FALSE)
  for(i in seq_len(nrow(cases))) cat(tryCatch(encode(call_value(cases$name[i],lapply(strsplit(cases$args[i],'|',fixed=TRUE)[[1]],decode))),error=function(e) 'REFUSE'),'\n',sep='')
} else if(args[1]=='program') {
  source<-gsub('(?s)/\\*.*?\\*/','',paste(readLines(args[2],warn=FALSE),collapse='\n'),perl=TRUE)
  statements<-trimws(strsplit(source,';',fixed=TRUE)[[1]]);statements<-statements[nzchar(statements)]
  required<-c('data metrics','set raw','magnitude=abs(x)','direction=sign(x)','ceiling=ceil(x)','floor=floor(x)','shown=put(magnitude,8.2)','output','put shown','run')
  if(!identical(statements,required)) stop('original sequence')
  input<-read.csv(args[3],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE);values<-vapply(input$x,function(x) if(nzchar(x)) as.numeric(x) else NA_real_,0)
  cat('STATEMENTS|',length(statements),'\n',sep='');for(x in values) emit('raw',list(x))
  records<-character()
  for(x in values) {
    magnitude<-call_value('abs',list(x));shown<-if(is.na(magnitude)) '       .' else sprintf('%8.2f',magnitude)
    emit('metrics',list(x,magnitude,call_value('sign',list(x)),call_value('ceil',list(x)),call_value('floor',list(x)),shown))
    records<-c(records,paste0(trimws(shown,whitespace=' '),' '))
  }
  for(record in records) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
