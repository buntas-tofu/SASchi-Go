# Independent byte-array oracle and fixed original-program witness.
unhex<-function(x) {if(!nzchar(x)) return('');rawToChar(as.raw(strtoi(substring(x,seq(1,nchar(x),2),seq(2,nchar(x),2)),16L)))}
hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
ascii<-function(x) {
  if(!identical(class(x),'character') || length(x)!=1L || is.na(x)) stop('character')
  b<-as.integer(charToRaw(x))
  if(length(b)>32767L || any(b<32L | b>126L)) stop('ASCII bounds')
  b
}
integer_value<-function(x,low,high) {
 if(!identical(class(x),'numeric') || length(x)!=1L || is.nan(x)) stop('numeric type')
 if(is.na(x)) return(x)
 if(!is.finite(x) || x<low || x>high || x!=floor(x)) stop('integer domain');x
}
epoch<-as.Date('1960-01-01');min_day<-as.numeric(as.Date('1753-01-01')-epoch);max_day<-as.numeric(as.Date('3999-12-31')-epoch)
call_value<-function(name,args) {
 limits<-switch(name,hms=list(c(0,23),c(0,59),c(0,59)),yyq=list(c(1753,3999),c(1,4)),datejul=list(c(1753001,3999366)),juldate7=list(c(min_day,max_day)),stop('name'))
 if(length(args)!=length(limits)) stop('arity')
 values<-mapply(function(x,bounds) integer_value(x,bounds[1],bounds[2]),args,limits)
 if(any(is.na(values))) return(NA_real_)
 if(name=='hms') return(sum(values*c(3600,60,1)))
 if(name=='yyq') return(as.numeric(as.Date(sprintf('%04d-%02d-01',values[1],3L*values[2]-2L))-epoch))
 if(name=='datejul') {
  year<-values[1]%/%1000;day<-values[1]%%1000
  start<-as.Date(sprintf('%04d-01-01',year));last<-as.Date(sprintf('%04d-12-31',year))
  if(day<1 || day>as.numeric(last-start)+1L) stop('ordinal day domain')
  return(as.numeric(start+day-1L-epoch))
 }
 date<-epoch+values[1];as.numeric(format(date,'%Y'))*1000+as.numeric(format(date,'%j'))
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
 required<-c('data civil','set raw','clock=hms(hour,minute,second)','quarterdate=yyq(year,quarter)','date=datejul(ordinal)','quarterordinal=juldate7(quarterdate)','recovered=juldate7(date)','output','put clock','put recovered','run')
 if(!identical(statements,required)) stop('original sequence')
 input<-read.csv(args[3],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
 if(!identical(names(input),c('tag','year','quarter','ordinal','hour','minute','second'))) stop('schema')
 rows<-lapply(seq_len(nrow(input)),function(i) c(list(store(input$tag[i],4L)),lapply(input[i,2:7],function(x) if(nzchar(x)) as.numeric(x) else NA_real_)))
 cat('STATEMENTS|',length(statements),'\n',sep='');records<-character()
 for(row in rows) emit('raw',row)
 for(row in rows) {
  clock<-call_value('hms',row[5:7]);quarter<-call_value('yyq',row[2:3]);date<-call_value('datejul',row[4])
  out<-list(clock,quarter,date,call_value('juldate7',list(quarter)),call_value('juldate7',list(date)))
  emit('civil',c(row,out));records<-c(records,vapply(out[c(1L,5L)],function(x) paste0(if(is.na(x)) '.' else sprintf('%.17g',x),' '),''))
 }
 for(record in records) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
