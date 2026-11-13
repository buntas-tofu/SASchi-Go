# Independently authored bounded normalization and predicate kernels.
here<-dirname(normalizePath(sub('^--file=','',commandArgs()[grep('^--file=',commandArgs())][1])))
source(file.path(here,'function_wave2_oracles.R'))
consumer_missing<-function(x) {
  if(inherits(x,'tagged')) {
    if(length(x)!=1L || nchar(x)!=1L || !(as.character(x) %in% c('_',LETTERS))) stop('missing tag')
    return(1)
  }
  if(identical(class(x),'character')) return(missing_value(x))
  if(!identical(class(x),'numeric') || length(x)!=1L || is.nan(x) || (!is.na(x) && (!is.finite(x) || abs(x)>2147483647))) stop('missing domain')
  as.numeric(is.na(x))
}
consumer_kernel<-function(name,args) {
  key<-strsplit(name,':',fixed=TRUE)[[1]]
  if(key[1]=='chain') {
    if(length(key)!=2L || length(args)!=1L) stop('chain arity')
    chain<-strsplit(key[2],',',fixed=TRUE)[[1]]
    allowed<-c('upcase','lowcase','trim','strip','trimn','compbl')
    if(length(chain)<2L || length(chain)>3L || any(!(chain %in% allowed))) stop('chain grammar')
    text<-rawToChar(as.raw(ws_ascii(args[[1]])));width<-nchar(text,type='bytes')
    if(!width) stop('source leaf')
    for(fn in rev(chain)) {
      if(fn=='upcase') text<-upper_text(text)
      else if(fn=='lowcase') text<-lower_text(text)
      else if(fn=='strip') text<-strip_text(text)
      else if(fn=='trim') {text<-ws_call_value('trimn',list(text));if(!nzchar(text)) text<-' '}
      else text<-ws_call_value(fn,list(text))
    }
    return(store(text,width))
  }
  if(key[1]!='pred' || length(key)!=3L || length(args)<2L) stop('predicate shape')
  fn<-key[2];op<-key[3];right<-tail(args,1L)[[1]];left_args<-head(args,-1L)
  if(!identical(class(right),'numeric') || length(right)!=1L || is.na(right) || !is.finite(right) || right<0 || right>32767 || right!=floor(right)) stop('predicate literal')
  if(fn=='missing') {
    if(length(left_args)!=1L) stop('missing arity')
    value<-consumer_missing(left_args[[1]])
  } else {
    if(!(fn %in% c('verify','anyalpha','anydigit','anyalnum','anyspace','notdigit'))) stop('predicate function')
    value<-val_call_value(fn,left_args)
  }
  result<-if(op %in% c('=','eq')) value==right else if(op %in% c('^=','~=','<>','ne')) value!=right else if(op %in% c('<','lt')) value<right else if(op %in% c('>','gt')) value>right else if(op %in% c('<=','le')) value<=right else if(op %in% c('>=','ge')) value>=right else stop('comparison')
  as.numeric(result)
}
args<-commandArgs(trailingOnly=TRUE)
cases<-read.csv(args[1],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
for(i in seq_len(nrow(cases))) cat(tryCatch(encode(consumer_kernel(cases$name[i],lapply(strsplit(cases$args[i],'|',fixed=TRUE)[[1]],decode))),error=function(e) 'REFUSE'),'\n',sep='')
