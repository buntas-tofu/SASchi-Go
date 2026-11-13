# Independent byte-array oracle and fixed original-program witness.
unhex<-function(x) {if(!nzchar(x)) return('');rawToChar(as.raw(strtoi(substring(x,seq(1,nchar(x),2),seq(2,nchar(x),2)),16L)))}
hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
ascii<-function(x) {
  if(!identical(class(x),'character') || length(x)!=1L || is.na(x)) stop('character')
  b<-as.integer(charToRaw(x))
  if(length(b)>32767L || any(b<32L | b>126L)) stop('ASCII bounds')
  b
}
num<-function(x) {
 if(!identical(class(x),'numeric') || length(x)!=1L || is.nan(x)) stop('numeric type')
 if(!is.na(x) && (!is.finite(x) || abs(x)>1000000)) stop('numeric bound');x
}
call_value<-function(name,args) {
 if(name %in% c('ifn','ifc')) {
  if(length(args)<3L || length(args)>4L) stop('IF arity')
  flag<-num(args[[1]]);choices<-args[-1L]
  if(name=='ifn') choices<-lapply(choices,num) else {
   bytes<-lapply(choices,ascii);if(any(lengths(bytes)>200L)) stop('character choice bound')
  }
  selected<-if(is.na(flag)) {if(length(choices)==3L) 3L else 2L} else if(flag!=0) 1L else 2L
  return(choices[[selected]])
 }
 if(!(name %in% c('choosen','choosec','whichn','whichc')) || length(args)<2L || length(args)>32L) stop('name or arity')
 character<-name %in% c('choosec','whichc')
 if(startsWith(name,'choose')) {
  index<-num(args[[1]]);choices<-args[-1L]
  if(character) {bytes<-lapply(choices,ascii);if(any(lengths(bytes)>200L)) stop('character bound')} else choices<-lapply(choices,num)
  if(is.na(index) || index!=floor(index) || index==0 || abs(index)>length(choices)) stop('CHOOSE index domain')
  selected<-if(index>0) index else length(choices)+index+1L;return(choices[[selected]])
 }
 if(character) {
  all<-lapply(args,ascii);if(any(lengths(all)>200L)) stop('character bound')
  values<-vapply(args,function(x) sub(' +$','',x),'');if(!nzchar(values[1L])) return(NA_real_)
 } else {values<-unlist(lapply(args,num));if(is.na(values[1L])) return(NA_real_)}
 found<-which(!is.na(values[-1L]) & values[-1L]==values[1L]);if(length(found)) found[1L] else 0L
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
 required<-c('data resolved','set raw','numeric=ifn(flag,a,b,c)','defaulted=ifn(flag,a,b)',"label=ifc(flag,'YES','NO','MISSING')","defaultlabel=ifc(flag,'Y','N')",'selected=choosen(idx,a,b,c)',"picked=choosec(idx,code,'TWO','END')",'where_n=whichn(a,b,a,a)',"where_c=whichc(code,'A','B','A')",'output','put numeric','put label','run')
 if(!identical(statements,required)) stop('original sequence')
 input<-read.csv(args[3],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
 if(!identical(names(input),c('flag','idx','a','b','c','code'))) stop('schema')
 rows<-lapply(seq_len(nrow(input)),function(i) c(lapply(input[i,1:5],function(x) if(nzchar(x)) as.numeric(x) else NA_real_),list(store(input$code[i],4L))))
 cat('STATEMENTS|',length(statements),'\n',sep='');records<-character()
 for(row in rows) emit('raw',row)
 for(row in rows) {
  f<-row[[1]];idx<-row[[2]];a<-row[[3]];b<-row[[4]];c<-row[[5]];code<-row[[6]]
  values<-list(call_value('ifn',list(f,a,b,c)),call_value('ifn',list(f,a,b)),call_value('ifc',list(f,'YES','NO','MISSING')),call_value('ifc',list(f,'Y','N')),call_value('choosen',list(idx,a,b,c)),call_value('choosec',list(idx,code,'TWO','END')),call_value('whichn',list(a,b,a,a)),call_value('whichc',list(code,'A','B','A')))
  saved<-values;for(k in c(3L,4L,6L)) saved[[k]]<-store(saved[[k]],200L)
  emit('resolved',c(row,saved));records<-c(records,paste0(if(is.na(values[[1]])) '.' else sprintf('%.17g',values[[1]]),' '),paste0(values[[3]],' '))
 }
 for(record in records) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
