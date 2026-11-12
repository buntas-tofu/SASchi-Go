# Independent typed classification and sequential row-summary witness.
unhex<-function(x) {if(!nzchar(x)) return('');rawToChar(as.raw(strtoi(substring(x,seq(1,nchar(x),2),seq(2,nchar(x),2)),16L)))}
hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
text_value<-function(x) {
  if(!identical(class(x),'character') || length(x)!=1L || is.na(x)) stop('character')
  b<-as.integer(charToRaw(x));if(length(b)>32767L || any(b<32L | b>126L)) stop('ASCII bounds');x
}
number<-function(x,tags=FALSE,integer=FALSE) {
  if(inherits(x,'tagged')) {if(!tags || !grepl('^[_A-Z]$',unclass(x))) stop('tag');return(NA_real_)}
  if(!is.numeric(x) || length(x)!=1L || is.nan(x)) stop('numeric')
  if(is.na(x)) return(NA_real_)
  if(!is.finite(x) || abs(x)>2147483647 || (integer && x!=trunc(x))) stop('domain');x
}
missing_value<-function(x) {
  if(identical(class(x),'character')) return(!nzchar(gsub(' ','',text_value(x),fixed=TRUE)))
  is.na(number(x,TRUE))
}
call_value<-function(name,args) {
  if(length(args)<1L || length(args)>32L || (name=='missing' && length(args)!=1L)) stop('arity')
  if(name %in% c('missing','cmiss')) return(sum(vapply(args,missing_value,TRUE)))
  if(name=='coalescec') {
    values<-lapply(args,text_value);selected<-which(vapply(values,function(x) nzchar(gsub(' ','',x,fixed=TRUE)),TRUE))
    out<-if(length(selected)) values[[selected[1]]] else ''
    if(nchar(out)>200L) stop('result bounds');return(out)
  }
  if(!(name %in% c('n','nmiss','coalesce','mean'))) stop('function')
  values<-vapply(args,function(x) number(x,name %in% c('n','nmiss'),name=='mean'),0)
  if(name=='n') return(sum(!is.na(values)))
  if(name=='nmiss') return(sum(is.na(values)))
  values<-values[!is.na(values)];if(!length(values)) return(NA_real_)
  if(name=='coalesce') return(values[1])
  total<-0;for(v in values) total<-total+v;total/length(values)
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
  required<-c('data filled','set raw','flag=missing(name)','count=n(a,b)','miss=nmiss(a,b)','mixed=cmiss(name,a,b)','choice=coalesce(a,b)',"label=coalescec(name,backup,'NA')",'avg=mean(a,b)','output','put label','run')
  if(!identical(statements,required)) stop('original sequence')
  input<-read.csv(args[3],colClasses='character',na.strings=NULL,check.names=FALSE);cat('STATEMENTS|',length(statements),'\n',sep='')
  raw<-lapply(seq_len(nrow(input)),function(i) list(store(input$name[i],4L),store(input$backup[i],4L),if(nzchar(input$a[i])) as.numeric(input$a[i]) else NA_real_,if(nzchar(input$b[i])) as.numeric(input$b[i]) else NA_real_))
  for(row in raw) emit('raw',row)
  records<-character()
  for(row in raw) {
    numeric<-row[3:4];label<-call_value('coalescec',c(row[1:2],list('NA')))
    emit('filled',c(row,list(call_value('missing',row[1]),call_value('n',numeric),call_value('nmiss',numeric),call_value('cmiss',c(row[1],numeric)),call_value('coalesce',numeric),store(label,200L),call_value('mean',numeric))))
    records<-c(records,paste0(trimws(label,whitespace=' '),' '))
  }
  for(record in records) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
