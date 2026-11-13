# Independent byte-position oracle. No Python implementation is imported.
unhex<-function(x) {if(!nzchar(x)) return('');rawToChar(as.raw(strtoi(substring(x,seq(1,nchar(x),2),seq(2,nchar(x),2)),16L)))}
hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
ascii<-function(x) {
 if(!identical(class(x),'character') || length(x)!=1L || is.na(x)) stop('character')
 b<-as.integer(charToRaw(x));if(length(b)>32767L || any(b<32L | b>126L)) stop('ASCII bounds');b
}
text<-function(b) rawToChar(as.raw(b))
call_value<-function(name,args) {
 limits<-switch(name,propcase=c(2L,2L),quote=c(1L,2L),dequote=c(1L,1L),countc=c(2L,3L),transtrn=c(3L,3L),stop('name'))
 if(length(args)<limits[1] || length(args)>limits[2]) stop('arity')
 all<-lapply(args,ascii);b<-all[[1]];n<-length(b)
 if(name=='propcase') {
  delimiters<-all[[2]];if(!length(delimiters) || length(delimiters)>64L) stop('delimiters')
  starts<-if(n) c(TRUE,head(b,-1L) %in% delimiters) else logical()
  upper<-b>=65L & b<=90L;b[upper]<-b[upper]+32L
  chosen<-starts & b>=97L & b<=122L;b[chosen]<-b[chosen]-32L
  return(text(b))
 }
 if(name=='quote') {
  q<-if(length(args)==1L) 34L else all[[2]]
  if(length(q)!=1L || !(q %in% c(34L,39L))) stop('quote character')
  result<-c(q,unlist(lapply(b,function(x) if(x==q) c(x,x) else x)),q)
  if(length(result)>200L) stop('QUOTE buffer');return(text(result))
 }
 if(name=='dequote') {
  if(!n || !(b[1L] %in% c(34L,39L))) return(text(b))
  q<-b[1L];out<-integer();i<-2L
  while(i<=n) {
   if(b[i]==q) {if(i<n && b[i+1L]==q) {out<-c(out,q);i<-i+2L;next};break}
   out<-c(out,b[i]);i<-i+1L
  }
  return(text(out))
 }
 if(name=='countc') {
  chars<-all[[2]];if(length(chars)>64L) stop('set bound')
  m<-if(length(args)==3L) toupper(text(all[[3]])) else ''
  if(nchar(m)>3L || grepl('[^IVT]',m)) stop('modifier')
  if(grepl('T',m,fixed=TRUE)) {b<-as.integer(charToRaw(sub(' +$','',text(b))));chars<-as.integer(charToRaw(sub(' +$','',text(chars))))}
  if(grepl('I',m,fixed=TRUE)) {b[b>=65L & b<=90L]<-b[b>=65L & b<=90L]+32L;chars[chars>=65L & chars<=90L]<-chars[chars>=65L & chars<=90L]+32L}
  if(!length(chars)) return(0L)
  found<-b %in% chars;return(sum(if(grepl('V',m,fixed=TRUE)) !found else found))
 }
 target<-all[[2]];replacement<-all[[3]]
 if(!length(target) || length(target)>64L || length(replacement)>64L) stop('replacement bounds')
 out<-integer();i<-1L
 while(i<=n) {
  end<-i+length(target)-1L
  if(end<=n && identical(b[seq.int(i,end)],target)) {out<-c(out,replacement);i<-end+1L} else {out<-c(out,b[i]);i<-i+1L}
 }
 if(length(out)>200L) stop('TRANSTRN result bound');text(out)
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
 required<-c('data quoted','set raw',"proper=propcase(label,' -')",'quoted=quote(code)','unquoted=dequote(code)',"marks=countc(label,'- ')","folded=countc(label,'a','it')","rewritten=transtrn(label,'-','__')",'output','put quoted','run')
 if(!identical(statements,required)) stop('original sequence')
 input<-read.csv(args[3],colClasses='character',na.strings=NULL,check.names=FALSE)
 if(!identical(names(input),c('label','code'))) stop('schema')
 cat('STATEMENTS|',length(statements),'\n',sep='');records<-character()
 for(i in seq_len(nrow(input))) emit('raw',list(store(input$label[i],12L),store(input$code[i],10L)))
 for(i in seq_len(nrow(input))) {
  label<-store(input$label[i],12L);code<-store(input$code[i],10L)
  values<-list(call_value('propcase',list(label,' -')),call_value('quote',list(code)),call_value('dequote',list(code)),call_value('countc',list(label,'- ')),call_value('countc',list(label,'a','it')),call_value('transtrn',list(label,'-','__')))
  emit('quoted',c(list(label,code),list(store(values[[1]],12L),store(values[[2]],200L),store(values[[3]],10L),values[[4]],values[[5]],store(values[[6]],200L))))
  records<-c(records,paste0(trimws(values[[2]],whitespace=' '),' '))
 }
 for(record in records) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
