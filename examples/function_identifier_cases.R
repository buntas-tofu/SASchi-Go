# Independent nested-item identifier witness, before source admission.
here<-dirname(normalizePath(sub('^--file=','',commandArgs()[grep('^--file=',commandArgs())][1])))
source(file.path(here,'function_wave2_oracles.R'))
identifier_kernel<-function(fn,args) {
  if(length(args)<3L) stop('identifier arity')
  prefix<-args[[1]];suffix<-tail(args,1L)[[1]];item<-args[seq.int(2L,length(args)-1L)]
  if(fn %in% c('upcase','lowcase','trim','strip')) {
    if(length(item)!=1L) stop('item arity')
    text<-rawToChar(as.raw(ws_ascii(item[[1]])))
    value<-switch(fn,upcase=upper_text(text),lowcase=lower_text(text),strip=strip_text(text),trim={x<-ws_call_value('trimn',list(text));if(nzchar(x)) x else ' '})
  } else if(fn %in% c('left','right','compbl','trimn')) value<-ws_call_value(fn,item)
  else if(fn=='substrn') value<-search_call_value(fn,item)
  else stop('item identity')
  store(cat_call_value('cats',list(prefix,value,suffix)),200L)
}
args<-commandArgs(trailingOnly=TRUE)
cases<-read.csv(args[1],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
for(i in seq_len(nrow(cases))) cat(tryCatch(encode(identifier_kernel(cases$name[i],lapply(strsplit(cases$args[i],'|',fixed=TRUE)[[1]],decode))),error=function(e) 'REFUSE'),'\n',sep='')
