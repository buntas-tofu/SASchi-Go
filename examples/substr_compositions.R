# Original independent composed fixed-character witness for maintainer review.
# Candidate documentary rules plus repository/base-R evidence, no live SAS.
args<-commandArgs(trailingOnly=TRUE)
hex<-function(x) paste(sprintf('%02x',as.integer(x)),collapse='')
unhex<-function(x) { if (!nzchar(x)) return(raw()); as.raw(strtoi(substring(x,seq(1,nchar(x),2),seq(2,nchar(x),2)),16L)) }
text<-function(x) { b<-unhex(x);if(length(b)<1 || length(b)>32767 || any(as.integer(b)<32 | as.integer(b)>126)) stop('text');b }
pad<-function(x,w) head(c(x,as.raw(rep(32L,w))),w)
catx<-function(delim,fields) {
  fields<-vapply(fields,function(x) trimws(rawToChar(x),whitespace=' '),'')
  result<-charToRaw(paste(fields[nzchar(fields)],collapse=rawToChar(delim)))
  if(length(result)>200) stop('CATX error state');result
}
rows<-read.delim(args[1],colClasses='character',na.strings=NULL,check.names=FALSE)
cat('id,status,width,result\n')
for(i in seq_len(nrow(rows))) {
 answer<-tryCatch({
  source<-text(rows$source[i]);tail<-text(rows$tail[i]);delim<-text(rows$delimiter[i]);mode<-rows$mode[i]
  sw<-as.numeric(rows$source_width[i]);tw<-as.numeric(rows$target_width[i]);pos<-as.numeric(rows$position[i]);size<-as.numeric(rows$length[i])
  if(any(!is.finite(c(sw,tw,pos,size))) || any(c(sw,tw,pos,size)!=floor(c(sw,tw,pos,size))) || sw<length(source) || sw>32767 || tw<0 || tw>32767 || pos<1 || size<1) stop('bounds')
  source<-pad(source,sw)
  if(mode=='substr-reverse-source') source<-rev(source)
  if(mode=='substr-concat-source') source<-c(source,tail)
  if(length(source)>32767 || pos+size-1>length(source)) stop('bounds')
  extracted<-source[seq.int(pos,length.out=size)];width<-if(tw==0) length(source) else tw
  stored<-pad(extracted,width)
  if(mode=='stored-reverse') result<-rev(stored)
  else if(mode=='stored-concat') { result<-c(stored,tail);width<-width+length(tail);if(width>32767) stop('width') }
  else if(mode %in% c('stored-catx','catx-substr')) {
    rawmodel<-catx(delim,list(extracted,tail));paddedmodel<-catx(delim,list(pad(extracted,length(source)),tail))
    if(!identical(rawmodel,paddedmodel)) stop('padding-sensitive consumer')
    result<-if(mode=='catx-substr') rawmodel else catx(delim,list(stored,tail));width<-200
    result<-pad(result,width)
  } else if(mode %in% c('substr-reverse-source','substr-concat-source')) result<-stored
  else stop('mode')
  paste('OK',width,hex(result),sep=',')
 },error=function(e) 'REFUSED,,')
 cat(rows$id[i],',',answer,'\n',sep='')
}
