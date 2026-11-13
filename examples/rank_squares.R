# Independent byte-array oracle and fixed original-program witness.
unhex<-function(x) {if(!nzchar(x)) return('');rawToChar(as.raw(strtoi(substring(x,seq(1,nchar(x),2),seq(2,nchar(x),2)),16L)))}
hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
ascii<-function(x) {
  if(!identical(class(x),'character') || length(x)!=1L || is.na(x)) stop('character')
  b<-as.integer(charToRaw(x))
  if(length(b)>32767L || any(b<32L | b>126L)) stop('ASCII bounds')
  b
}
integer_value<-function(x,low=-1000000,high=1000000,missing=TRUE) {
 if(!identical(class(x),'numeric') || length(x)!=1L || is.nan(x)) stop('numeric type')
 if(is.na(x)) {if(missing) return(x);stop('missing')}
 if(!is.finite(x) || x<low || x>high || x!=floor(x)) stop('integer domain');x
}
call_value<-function(name,args) {
 ranked<-name %in% c('largest','smallest')
 if(!(name %in% c('largest','smallest','css','uss')) || length(args)<if(ranked) 2L else 1L || length(args)>if(ranked) 33L else 32L) stop('arity or name')
 values<-unlist(lapply(if(ranked) args[-1L] else args,integer_value));nargs<-length(values)
 if(ranked) k<-integer_value(args[[1]],1,nargs,FALSE)
 values<-values[!is.na(values)];n<-length(values)
 if(ranked) {if(k>n) return(NA_real_);return(sort(values,decreasing=name=='largest')[k])}
 if(!n) return(NA_real_)
 if(name=='uss') return(sum(values*values))
 # Pairwise identity avoids subtracting large nearly equal raw sums.
 if(n==1L) return(0)
 pairs<-combn(values,2L);sum((pairs[1L,]-pairs[2L,])^2)/n
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
 required<-c('data reconciled','set raw','high=largest(k,a,b,c)','low=smallest(k,a,b,c)','centered=css(a,b,c)','uncentered=uss(a,b,c)','output','put high','put low','run')
 if(!identical(statements,required)) stop('original sequence')
 input<-read.csv(args[3],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
 if(!identical(names(input),c('tag','k','a','b','c'))) stop('schema')
 rows<-lapply(seq_len(nrow(input)),function(i) c(list(store(input$tag[i],4L)),lapply(input[i,2:5],function(x) if(nzchar(x)) as.numeric(x) else NA_real_)))
 cat('STATEMENTS|',length(statements),'\n',sep='');records<-character()
 for(row in rows) emit('raw',row)
 for(row in rows) {
  vals<-row[3:5];k<-row[[2]]
  out<-list(call_value('largest',c(list(k),vals)),call_value('smallest',c(list(k),vals)),call_value('css',vals),call_value('uss',vals))
  emit('reconciled',c(row,out));records<-c(records,vapply(out[c(1L,2L)],function(x) paste0(if(is.na(x)) '.' else sprintf('%.17g',x),' '),''))
 }
 for(record in records) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
